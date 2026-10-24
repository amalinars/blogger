#!/usr/bin/env python3
"""Adsterra ad-render QA worker.

This module only loads the configured page through the proxy pool and inspects
ad scripts, containers, and network traffic. It never clicks advertisements and
hard-caps the number of visits per run.
"""

import json
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page

from automation.adsterra.engine import create_camoufox_session, get_random_viewport
from automation.adsterra.report import (
    is_ad_url,
    same_host,
    summarize_ad_checks,
    utc_now_iso,
    write_session_report,
)
from automation.browser_verifier import BrowserVerifier
from core.proxy_manager import ProxyManager

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
CONFIG_FILE = CURRENT_DIR / "config.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "adsterra_qa"


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            pass
    return {
        "target_url": "https://article.riztama.my.id/",
        "headless": True,
        "humanize": True,
        "run_browser_verifier": True,
        "strict_verifier": False,
        "wait_after_load_seconds": 5.0,
        "ad_wait_seconds": 12.0,
        "ad_dwell_seconds": 3.5,
        "max_ad_slots_per_pass": 4,
        "scroll_to_ad": True,
        "min_visible_ratio": 0.5,
        "popup_dwell_seconds": {"min": 15.0, "max": 25.0},
        "screenshot": True,
        "report_dir": str(DEFAULT_REPORT_DIR),
        "concurrency": 2,
        "max_sessions_per_run": 8,
        "max_sessions_per_proxy": 1,
        "session_cooldown_seconds": {"min": 5.0, "max": 10.0},
        "adsterra_hosts": ["bauval.org"],
        "social_bar_script_id": "adsterra-social-bar",
        "native_script_id": "adsterra-native-banner",
        "native_container_id": "container-eff1cc809a63f65a58e6ad5541eb7757",
    }


def emit_log(
    message: str,
    tag: str = "[QA]",
    style: str = "white",
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    worker_id: int = 1,
) -> None:
    if event_callback:
        event_callback(
            "log_message",
            {
                "worker_id": worker_id,
                "message": f"{tag} {message}",
                "style": style,
            },
        )
    else:
        print(f"{tag} {message}")


def country_label(country: Optional[str]) -> str:
    return (country or "Unknown").strip() or "Unknown"


def is_proxy_pool_exhausted(stats: Dict[str, Any]) -> bool:
    """True when no proxy is usable and no worker is still holding one."""
    if not stats:
        return False
    if stats.get("in_use", 0) > 0:
        return False
    usable = (
        stats.get("alive", 0)
        + stats.get("unknown", 0)
        + stats.get("cooldown", 0)
    )
    return usable == 0


class SessionBudget:
    """Thread-safe cap that prevents unbounded QA visits."""

    def __init__(self, max_sessions: int, max_sessions_per_proxy: int = 1):
        self.max_sessions = max(1, int(max_sessions))
        self.max_sessions_per_proxy = max(1, int(max_sessions_per_proxy))
        self._lock = threading.RLock()
        self.reserved = 0
        self.completed = 0
        self.passed = 0
        self.warned = 0
        self.failed = 0
        self.stopped = False
        self.proxy_counts: Dict[str, int] = {}

    def has_capacity(self) -> bool:
        with self._lock:
            return not self.stopped and self.reserved < self.max_sessions

    def is_exhausted(self) -> bool:
        with self._lock:
            return self.stopped or self.completed >= self.max_sessions

    def stop(self) -> None:
        with self._lock:
            self.stopped = True

    def reserve(self) -> bool:
        with self._lock:
            if self.stopped or self.reserved >= self.max_sessions:
                return False
            self.reserved += 1
            return True

    def can_use_proxy(self, proxy_id: str) -> bool:
        with self._lock:
            return self.proxy_counts.get(proxy_id, 0) < self.max_sessions_per_proxy

    def mark_proxy(self, proxy_id: str) -> None:
        with self._lock:
            self.proxy_counts[proxy_id] = self.proxy_counts.get(proxy_id, 0) + 1

    def record(self, status: str) -> None:
        with self._lock:
            self.completed += 1
            if status == "PASS":
                self.passed += 1
            elif status == "WARN":
                self.warned += 1
            else:
                self.failed += 1

    def covered_all(self, total_proxies: int) -> bool:
        with self._lock:
            if total_proxies <= 0:
                return False
            covered = sum(
                1
                for count in self.proxy_counts.values()
                if count >= self.max_sessions_per_proxy
            )
            return covered >= total_proxies

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "max_sessions": self.max_sessions,
                "max_sessions_per_proxy": self.max_sessions_per_proxy,
                "reserved": self.reserved,
                "completed": self.completed,
                "passed": self.passed,
                "warned": self.warned,
                "failed": self.failed,
                "remaining": max(0, self.max_sessions - self.completed),
                "proxy_counts": dict(self.proxy_counts),
                "stopped": self.stopped,
            }


