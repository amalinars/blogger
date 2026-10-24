#!/usr/bin/env python3
"""Shortlink gate-flow QA with an ad viewability check at step 3.

This mode walks the customer-facing gate: wait for each countdown, click the
Continue/Open order button, scroll to the native ad at step 3, then verify the
final redirect. Ad requests are allowed so the native unit can render.
"""

import argparse
import json
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.adsterra.engine import (
    create_camoufox_session,
    get_random_viewport,
    resolve_geo_profile,
)
from automation.adsterra.qa import (
    SessionBudget,
    _native_rendered,
    _scroll_to_ad_slot,
    _wait_for_ad_render,
    country_label,
    is_proxy_pool_exhausted,
    load_config,
)
from automation.adsterra.report import sanitize_payload, utc_now_iso
from automation.browser_verifier import BrowserVerifier
from core.proxy_manager import ProxyManager

DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "adsterra_qa"
STEP_TIMEOUT_SECONDS = 60.0
FINAL_REDIRECT_TIMEOUT_SECONDS = 10.0
EventCallback = Callable[[str, Dict[str, Any]], None]


def _emit(callback: Optional[EventCallback], event: str, **data: Any) -> None:
    if callback is None:
        return
    try:
        callback(event, data)
    except Exception:
        pass


def _log(callback: Optional[EventCallback], message: str) -> None:
    if callback is not None:
        _emit(callback, "log_message", message=message)
    else:
        print(f"[FLOW] {message}", flush=True)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _destination_matches(current_url: str, expected_url: str) -> bool:
    current = urlparse(current_url)
    expected = urlparse(expected_url)
    if not current.hostname or not expected.hostname:
        return False
    if current.hostname.lower() != expected.hostname.lower():
        return False
    expected_path = (expected.path or "/").rstrip("/")
    current_path = (current.path or "/").rstrip("/")
    return current_path == expected_path or current_path.startswith(
        expected_path + "/"
    )


def _wait_and_click_step(
    page: Any,
    index: int,
    event_callback: Optional[EventCallback],
) -> Dict[str, Any]:
    _emit(event_callback, "step_waiting", index=index + 1)
    step = page.locator(f"#step-{index}").first
    step.wait_for(state="visible", timeout=30000)
    step.evaluate(
        "(element) => element.scrollIntoView({block: 'center', behavior: 'instant'})"
    )
    page.wait_for_timeout(700)

    button = step.locator("button").first
    button.wait_for(state="visible", timeout=30000)
    label = (button.inner_text() or "").strip().replace("\n", " ")
    started = time.time()
    while time.time() - started < STEP_TIMEOUT_SECONDS:
        if button.is_enabled():
            break
        page.wait_for_timeout(250)
    else:
        raise TimeoutError(
            f"Step {index + 1} button did not become enabled within "
            f"{STEP_TIMEOUT_SECONDS:.0f}s."
        )

    waited = round(time.time() - started, 2)
    _log(
        event_callback,
        f"Langkah {index + 1} siap setelah {waited} dtk; klik {label!r}.",
    )
    try:
        button.click(timeout=8000)
    except Exception:
        _log(
            event_callback,
            f"Klik langkah {index + 1} terhalang; memakai cara cadangan.",
        )
        button.evaluate("(element) => element.click()")
    step_result = {
        "index": index + 1,
        "label": label,
        "waited_seconds": waited,
        "clicked": True,
    }
    _emit(event_callback, "step_completed", **step_result)
    return step_result


def _wait_for_active_step(page: Any, index: int) -> None:
    page.wait_for_function(
        """(stepIndex) => {
            const element = document.getElementById(`step-${stepIndex}`);
            return Boolean(element && element.getAttribute('aria-current') === 'step');
        }""",
        arg=index,
        timeout=30000,
    )


def _measure_ad_section(page: Any) -> Dict[str, Any]:
    try:
        return page.evaluate(
            """() => {
                const element = document.querySelector(
                    'section[aria-label="Advertisement"]'
                );
                if (!element) return { present: false };
                const rect = element.getBoundingClientRect();
                const viewportHeight = window.innerHeight || 0;
                const visible = Math.max(
                    0,
                    Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0)
                );
                return {
                    present: true,
                    top: Math.round(rect.top),
                    bottom: Math.round(rect.bottom),
                    height: Math.round(rect.height),
                    visiblePixels: Math.round(visible),
                    visibleRatio: rect.height > 0
                        ? Math.round((visible / rect.height) * 1000) / 1000
                        : 0,
                    inViewport: visible > 0,
                    scrollY: Math.round(window.scrollY),
                    scrollHeight: document.body ? document.body.scrollHeight : 0,
                    viewportHeight
                };
            }"""
        )
    except Exception:
        return {"present": False}