def _collect_dom_snapshot(page: Page, config: Dict[str, Any]) -> Dict[str, Any]:
    native_id = config.get("native_container_id", "")
    return page.evaluate(
        """(nativeId) => {
            const metric = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const viewportWidth = window.innerWidth || 0;
                const viewportHeight = window.innerHeight || 0;
                const visibleWidth = Math.max(0, Math.min(rect.right, viewportWidth) - Math.max(rect.left, 0));
                const visibleHeight = Math.max(0, Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0));
                const area = Math.max(1, rect.width * rect.height);
                const visibleRatio = (visibleWidth * visibleHeight) / area;
                return {
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    visibleRatio: Math.round(visibleRatio * 1000) / 1000,
                    inViewport: visibleRatio > 0,
                    viewportHeight: viewportHeight,
                    scrollY: Math.round(window.scrollY)
                };
            };

            const scripts = Array.from(document.scripts).map((script) => ({
                src: script.src || "",
                id: script.id || "",
                type: script.type || "",
                async: !!script.async,
                defer: !!script.defer
            }));

            const iframes = Array.from(document.querySelectorAll("iframe")).map((frame) => ({
                src: frame.src || "",
                id: frame.id || "",
                ...metric(frame)
            }));

            const containers = Array.from(
                document.querySelectorAll('[id^="container-"], [id*="adsterra"], [class*="adsterra"]')
            ).map((element) => ({
                id: element.id || "",
                tag: element.tagName,
                className: String(element.className || ""),
                childCount: element.childElementCount,
                iframeCount: element.querySelectorAll("iframe").length,
                innerHtmlLength: (element.innerHTML || "").length,
                ...metric(element)
            }));

            const nativeElement = nativeId ? document.getElementById(nativeId) : null;
            const nativeContainer = nativeElement
                ? {
                    present: true,
                    id: nativeElement.id,
                    childCount: nativeElement.childElementCount,
                    iframeCount: nativeElement.querySelectorAll("iframe").length,
                    innerHtmlLength: (nativeElement.innerHTML || "").length,
                    ...metric(nativeElement)
                }
                : { present: false, id: nativeId || "" };

            const resources = performance
                .getEntriesByType("resource")
                .filter((entry) => entry.name && entry.name.includes("bauval.org"))
                .map((entry) => ({
                    name: entry.name,
                    initiatorType: entry.initiatorType,
                    duration: Math.round(entry.duration),
                    transferSize: entry.transferSize,
                    responseEnd: Math.round(entry.responseEnd)
                }));

            return {
                url: location.href,
                title: document.title,
                readyState: document.readyState,
                bodyTextLength: (document.body && document.body.innerText || "").length,
                scripts: scripts,
                iframes: iframes,
                containers: containers,
                nativeContainer: nativeContainer,
                resources: resources
            };
        }""",
        native_id,
    )


def _normalize_dom(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": raw.get("url", ""),
        "title": raw.get("title", ""),
        "ready_state": raw.get("readyState", ""),
        "body_text_length": raw.get("bodyTextLength", 0),
        "scripts": raw.get("scripts") or [],
        "iframes": raw.get("iframes") or [],
        "containers": raw.get("containers") or [],
        "native_container": raw.get("nativeContainer") or {"present": False},
        "resources": raw.get("resources") or [],
    }