AD_SLOT_SELECTOR = (
    'section[aria-label="Advertisement"], '
    '[id^="container-"], [id*="adsterra"], [class*="adsterra"], '
    'iframe[src*="abscloud"], iframe[src*="bauval"]'
)


def _scan_ad_slots(page: Any) -> List[Dict[str, Any]]:
    """Tag every top-level ad unit on the page and return its viewport metrics."""
    try:
        return page.evaluate(
            """(selector) => {
                const nodes = Array.from(document.querySelectorAll(selector));
                const top = nodes.filter(
                    (el) => !nodes.some((other) => other !== el && other.contains(el))
                );
                return top.map((el, index) => {
                    el.setAttribute('data-qa-ad-slot', String(index));
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const vw = window.innerWidth || 0;
                    const vh = window.innerHeight || 0;
                    const visW = Math.max(0, Math.min(rect.right, vw) - Math.max(rect.left, 0));
                    const visH = Math.max(0, Math.min(rect.bottom, vh) - Math.max(rect.top, 0));
                    const area = Math.max(1, rect.width * rect.height);
                    return {
                        index,
                        tag: el.tagName,
                        id: el.id || '',
                        className: String(el.className || ''),
                        src: el.src || '',
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        visibleRatio: Math.round(((visW * visH) / area) * 1000) / 1000,
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity
                    };
                });
            }""",
            AD_SLOT_SELECTOR,
        )
    except Exception:
        return []


def _dwell_on_ad_slots(
    page: Any,
    config: Dict[str, Any],
    label: str,
    event_callback: Optional[EventCallback] = None,
    worker_id: int = 1,
) -> List[Dict[str, Any]]:
    """Scroll each ad unit into view, keep it viewable, and report the dwell."""
    min_ratio = float(config.get("min_visible_ratio", 0.5))
    dwell_seconds = float(config.get("ad_dwell_seconds", 3.5))
    max_slots = int(config.get("max_ad_slots_per_pass", 4))
    wait_seconds = float(config.get("ad_wait_seconds", 12.0))

    deadline = time.time() + wait_seconds
    slots: List[Dict[str, Any]] = []
    while time.time() < deadline:
        slots = _scan_ad_slots(page)
        if slots:
            break
        page.wait_for_timeout(400)

    observed: List[Dict[str, Any]] = []
    for slot in slots[:max_slots]:
        index = slot.get("index")
        try:
            page.evaluate(
                """(idx) => {
                    const el = document.querySelector(`[data-qa-ad-slot="${idx}"]`);
                    if (el) el.scrollIntoView({block: 'center', behavior: 'instant'});
                }""",
                index,
            )
        except Exception:
            pass

        ratio = float(slot.get("visibleRatio") or 0)
        visible_deadline = time.time() + 2.5
        while time.time() < visible_deadline:
            page.wait_for_timeout(300)
            current = _scan_ad_slots(page)
            match = next((s for s in current if s.get("index") == index), None)
            if match:
                ratio = float(match.get("visibleRatio") or ratio)
                if ratio >= min_ratio:
                    break

        dwelled = 0.0
        try:
            viewport = page.viewport_size or {}
        except Exception:
            viewport = {}
        if not viewport.get("width") or not viewport.get("height"):
            viewport = {"width": 1366, "height": 768}
        dwell_end = time.time() + dwell_seconds
        while time.time() < dwell_end:
            try:
                page.mouse.move(
                    random.randint(50, max(60, int(viewport.get("width", 1366)) - 50)),
                    random.randint(50, max(60, int(viewport.get("height", 768)) - 50)),
                )
            except Exception:
                pass
            page.wait_for_timeout(250)
            dwelled += 0.25

        entry = {
            "label": label,
            "index": index,
            "id": slot.get("id", ""),
            "tag": slot.get("tag", ""),
            "src": slot.get("src", ""),
            "width": slot.get("width", 0),
            "height": slot.get("height", 0),
            "visible_ratio": round(ratio, 3),
            "visible": ratio >= min_ratio,
            "dwell_seconds": round(dwelled, 2),
        }
        observed.append(entry)
        _emit(
            event_callback,
            "ad_dwell",
            worker_id=worker_id,
            label=label,
            ad_id=entry["id"],
            visible=entry["visible"],
            visible_ratio=entry["visible_ratio"],
            dwell_seconds=entry["dwell_seconds"],
        )
        _log(
            event_callback,
            f"Iklan {label}: {entry['tag']}#{entry['id'] or '-'} "
            f"terlihat {entry['visible_ratio']:.0%} selama "
            f"{entry['dwell_seconds']:.1f} dtk.",
        )

    return observed


def _check_ad_viewability(
    page: Any,
    config: Dict[str, Any],
    popups: List[str],
    event_callback: Optional[EventCallback] = None,
    worker_id: int = 1,
) -> Dict[str, Any]:
    started = time.time()
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(900)
    except Exception:
        pass

    _scroll_to_ad_slot(page, config)
    snapshot = _wait_for_ad_render(page, config, expected_url=page.url)
    native = snapshot.get("native_container") or {}
    section = _measure_ad_section(page)
    resources = snapshot.get("resources") or []
    hosts = sorted(
        {
            _host(entry.get("name", ""))
            for entry in resources
            if _host(entry.get("name", ""))
        }
    )
    section_ratio = float(section.get("visibleRatio") or 0)
    native_ratio = float(native.get("visibleRatio") or 0)

    slots = _dwell_on_ad_slots(
        page,
        config,
        label="akhir",
        event_callback=event_callback,
        worker_id=worker_id,
    )
    visible_slots = [slot for slot in slots if slot.get("visible")]
    any_visible = bool(
        visible_slots
        or (section.get("inViewport") and section_ratio >= 0.5)
        or native_ratio >= 0.5
    )

    return {
        "section_present": bool(section.get("present")),
        "section_visible_ratio": section_ratio,
        "section_in_viewport": bool(section.get("inViewport"))
        and section_ratio >= 0.5,
        "native_present": bool(native.get("present")),
        "native_rendered": _native_rendered(native),
        "native_visible_ratio": native_ratio,
        "native_in_viewport": native_ratio >= 0.5,
        "scroll_y": int(section.get("scrollY") or native.get("scrollY") or 0),
        "scroll_height": int(section.get("scrollHeight") or 0),
        "viewport_height": int(
            section.get("viewportHeight") or native.get("viewportHeight") or 0
        ),
        "ad_resources": len(resources),
        "ad_resource_hosts": hosts[:10],
        "popups_opened": len(popups),
        "ad_slots": slots,
        "visible_ad_count": len(visible_slots),
        "any_ad_visible": any_visible,
        "total_dwell_seconds": round(
            sum(float(slot.get("dwell_seconds") or 0) for slot in slots), 2
        ),
        "waited_seconds": round(time.time() - started, 2),
    }


def _read_browser_geo(page: Any) -> Dict[str, Any]:
    try:
        return page.evaluate(
            """() => ({
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
                locale: navigator.language || '',
                languages: navigator.languages || [],
                offset_minutes: new Date().getTimezoneOffset()
            })"""
        )
    except Exception:
        return {}