def _native_rendered(container: Dict[str, Any]) -> bool:
    return bool(
        container.get("present")
        and container.get("height", 0) >= 20
        and (
            container.get("childCount", 0) > 0
            or container.get("iframeCount", 0) > 0
            or container.get("innerHtmlLength", 0) > 100
        )
    )


def _scroll_to_ad_slot(page: Page, config: Dict[str, Any]) -> None:
    native_id = config.get("native_container_id", "")
    try:
        page.evaluate(
            """(nativeId) => {
                const element = nativeId ? document.getElementById(nativeId) : null;
                if (!element) {
                    window.scrollTo(0, document.body.scrollHeight);
                    return;
                }
                element.scrollIntoView({ block: "center", behavior: "instant" });
            }""",
            native_id,
        )
        page.wait_for_timeout(1200)
    except Exception:
        pass


def _wait_for_ad_render(
    page: Page,
    config: Dict[str, Any],
    expected_url: str = "",
) -> Dict[str, Any]:
    deadline = time.time() + float(config.get("ad_wait_seconds", 12.0))
    snapshot = _normalize_dom(_collect_dom_snapshot(page, config))

    while time.time() < deadline:
        if expected_url and not same_host(snapshot.get("url", ""), expected_url):
            break
        if _native_rendered(snapshot.get("native_container") or {}):
            break
        time.sleep(0.5)
        snapshot = _normalize_dom(_collect_dom_snapshot(page, config))

    return snapshot