def _take_screenshot(page: Any, report_dir: str, stamp: str, label: str) -> Optional[str]:
    try:
        directory = Path(report_dir) / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"flow_{stamp}_{label}.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def _write_report(report_dir: str, result: Dict[str, Any]) -> str:
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"flow_{stamp}.json"
    path.write_text(
        json.dumps(sanitize_payload(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(path)


def run_flow_session(
    config: Dict[str, Any],
    headless: bool = True,
    url: Optional[str] = None,
    screenshot: bool = False,
    event_callback: Optional[EventCallback] = None,
    worker_id: int = 1,
    proxy_data: Optional[Dict[str, Any]] = None,
    enable_verifier: bool = False,
    stop_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    target_url = url or str(config.get("target_url") or "")
    report_dir = str(config.get("report_dir") or DEFAULT_REPORT_DIR)
    started = time.time()
    started_at = utc_now_iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    proxy_info: Dict[str, Any] = {}
    if proxy_data:
        proxy_info = {
            "id": proxy_data.get("id") or "",
            "ip": proxy_data.get("ip_detected") or proxy_data.get("host") or "unknown",
            "country": country_label(proxy_data.get("country")),
        }

    result: Dict[str, Any] = {
        "mode": "shortlink-flow",
        "worker_id": worker_id,
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "target_url": target_url,
        "proxy": proxy_info,
        "verifier": {},
        "geo": {},
        "ad_observations": [],
        "destination_url": None,
        "final_url": None,
        "redirect_mode": None,
        "status": "FAIL",
        "score": 0,
        "checks": {},
        "steps": [],
        "ad": {},
        "ads_allowed": True,
        "warnings": [],
        "off_target_navigations": [],
        "navigation_requests": [],
        "request_failures": [],
        "popups": [],
        "page_errors": [],
        "console_errors": [],
        "issues": [],
        "screenshot": None,
        "report_path": None,
    }

    page = None
    last_main_url = ""
    navigation_requests: List[Dict[str, Any]] = []
    request_failures: List[Dict[str, Any]] = []
    off_target_navigations: List[str] = []
    popups: List[str] = []
    pending_popups: List[Any] = []
    ad_observations: List[Dict[str, Any]] = []
    page_errors: List[str] = []
    console_errors: List[str] = []

    try:
        with create_camoufox_session(
            proxy_data=proxy_data,
            headless=headless,
            humanize=bool(config.get("humanize", False)),
            allow_ads=True,
        ) as browser:
            page = browser.new_page(viewport=get_random_viewport())
            page.set_default_timeout(30000)

            def on_frame_navigated(frame: Any) -> None:
                nonlocal last_main_url
                try:
                    if frame.parent_frame is not None:
                        return
                    new_url = str(frame.url or "")
                    if not new_url:
                        return
                    previous = last_main_url
                    last_main_url = new_url
                    if (
                        previous
                        and _host(new_url) != _host(target_url)
                        and new_url not in off_target_navigations
                    ):
                        off_target_navigations.append(new_url)
                    if previous != new_url:
                        _emit(
                            event_callback,
                            "main_frame_navigated",
                            url=new_url,
                        )
                except Exception:
                    pass

            def on_request(request: Any) -> None:
                try:
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        navigation_requests.append(
                            {
                                "url": request.url,
                                "host": _host(request.url),
                                "decision": "allow",
                            }
                        )
                except Exception:
                    pass

            def on_popup(popup: Any) -> None:
                # Never close immediately: the popunder only counts as an
                # impression once its advertiser page has actually loaded.
                try:
                    url = str(popup.url or "")
                    popups.append(url)
                    pending_popups.append(popup)
                    _emit(
                        event_callback,
                        "popup_opened",
                        worker_id=worker_id,
                        url=url,
                    )
                except Exception:
                    pass

            def drain_popups() -> None:
                """Give each popunder time to load and be viewed, then close."""
                dwell_cfg = config.get("popup_dwell_seconds", {}) or {}
                low = float(dwell_cfg.get("min", 15.0))
                high = float(dwell_cfg.get("max", 25.0))
                while pending_popups:
                    popup = pending_popups.pop(0)
                    try:
                        if popup.is_closed():
                            continue
                        try:
                            popup.wait_for_load_state(
                                "domcontentloaded", timeout=15000
                            )
                        except Exception:
                            pass
                        try:
                            popup.bring_to_front()
                        except Exception:
                            pass
                        url = ""
                        try:
                            url = str(popup.url or "")
                        except Exception:
                            pass
                        _emit(
                            event_callback,
                            "popup_dwell",
                            worker_id=worker_id,
                            url=url,
                        )
                        _log(
                            event_callback,
                            f"Popunder dibiarkan terbuka {low:.0f}-{high:.0f} dtk.",
                        )
                        dwell_end = time.time() + random.uniform(low, high)
                        try:
                            viewport = popup.viewport_size or {}
                        except Exception:
                            viewport = {}
                        if not viewport.get("width") or not viewport.get("height"):
                            viewport = {"width": 1366, "height": 768}
                        while time.time() < dwell_end:
                            if stop_event and stop_event.is_set():
                                break
                            try:
                                popup.mouse.move(
                                    random.randint(
                                        40,
                                        max(50, int(viewport["width"]) - 40),
                                    ),
                                    random.randint(
                                        40,
                                        max(50, int(viewport["height"]) - 40),
                                    ),
                                )
                            except Exception:
                                pass
                            if random.random() < 0.3:
                                try:
                                    popup.mouse.wheel(0, random.randint(20, 140))
                                except Exception:
                                    pass
                            popup.wait_for_timeout(400)
                        try:
                            popup.close()
                        except Exception:
                            pass
                        _emit(
                            event_callback,
                            "popup_closed",
                            worker_id=worker_id,
                            url=url,
                        )
                    except Exception:
                        pass
                try:
                    page.bring_to_front()
                except Exception:
                    pass

            def on_page_error(error: Any) -> None:
                if len(page_errors) < 20:
                    page_errors.append(str(error)[:500])

            def on_console(message: Any) -> None:
                try:
                    if message.type == "error" and len(console_errors) < 30:
                        console_errors.append(str(message.text)[:500])
                except Exception:
                    pass

            def on_request_failed(request: Any) -> None:
                try:
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        request_failures.append(
                            {
                                "url": request.url,
                                "error": str(request.failure or ""),
                            }
                        )
                except Exception:
                    pass

            page.on("framenavigated", on_frame_navigated)
            page.on("request", on_request)
            page.on("popup", on_popup)
            page.on("pageerror", on_page_error)
            page.on("console", on_console)
            page.on("requestfailed", on_request_failed)

            # ── Sticky proxy assignment surfaced to the dashboard ──
            expected_geo = resolve_geo_profile(proxy_data)
            result["geo"]["expected"] = expected_geo
            if proxy_info:
                _emit(
                    event_callback,
                    "proxy_assigned",
                    worker_id=worker_id,
                    proxy_id=proxy_info["id"],
                    ip=proxy_info["ip"],
                    country=proxy_info["country"],
                    timezone=expected_geo.get("timezone"),
                    locale=expected_geo.get("locale"),
                    geo_source=expected_geo.get("source"),
                    status=f"IP: {proxy_info['ip']} ({proxy_info['country']})",
                )

            # ── Independent browser + proxy verifier (pre-flight audit) ──
            if enable_verifier:
                _emit(
                    event_callback,
                    "status_update",
                    worker_id=worker_id,
                    status="Cek keamanan browser...",
                )
                try:
                    page.goto("about:blank", wait_until="domcontentloaded", timeout=20000)
                    verifier = BrowserVerifier(
                        strict_mode=bool(config.get("strict_verifier", False))
                    )
                    report = verifier.verify(
                        page,
                        expected_ip=(proxy_data or {}).get("ip_detected"),
                        expected_country=(proxy_data or {}).get("country"),
                        check_ads=True,
                    )
                    actual = report.actual_state
                    result["verifier"] = report.to_dict()
                    _emit(
                        event_callback,
                        "verifier_report",
                        worker_id=worker_id,
                        score=report.score,
                        is_safe=report.is_safe,
                        detected_ip=actual.get("ip"),
                        detected_country=country_label(actual.get("country")),
                        isp=actual.get("isp"),
                        bot_detected=bool(actual.get("webdriver")),
                        webdriver_hidden=actual.get("webdriver") is False,
                        webrtc_leak=bool(actual.get("webrtc_leak")),
                        ads_allowed=bool(actual.get("ads_allowed", True)),
                        adblock_detected=bool(actual.get("adblock_detected", False)),
                        os=actual.get("detected_os", "unknown"),
                    )
                    _log(
                        event_callback,
                        f"[W{worker_id}] Cek browser {report.score}/100 | "
                        f"bot={'ketahuan' if actual.get('webdriver') else 'aman'} | "
                        f"IP keluar={actual.get('ip')} | "
                        f"webrtc={'bocor' if actual.get('webrtc_leak') else 'aman'}",
                    )
                except Exception as error:
                    _log(
                        event_callback,
                        f"[W{worker_id}] Catatan cek: {str(error)[:120]}",
                    )

            _emit(event_callback, "session_started", worker_id=worker_id)
            _emit(event_callback, "flow_started", target_url=target_url)
            _log(event_callback, f"Membuka {target_url} (iklan aktif)")
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_selector("#step-0", timeout=30000)

            # ── Report the real browser clock/locale vs. the proxy profile ──
            actual_geo = _read_browser_geo(page)
            expected_tz = str(expected_geo.get("timezone") or "")
            expected_locale = str(expected_geo.get("locale") or "")
            actual_tz = str(actual_geo.get("timezone") or "")
            actual_locale = str(actual_geo.get("locale") or "")
            tz_matched = (
                actual_tz.lower() == expected_tz.lower()
                if expected_tz and actual_tz
                else None
            )
            locale_matched = (
                actual_locale.lower() == expected_locale.lower()
                if expected_locale and actual_locale
                else None
            )
            result["geo"].update({
                "actual": actual_geo,
                "timezone_matched": tz_matched,
                "locale_matched": locale_matched,
            })
            _emit(
                event_callback,
                "geo_report",
                worker_id=worker_id,
                expected_timezone=expected_tz or "—",
                expected_locale=expected_locale or "—",
                actual_timezone=actual_tz or "—",
                actual_locale=actual_locale or "—",
                timezone_matched=tz_matched,
                locale_matched=locale_matched,
                geo_source=expected_geo.get("source", "unknown"),
            )
            _log(
                event_callback,
                f"Geo sinkron: zona {actual_tz or '—'} "
                f"(proxy {expected_tz or '—'}), "
                f"locale {actual_locale or '—'} "
                f"(proxy {expected_locale or '—'}).",
            )
            if tz_matched is False:
                result["warnings"].append(
                    f"Timezone mismatch: browser '{actual_tz}' vs proxy "
                    f"'{expected_tz}'."
                )
            if locale_matched is False:
                result["warnings"].append(
                    f"Locale mismatch: browser '{actual_locale}' vs proxy "
                    f"'{expected_locale}'."
                )

            page.locator("#step-0").first.evaluate(
                "(element) => element.scrollIntoView({block: 'center', behavior: 'instant'})"
            )
            page.wait_for_timeout(500)

            ad_observations.extend(
                _dwell_on_ad_slots(
                    page,
                    config,
                    label="muat awal",
                    event_callback=event_callback,
                    worker_id=worker_id,
                )
            )
            drain_popups()

            for index in range(3):
                step_result = _wait_and_click_step(page, index, event_callback)
                result["steps"].append(step_result)
                ad_observations.extend(
                    _dwell_on_ad_slots(
                        page,
                        config,
                        label=f"langkah {index + 1}",
                        event_callback=event_callback,
                        worker_id=worker_id,
                    )
                )
                drain_popups()
                if screenshot:
                    path = _take_screenshot(
                        page, report_dir, stamp, f"step{index + 1}"
                    )
                    if path:
                        result["screenshot"] = path
                if index < 2:
                    _wait_for_active_step(page, index + 1)
                else:
                    page.locator("#destination").wait_for(
                        state="visible", timeout=30000
                    )
                    _log(
                        event_callback,
                        "Tiga langkah selesai; tombol tujuan sudah muncul.",
                    )

            final_link = page.locator("#destination a[href]").first
            final_link.wait_for(state="visible", timeout=20000)
            destination_url = final_link.get_attribute("href") or ""
            result["destination_url"] = destination_url
            if not destination_url:
                raise RuntimeError("Final destination link has no href.")
            _emit(
                event_callback,
                "destination_visible",
                destination_url=destination_url,
            )

            _log(event_callback, "Scroll ke iklan di langkah 3.")
            ad = _check_ad_viewability(
                page,
                config,
                popups,
                event_callback=event_callback,
                worker_id=worker_id,
            )
            ad_observations.extend(ad.get("ad_slots") or [])
            drain_popups()
            result["ad"] = ad
            result["ad_observations"] = ad_observations
            ads_visible_during_flow = any(
                bool(entry.get("visible")) for entry in ad_observations
            )
            ad_checks = {
                "ad_section_in_viewport": ad["section_in_viewport"],
                "native_ad_rendered": ad["native_rendered"],
                "native_ad_in_viewport": ad["native_in_viewport"],
                "ads_visible_during_flow": ads_visible_during_flow,
            }
            _emit(event_callback, "ad_check", ad=ad, checks=ad_checks)
            if not ad["native_rendered"]:
                result["warnings"].append(
                    "Native ad container did not render within the wait window."
                )
            if not ad["native_in_viewport"]:
                result["warnings"].append(
                    "Native ad container was not at least 50% in the viewport."
                )
            if not ads_visible_during_flow:
                result["warnings"].append(
                    "No ad unit stayed at least 50% in view during the flow."
                )
            _log(
                event_callback,
                "Cek iklan "
                f"bagian={ad['section_visible_ratio']:.0%} "
                f"iklan={'termuat' if ad['native_rendered'] else 'kosong'} "
                f"terlihat={ad['native_in_viewport']} "
                f"unit_terlihat={ad['visible_ad_count']} "
                f"dwell={ad['total_dwell_seconds']:.1f} dtk "
                f"jumlah={ad['ad_resources']}",
            )

            final_link.scroll_into_view_if_needed()
            page.wait_for_timeout(350)
            _log(
                event_callback,
                f"Klik tombol akhir ke {destination_url}",
            )
            _emit(
                event_callback,
                "redirect_started",
                destination_url=destination_url,
            )
            try:
                final_link.click(timeout=8000)
            except Exception:
                _log(
                    event_callback,
                    "Klik akhir terhalang; memakai cara cadangan.",
                )
                final_link.evaluate("(element) => element.click()")

            click_redirect_url = ""
            deadline = time.time() + FINAL_REDIRECT_TIMEOUT_SECONDS
            while time.time() < deadline:
                candidates = [last_main_url, page.url]
                try:
                    candidates.append(page.evaluate("location.href"))
                except Exception:
                    pass
                for candidate in candidates:
                    if candidate and _destination_matches(candidate, destination_url):
                        click_redirect_url = candidate
                        break
                if click_redirect_url:
                    break
                time.sleep(0.5)

            redirect_mode = "click" if click_redirect_url else "fallback"
            result["redirect_mode"] = redirect_mode
            if not click_redirect_url:
                message = (
                    "Klik akhir tidak membuka halaman; menuju alamat secara langsung."
                )
                _log(event_callback, message)
                result["warnings"].append(message)
                try:
                    page.goto(
                        destination_url,
                        wait_until="domcontentloaded",
                        timeout=45000,
                    )
                except Exception as error:
                    result["issues"].append(
                        f"Fallback destination load failed: {str(error)[:300]}"
                    )
            else:
                _log(event_callback, f"Sampai lewat klik: {click_redirect_url}")
                _emit(
                    event_callback,
                    "redirect_reached",
                    final_url=click_redirect_url,
                )

            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            try:
                final_url = page.evaluate("location.href")
            except Exception:
                final_url = last_main_url or page.url
            result["final_url"] = final_url
            final_ok = _destination_matches(final_url, destination_url)
            if final_ok:
                _log(event_callback, f"Sampai di tujuan: {final_url}")
            else:
                result["issues"].append(
                    f"Final redirect did not reach the destination: {final_url}"
                )

            if screenshot:
                path = _take_screenshot(page, report_dir, stamp, "final")
                if path:
                    result["screenshot"] = path

            checks = {
                "page_loaded": bool(result["steps"]),
                "step_1_completed": len(result["steps"]) >= 1,
                "step_2_completed": len(result["steps"]) >= 2,
                "step_3_completed": len(result["steps"]) >= 3,
                "destination_visible": bool(destination_url),
                **ad_checks,
                "final_redirect_ok": final_ok,
            }
            result["checks"] = checks
            result["status"] = "PASS" if all(checks.values()) else "FAIL"
            result["score"] = 100 if result["status"] == "PASS" else 0

    except Exception as error:
        result["status"] = "FAIL"
        result["score"] = 0
        result["issues"].append(f"Kesalahan: {str(error)[:400]}")
        if page is not None and screenshot:
            path = _take_screenshot(page, report_dir, stamp, "error")
            if path:
                result["screenshot"] = path
    finally:
        result["finished_at"] = utc_now_iso()
        result["duration_seconds"] = round(time.time() - started, 2)
        result["off_target_navigations"] = off_target_navigations[:20]
        result["navigation_requests"] = navigation_requests[:30]
        result["request_failures"] = request_failures[:20]
        result["popups"] = popups[:10]
        result["page_errors"] = page_errors[:20]
        result["console_errors"] = console_errors[:20]
        result["report_path"] = _write_report(report_dir, result)
        _emit(event_callback, "flow_completed", **result)
        _emit(
            event_callback,
            "session_completed",
            worker_id=worker_id,
            status=result["status"],
            score=result["score"],
        )

    return result


def flow_worker_thread_loop_sticky(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[EventCallback] = None,
    stop_event: Optional[threading.Event] = None,
    sticky_proxy_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Cycle flow sessions with a permanently-assigned (sticky) proxy.

    The proxy is never returned to the pool, so the worker always keeps its
    unique IP. Each iteration runs the gate-flow plus the browser verifier.
    """
    tag = f"[W{worker_id}]"
    proxy_data = sticky_proxy_data or {}
    ip = proxy_data.get("ip_detected") or proxy_data.get("host", "?")
    country = country_label(proxy_data.get("country"))

    def _log(message: str, style: str = "white") -> None:
        if event_callback:
            event_callback(
                "log_message",
                {"worker_id": worker_id, "message": f"{tag} {message}", "style": style},
            )

    _log(f"Browser siap — IP {ip} ({country}).", "green")
    if event_callback and sticky_proxy_data:
        event_callback(
            "proxy_assigned",
            {
                "worker_id": worker_id,
                "proxy_id": sticky_proxy_data.get("id", ""),
                "ip": ip,
                "country": country,
                "status": f"IP: {ip} ({country})",
            },
        )

    enable_verifier = bool(config.get("run_browser_verifier", True))
    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break
        if not budget.reserve():
            break

        proxy_id = sticky_proxy_data.get("id") if sticky_proxy_data else None
        if proxy_id:
            budget.mark_proxy(proxy_id)

        try:
            result = run_flow_session(
                config,
                headless=bool(config.get("headless", True)),
                url=config.get("target_url"),
                screenshot=bool(config.get("screenshot", False)),
                event_callback=event_callback,
                worker_id=worker_id,
                proxy_data=sticky_proxy_data,
                enable_verifier=enable_verifier,
                stop_event=stop_event,
            )
            budget.record((result or {}).get("status", "FAIL"))
        except Exception as error:
            budget.record("FAIL")
            _log(f"Kesalahan browser: {str(error)[:160]}", "red")

        if stop_event and stop_event.is_set():
            break
        if budget.is_exhausted():
            break

        # Sticky mode: never check covered_all — the proxy is always ours.
        stats = proxy_manager.get_stats()
        if is_proxy_pool_exhausted(stats):
            budget.stop()
            _log("Stok IP habis. Berhenti.", "yellow")
            break

        cooldown = config.get("session_cooldown_seconds", {}) or {}
        delay = random.uniform(
            float(cooldown.get("min", 5.0)), float(cooldown.get("max", 10.0))
        )
        if event_callback:
            event_callback(
                "status_update",
                {"worker_id": worker_id, "status": f"Jeda {delay:.0f} detik..."},
            )
        sleep_end = time.time() + delay
        while time.time() < sleep_end and not (stop_event and stop_event.is_set()):
            time.sleep(0.3)

    _log("Browser selesai.", "dim")


def flow_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[EventCallback] = None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """Cycle flow sessions while rotating to a fresh, never-reused proxy.

    Every completed visit releases its proxy and the next visit acquires a
    different one. With the per-proxy cap at 1 the same IP is never used twice
    in a single run; once every IP has been used the run stops.
    """
    tag = f"[W{worker_id}]"

    def _log(message: str, style: str = "white") -> None:
        if event_callback:
            event_callback(
                "log_message",
                {"worker_id": worker_id, "message": f"{tag} {message}", "style": style},
            )

    caller_prefix = f"flow_rot_w{worker_id}"
    enable_verifier = bool(config.get("run_browser_verifier", True))
    _log("Browser siap — IP dirotasi tiap kunjungan.", "green")

    idle_rounds = 0
    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break

        caller_id = f"{caller_prefix}_{int(time.time() * 1000)}"
        proxy = proxy_manager.acquire_proxy(
            caller_id=caller_id, exclusive=True, verify_alive=True
        )
        if not proxy:
            stats = proxy_manager.get_stats()
            if is_proxy_pool_exhausted(stats):
                budget.stop()
                _log("Stok IP habis. Berhenti.", "yellow")
                break
            idle_rounds += 1
            if event_callback:
                event_callback(
                    "status_update",
                    {"worker_id": worker_id, "status": "Menunggu IP bebas..."},
                )
            if idle_rounds > 30:
                _log("Tidak ada IP bebas. Berhenti.", "yellow")
                break
            time.sleep(2.0)
            continue

        proxy_id = proxy.get("id") or ""
        # Never reuse an IP already used in this run (per-proxy cap).
        if not budget.can_use_proxy(proxy_id):
            proxy_manager.release_proxy(proxy_id, caller_id=caller_id)
            stats = proxy_manager.get_stats()
            if budget.covered_all(stats.get("total", 0)):
                budget.stop()
                _log("Semua IP sudah pernah dipakai. Berhenti.", "yellow")
                break
            idle_rounds += 1
            if idle_rounds > 60:
                _log("Tidak ada IP baru. Berhenti.", "yellow")
                break
            time.sleep(0.5)
            continue

        idle_rounds = 0
        if not budget.reserve():
            proxy_manager.release_proxy(proxy_id, caller_id=caller_id)
            break
        budget.mark_proxy(proxy_id)

        ip = proxy.get("ip_detected") or proxy.get("host", "?")
        country = country_label(proxy.get("country"))
        if event_callback:
            event_callback(
                "proxy_assigned",
                {
                    "worker_id": worker_id,
                    "proxy_id": proxy_id,
                    "ip": ip,
                    "country": country,
                    "status": f"IP: {ip} ({country})",
                },
            )

        try:
            result = run_flow_session(
                config,
                headless=bool(config.get("headless", True)),
                url=config.get("target_url"),
                screenshot=bool(config.get("screenshot", False)),
                event_callback=event_callback,
                worker_id=worker_id,
                proxy_data=proxy,
                enable_verifier=enable_verifier,
                stop_event=stop_event,
            )
            budget.record((result or {}).get("status", "FAIL"))
        except Exception as error:
            budget.record("FAIL")
            _log(f"Kesalahan browser: {str(error)[:160]}", "red")
        finally:
            proxy_manager.release_proxy(proxy_id, caller_id=caller_id)

        if stop_event and stop_event.is_set():
            break
        if budget.is_exhausted():
            break

        stats = proxy_manager.get_stats()
        if is_proxy_pool_exhausted(stats):
            budget.stop()
            _log("Stok IP habis. Berhenti.", "yellow")
            break
        if budget.covered_all(stats.get("total", 0)):
            budget.stop()
            _log("Semua IP sudah pernah dipakai. Berhenti.", "yellow")
            break

        cooldown = config.get("session_cooldown_seconds", {}) or {}
        delay = random.uniform(
            float(cooldown.get("min", 5.0)), float(cooldown.get("max", 10.0))
        )
        if event_callback:
            event_callback(
                "status_update",
                {
                    "worker_id": worker_id,
                    "status": f"Rotasi IP berikutnya — jeda {delay:.0f} detik...",
                },
            )
        sleep_end = time.time() + delay
        while time.time() < sleep_end and not (stop_event and stop_event.is_set()):
            time.sleep(0.3)

    _log("Browser selesai.", "dim")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded shortlink gate-flow QA with ads enabled and a "
            "step-3 native-ad viewability check."
        )
    )
    parser.add_argument("--url", help="Override the configured target URL.")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of flow runs, capped at 3 (default: 1).",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window.",
    )
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Save step screenshots (disabled by default to keep runs light).",
    )
    args = parser.parse_args()

    runs = max(1, min(args.runs, 3))
    config = load_config()
    failures = 0

    for run_index in range(1, runs + 1):
        _log(None, f"Run {run_index}/{runs}")
        result = run_flow_session(
            config,
            headless=not args.no_headless,
            url=args.url,
            screenshot=args.screenshot,
        )
        print(
            json.dumps(
                {
                    "run": run_index,
                    "status": result["status"],
                    "score": result["score"],
                    "steps": result["steps"],
                    "ad": result["ad"],
                    "redirect_mode": result["redirect_mode"],
                    "warnings": result["warnings"],
                    "destination_url": result["destination_url"],
                    "final_url": result["final_url"],
                    "issues": result["issues"],
                    "report_path": result["report_path"],
                    "screenshot": result["screenshot"],
                },
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )
        if result["status"] != "PASS":
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