def _safe_screenshot(page: Page, report_dir: str, worker_id: int) -> Optional[str]:
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = Path(report_dir) / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"session_{stamp}_w{worker_id}.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def run_qa_session(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    sticky_proxy_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Run one capped, verification-only visit to the configured page.

    Args:
        sticky_proxy_data: If provided, use this proxy for the entire session
            without acquiring/releasing. The proxy stays permanently assigned
            to this worker.
    """
    if stop_event and stop_event.is_set():
        return None
    if budget.is_exhausted() or not budget.has_capacity():
        return None

    tag = f"[W{worker_id}]"
    caller_id = f"adsterra_qa_worker_{worker_id}"
    target_url = config.get("target_url", "https://article.riztama.my.id/")
    report_dir = config.get("report_dir", str(DEFAULT_REPORT_DIR))

    if sticky_proxy_data:
        # Sticky proxy mode: use the pre-assigned proxy directly.
        proxy_data = sticky_proxy_data
        is_sticky = True
    else:
        if event_callback:
            event_callback(
                "status_update",
                {"worker_id": worker_id, "status": "Acquiring proxy..."},
            )
        proxy_data = proxy_manager.acquire_proxy(
            caller_id=caller_id, exclusive=True, verify_alive=True
        )
        is_sticky = False

    if not proxy_data:
        emit_log(
            "No healthy proxy available. Waiting for the pool.",
            tag=tag,
            style="yellow",
            event_callback=event_callback,
            worker_id=worker_id,
        )
        if event_callback:
            event_callback(
                "status_update",
                {"worker_id": worker_id, "status": "Waiting for proxy..."},
            )
        time.sleep(3.0)
        return None

    proxy_id = proxy_data.get("id") or ""
    ip = proxy_data.get("ip_detected") or proxy_data.get("host") or "unknown"
    country = country_label(proxy_data.get("country"))
    proxy_info = {
        "id": proxy_id,
        "ip": ip,
        "country": country,
        "connection_type": proxy_data.get("connection_type"),
    }

    if not is_sticky:
        if not budget.can_use_proxy(proxy_id):
            proxy_manager.release_proxy(proxy_id, caller_id=caller_id)
            emit_log(
                f"Proxy {proxy_id} already covered; rotating to the next one.",
                tag=tag,
                style="dim",
                event_callback=event_callback,
                worker_id=worker_id,
            )
            time.sleep(2.0)
            return None
    else:
        # Emit proxy_assigned so the TUI can display IP even for sticky mode
        if event_callback:
            event_callback(
                "proxy_assigned",
                {
                    "worker_id": worker_id,
                    "proxy_id": proxy_id,
                    "ip": ip,
                    "country": country,
                    "status": f"Proxy: {ip} ({country})",
                },
            )

    if not budget.reserve():
        if not is_sticky:
            proxy_manager.release_proxy(proxy_id, caller_id=caller_id)
        return None

    if not is_sticky:
        budget.mark_proxy(proxy_id)
    if event_callback:
        # For non-sticky mode, emit proxy_assigned here (sticky already did it above)
        if not is_sticky:
            event_callback(
                "proxy_assigned",
                {
                    "worker_id": worker_id,
                    "proxy_id": proxy_id,
                    "ip": ip,
                    "country": country,
                    "status": f"Proxy: {ip} ({country})",
                },
            )
        event_callback(
            "status_update",
            {"worker_id": worker_id, "status": "Launching Camoufox..."},
        )

    started_ts = time.time()
    started_at = utc_now_iso()
    result: Dict[str, Any] = {
        "mode": "ad-render-qa",
        "worker_id": worker_id,
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "target_url": target_url,
        "proxy": proxy_info,
        "status": "FAIL",
        "score": 0,
        "checks": {},
        "labels": {},
        "issues": [],
        "evidence": {},
        "screenshot": None,
        "report_path": None,
    }

    page: Optional[Page] = None
    report_written = False
    proxy_error_msg: Optional[str] = None

    try:
        with create_camoufox_session(
            proxy_data=proxy_data,
            headless=bool(config.get("headless", True)),
            humanize=bool(config.get("humanize", True)),
            allow_ads=True,
        ) as browser:
            page = browser.new_page(viewport=get_random_viewport())
            page.set_default_timeout(45000)

            verifier_result: Optional[Dict[str, Any]] = None
            if config.get("run_browser_verifier", True):
                if event_callback:
                    event_callback(
                        "status_update",
                        {"worker_id": worker_id, "status": "Running pre-flight verifier..."},
                    )
                try:
                    page.goto("about:blank", wait_until="domcontentloaded", timeout=20000)
                    verifier = BrowserVerifier(
                        strict_mode=bool(config.get("strict_verifier", False))
                    )
                    report = verifier.verify(
                        page,
                        expected_ip=proxy_data.get("ip_detected"),
                        expected_country=proxy_data.get("country"),
                        check_ads=True,
                    )
                    verifier_result = report.to_dict()
                    actual = report.actual_state
                    webgl = (
                        f"{actual.get('webgl_vendor', '')} "
                        f"{actual.get('webgl_renderer', '')}"
                    ).strip() or "Native GPU"
                    if event_callback:
                        event_callback(
                            "verifier_report",
                            {
                                "worker_id": worker_id,
                                "score": report.score,
                                "is_safe": report.is_safe,
                                "webdriver_hidden": actual.get("webdriver") is False,
                                "webrtc_safe": not bool(actual.get("webrtc_leak")),
                                "webgl": webgl[:32],
                                "canvas_audio_ok": bool(
                                    actual.get("canvas_ok") and actual.get("audio_ok")
                                ),
                                "ads_allowed": bool(actual.get("ads_allowed", True)),
                                "adblock_detected": bool(
                                    actual.get("adblock_detected", False)
                                ),
                                "os": actual.get("detected_os", "unknown"),
                            },
                        )
                    emit_log(
                        f"Verifier {report.score}/100 | bot="
                        f"{'hidden' if actual.get('webdriver') is False else 'detected'} | "
                        f"webrtc={'safe' if not actual.get('webrtc_leak') else 'leak'} | "
                        f"adblock={'yes' if actual.get('adblock_detected') else 'no'}",
                        tag=tag,
                        style="green" if report.is_safe else "yellow",
                        event_callback=event_callback,
                        worker_id=worker_id,
                    )
                except Exception as error:
                    emit_log(
                        f"Verifier notice: {str(error)[:120]}",
                        tag=tag,
                        style="dim",
                        event_callback=event_callback,
                        worker_id=worker_id,
                    )

            network: List[Dict[str, Any]] = []
            page_errors: List[str] = []
            console_errors: List[str] = []
            popups: List[str] = []
            navigations: List[str] = []
            blocked_navigations: List[str] = []

            def update_pending(url: str, **changes: Any) -> bool:
                for entry in reversed(network):
                    if entry.get("url") == url and entry.get("pending"):
                        entry.update(changes)
                        entry["pending"] = False
                        return True
                return False

            def on_request(request: Any) -> None:
                try:
                    url = request.url
                    if not is_ad_url(url, config):
                        return
                    network.append(
                        {
                            "url": url,
                            "status": None,
                            "failed": False,
                            "pending": True,
                            "error": None,
                            "resource_type": request.resource_type,
                        }
                    )
                except Exception:
                    pass

            def on_response(response: Any) -> None:
                try:
                    url = response.url
                    if not is_ad_url(url, config):
                        return
                    changes = {
                        "status": response.status,
                        "failed": False,
                        "error": None,
                        "resource_type": response.request.resource_type,
                    }
                    if not update_pending(url, **changes):
                        network.append(
                            {
                                "url": url,
                                "pending": False,
                                **changes,
                            }
                        )
                except Exception:
                    pass

            def on_request_failed(request: Any) -> None:
                try:
                    url = request.url
                    if not is_ad_url(url, config):
                        return
                    changes = {
                        "status": None,
                        "failed": True,
                        "error": str(request.failure or ""),
                        "resource_type": request.resource_type,
                    }
                    if not update_pending(url, **changes):
                        network.append(
                            {
                                "url": url,
                                "pending": False,
                                **changes,
                            }
                        )
                except Exception:
                    pass

            def on_page_error(error: Any) -> None:
                if len(page_errors) < 20:
                    page_errors.append(str(error)[:500])

            def on_console(message: Any) -> None:
                try:
                    if message.type == "error" and len(console_errors) < 50:
                        console_errors.append(str(message.text)[:500])
                except Exception:
                    pass

            def on_frame_navigated(frame: Any) -> None:
                try:
                    if frame.parent_frame is not None:
                        return
                    url = str(frame.url or "")
                    if url.startswith(("http://", "https://")) and url not in navigations:
                        navigations.append(url)
                except Exception:
                    pass

            def on_popup(popup: Any) -> None:
                popup_url = ""
                try:
                    popup_url = str(popup.url or "")
                    if len(popups) < 10:
                        popups.append(popup_url)
                    popup.close()
                except Exception:
                    pass
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                if event_callback:
                    event_callback(
                        "popup_closed",
                        {"worker_id": worker_id, "url": popup_url},
                    )

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfailed", on_request_failed)
            page.on("pageerror", on_page_error)
            page.on("console", on_console)
            page.on("framenavigated", on_frame_navigated)
            page.on("popup", on_popup)

            if event_callback:
                event_callback(
                    "session_started",
                    {"worker_id": worker_id, "url": target_url, "status": "Loading page..."},
                )
                event_callback(
                    "status_update",
                    {"worker_id": worker_id, "status": "Loading target page..."},
                )

            wait_seconds = float(config.get("wait_after_load_seconds", 5.0))
            target_host = (urlparse(target_url).hostname or "").lower()
            recovery_attempts = 0

            def main_frame_guard(route: Any, request: Any) -> None:
                try:
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        host = (urlparse(request.url).hostname or "").lower()
                        if host and target_host and host != target_host:
                            blocked_navigations.append(request.url)
                            route.abort()
                            return
                except Exception:
                    pass
                try:
                    route.continue_()
                except Exception:
                    pass

            page.route("**/*", main_frame_guard)

            def on_target() -> bool:
                try:
                    current = (urlparse(page.url).hostname or "").lower()
                    return bool(target_host and current == target_host)
                except Exception:
                    return False

            def load_target() -> None:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

            def recover_target(reason: str) -> bool:
                nonlocal recovery_attempts
                if recovery_attempts >= 1:
                    return False
                recovery_attempts += 1
                emit_log(
                    f"Main tab left the target after {reason}; recovering once.",
                    tag=tag,
                    style="yellow",
                    event_callback=event_callback,
                    worker_id=worker_id,
                )
                if event_callback:
                    event_callback(
                        "status_update",
                        {"worker_id": worker_id, "status": "Restoring target page..."},
                    )
                try:
                    load_target()
                    return on_target()
                except Exception as error:
                    emit_log(
                        f"Could not restore target page: {str(error)[:120]}",
                        tag=tag,
                        style="red",
                        event_callback=event_callback,
                        worker_id=worker_id,
                    )
                    return False

            def scroll_to_ad_slot() -> None:
                if not config.get("scroll_to_ad", True):
                    return
                if event_callback:
                    event_callback(
                        "status_update",
                        {"worker_id": worker_id, "status": "Scrolling to ad slot..."},
                    )
                _scroll_to_ad_slot(page, config)

            load_target()

            if not on_target():
                recover_target("initial navigation")

            scroll_to_ad_slot()

            if event_callback:
                event_callback(
                    "status_update",
                    {"worker_id": worker_id, "status": "Inspecting Adsterra units..."},
                )

            dom = _wait_for_ad_render(page, config, target_url)

            if not on_target() and recover_target("an ad redirect"):
                scroll_to_ad_slot()
                dom = _wait_for_ad_render(page, config, target_url)

            summary = summarize_ad_checks(
                dom=dom,
                network=network,
                page_errors=page_errors,
                console_errors=console_errors,
                popups=popups,
                verifier=verifier_result,
                config=config,
                navigations=navigations,
                blocked_navigations=blocked_navigations,
            )
            result.update(summary)

            if event_callback:
                event_callback(
                    "ad_check",
                    {
                        "worker_id": worker_id,
                        "status": result["status"],
                        "score": result["score"],
                        "checks": result["checks"],
                        "issues": result["issues"],
                    },
                )

            if config.get("screenshot", True):
                screenshot = _safe_screenshot(page, report_dir, worker_id)
                result["screenshot"] = screenshot
                if screenshot and event_callback:
                    event_callback(
                        "screenshot_saved",
                        {"worker_id": worker_id, "path": screenshot},
                    )

    except Exception as error:
        proxy_error_msg = str(error)
        result["status"] = "FAIL"
        result["score"] = 0
        result["issues"] = [f"Session error: {proxy_error_msg[:300]}"]
        emit_log(
            f"Session error: {proxy_error_msg[:120]}",
            tag=tag,
            style="red",
            event_callback=event_callback,
            worker_id=worker_id,
        )
        if page is not None and config.get("screenshot", True):
            result["screenshot"] = _safe_screenshot(page, report_dir, worker_id)
    finally:
        result["finished_at"] = utc_now_iso()
        result["duration_seconds"] = round(time.time() - started_ts, 2)

        if not report_written:
            try:
                report_path = write_session_report(report_dir, result)
                result["report_path"] = str(report_path)
                report_written = True
            except Exception as error:
                emit_log(
                    f"Could not write report: {str(error)[:120]}",
                    tag=tag,
                    style="red",
                    event_callback=event_callback,
                    worker_id=worker_id,
                )

        if proxy_id:
            if proxy_error_msg and any(
                key in proxy_error_msg.lower()
                for key in (
                    "proxy",
                    "tunnel",
                    "timeout",
                    "connect",
                    "refused",
                    "reset",
                )
            ):
                proxy_manager.report_failure(
                    proxy_id, error_message=proxy_error_msg, is_proxy_error=True
                )
            # Only release the proxy back to the pool in dynamic (non-sticky) mode.
            # Sticky proxies stay assigned to their worker for the whole run.
            if not is_sticky:
                proxy_manager.release_proxy(proxy_id, caller_id=caller_id)

        budget.record(result["status"])

        if event_callback:
            event_callback(
                "session_completed",
                {
                    "worker_id": worker_id,
                    "status": result["status"],
                    "score": result["score"],
                    "issues": result["issues"],
                    "report_path": result["report_path"],
                    "screenshot": result["screenshot"],
                    "checks": result["checks"],
                    "target_url": target_url,
                },
            )

    return result


def worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    tag = f"[W{worker_id}]"
    emit_log(
        f"QA worker {worker_id} started.",
        tag=tag,
        style="green",
        event_callback=event_callback,
        worker_id=worker_id,
    )

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break

        try:
            run_qa_session(
                worker_id=worker_id,
                config=config,
                proxy_manager=proxy_manager,
                budget=budget,
                event_callback=event_callback,
                stop_event=stop_event,
            )
        except Exception as error:
            emit_log(
                f"Worker error: {str(error)[:160]}",
                tag=tag,
                style="red",
                event_callback=event_callback,
                worker_id=worker_id,
            )

        if stop_event and stop_event.is_set():
            break
        if budget.is_exhausted():
            break

        stats = proxy_manager.get_stats()
        if is_proxy_pool_exhausted(stats):
            budget.stop()
            emit_log(
                "Proxy pool exhausted. Stopping.",
                tag=tag,
                style="yellow",
                event_callback=event_callback,
                worker_id=worker_id,
            )
            break
        if budget.covered_all(stats.get("total", 0)):
            budget.stop()
            emit_log(
                "Every proxy has reached its QA visit cap. Stopping.",
                tag=tag,
                style="yellow",
                event_callback=event_callback,
                worker_id=worker_id,
            )
            break

        cooldown = config.get("session_cooldown_seconds", {}) or {}
        delay = random.uniform(
            float(cooldown.get("min", 5.0)), float(cooldown.get("max", 10.0))
        )
        if event_callback:
            event_callback(
                "status_update",
                {"worker_id": worker_id, "status": f"Cooldown ({delay:.1f}s)..."},
            )
        time.sleep(delay)

    emit_log(
        f"QA worker {worker_id} stopped.",
        tag=tag,
        style="dim",
        event_callback=event_callback,
        worker_id=worker_id,
    )


def worker_thread_loop_sticky(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    sticky_proxy_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Worker loop with a permanently-assigned (sticky) proxy.

    The proxy is never released back to the pool. Each iteration uses the
    same proxy so that workers always keep their unique IP assignment.
    """
    tag = f"[W{worker_id}]"
    ip = (sticky_proxy_data or {}).get("ip_detected") or (sticky_proxy_data or {}).get("host", "?")
    country = country_label((sticky_proxy_data or {}).get("country"))

    emit_log(
        f"QA worker {worker_id} started (sticky proxy {ip} / {country}).",
        tag=tag,
        style="green",
        event_callback=event_callback,
        worker_id=worker_id,
    )

    # Push initial proxy info to TUI immediately
    if event_callback and sticky_proxy_data:
        event_callback(
            "proxy_assigned",
            {
                "worker_id": worker_id,
                "proxy_id": sticky_proxy_data.get("id", ""),
                "ip": ip,
                "country": country,
                "status": f"Proxy: {ip} ({country})",
            },
        )

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break

        try:
            run_qa_session(
                worker_id=worker_id,
                config=config,
                proxy_manager=proxy_manager,
                budget=budget,
                event_callback=event_callback,
                stop_event=stop_event,
                sticky_proxy_data=sticky_proxy_data,
            )
        except Exception as error:
            emit_log(
                f"Worker error: {str(error)[:160]}",
                tag=tag,
                style="red",
                event_callback=event_callback,
                worker_id=worker_id,
            )

        if stop_event and stop_event.is_set():
            break
        if budget.is_exhausted():
            break

        # In sticky mode we do NOT check covered_all — the proxy is always ours.
        # Only stop if proxy pool went totally dead.
        stats = proxy_manager.get_stats()
        if is_proxy_pool_exhausted(stats):
            budget.stop()
            emit_log(
                "Proxy pool exhausted. Stopping.",
                tag=tag,
                style="yellow",
                event_callback=event_callback,
                worker_id=worker_id,
            )
            break

        cooldown = config.get("session_cooldown_seconds", {}) or {}
        delay = random.uniform(
            float(cooldown.get("min", 5.0)), float(cooldown.get("max", 10.0))
        )
        if event_callback:
            event_callback(
                "status_update",
                {"worker_id": worker_id, "status": f"Cooldown ({delay:.1f}s)..."},
            )
        # Sleep in small slices so Ctrl+C is responsive
        sleep_end = time.time() + delay
        while time.time() < sleep_end and not (stop_event and stop_event.is_set()):
            time.sleep(0.3)

    emit_log(
        f"QA worker {worker_id} stopped.",
        tag=tag,
        style="dim",
        event_callback=event_callback,
        worker_id=worker_id,
    )
