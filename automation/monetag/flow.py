#!/usr/bin/env python3
"""
automation.monetag.flow
Workflow automasi khusus Monetag:
- Tanpa menunggu flow shortlink langkah 1-3.
- Fokus memicu tayangan iklan: MultiTag (Popunder/OnClick), In-Page Push, Vignette.
- Interaksi humanize murni pada tab Popunder & Direct Link (dwell time + natural scroll/mouse wander).
- Kompatibel penuh dengan GUI dashboard (event stepper & reporting).
"""

import os
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from automation.adsterra.engine import build_camoufox_kwargs, resolve_geo_profile
from automation.adsterra.qa import SessionBudget, country_label
from automation.browser_verifier import BrowserVerifier
from automation.monetag.humanizer import human_click, human_move, human_scroll, human_wander
from core.proxy_manager import ProxyManager


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _emit(callback: Optional[Callable[[str, Dict[str, Any]], None]], event_type: str, **kwargs: Any) -> None:
    if callback:
        try:
            callback(event_type, kwargs)
        except Exception:
            pass


def run_monetag_session(
    worker_id: int,
    proxy_data: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan 1 sesi automasi Monetag secara utuh dan humanized.
    """
    target_url = config.get("target_url", "https://article.riztama.my.id/")
    direct_link_url = config.get("direct_link_url", "https://uplcm.com/4/12124796")
    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    enable_verifier = bool(config.get("run_browser_verifier", True))

    popunder_dwell_cfg = config.get("dwell_popup_seconds", {}) or {"min": 10.0, "max": 18.0}
    direct_link_dwell_cfg = config.get("dwell_direct_link_seconds", {}) or {"min": 12.0, "max": 24.0}
    direct_link_chance = float(config.get("direct_link_chance", 0.50))

    session_start = time.time()
    popups_opened: List[Any] = []
    direct_links_processed = 0
    popunders_processed = 0

    proxy_info = proxy_data or {}
    proxy_label = (
        f"{proxy_info.get('host')}:{proxy_info.get('port')}"
        if proxy_info.get("host")
        else "Direct/Local"
    )

    def log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"[W{worker_id}] {msg}",
            style=style,
        )

    log(f"Memulai sesi Monetag dengan proxy: {proxy_label}", "cyan")

    camoufox_kwargs = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize_enabled,
        allow_ads=True,
    )

    with Camoufox(**camoufox_kwargs) as browser:
        context = browser.new_context(
            viewport=camoufox_kwargs.get("viewport", {"width": 1366, "height": 768}),
            user_agent=camoufox_kwargs.get("user_agent"),
            locale=camoufox_kwargs.get("locale", "en-US"),
            timezone_id=camoufox_kwargs.get("timezone_id", "America/New_York"),
        )
        page = context.new_page()

        # Listener deteksi pembukaan popup / tab iklan baru
        def on_popup(popup_page: Any) -> None:
            popups_opened.append(popup_page)
            p_url = str(popup_page.url or "")
            log(f"📑 Tab iklan baru terdeteksi: {p_url[:65]}...", "magenta")
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="📑 Tab Iklan",
                status=f"Popunder terbuka: {_host(p_url)}",
            )

        page.on("popup", on_popup)

        # ── Pre-flight Browser Audit (Optional Verifier) ──
        if enable_verifier:
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="🛡️ Audit IP",
                status="Cek IP, WebRTC & stealth...",
            )
            try:
                page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
                verifier = BrowserVerifier(strict_mode=False)
                report = verifier.verify(
                    page,
                    expected_ip=proxy_info.get("ip_detected"),
                    expected_country=proxy_info.get("country"),
                    check_ads=True,
                )
                actual = report.actual_state
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
                    webrtc_leak=bool(actual.get("webrtc_leak")),
                    ads_allowed=bool(actual.get("ads_allowed", True)),
                )
            except Exception as e_ver:
                log(f"Catatan verifier: {str(e_ver)[:90]}", "dim")

        # ── 1. Kunjungi Halaman Target (MultiTag Web) ──
        _emit(event_callback, "session_started", worker_id=worker_id)
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="🌐 MultiTag Web",
            status="Membuka web Monetag...",
        )
        log(f"Membuka halaman target: {target_url}", "bold yellow")
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            log(f"Peringatan loading ({e}), melanjutkan interaksi...", "dim")

        # Jeda natural membaca halaman awal (2.5 - 4.5 dtk)
        time.sleep(random.uniform(2.5, 4.5))

        # ── 2. Perilaku Membaca Natural (Scroll & Mouse Wander) ──
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="📜 Natural Wander",
            status="Scroll santai & inisialisasi tag...",
        )
        log("Membaca konten & scrolling santai untuk memuat MultiTag / In-Page Push...", "cyan")
        vp = page.viewport_size or {"width": 1366, "height": 768}
        human_wander(page, duration_seconds=random.uniform(3.5, 5.5))
        human_scroll(page, scroll_amount=random.randint(220, 420))

        # ── 3. Memicu Popunder MultiTag Monetag (Humanized Click) ──
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="🎯 Klik Interaktif",
            status="Trigger OnClick Popunder...",
        )
        click_attempts = random.randint(1, 3)
        log(f"Melakukan {click_attempts}x klik interaksi natural untuk memicu Popunder Monetag...", "bold yellow")

        for i in range(click_attempts):
            continue_btn = page.locator("#step-0 button, main h1, main p").first
            btn_box = None
            try:
                if continue_btn.is_visible(timeout=1500):
                    btn_box = continue_btn.bounding_box()
            except Exception:
                pass

            if btn_box:
                target_pos = (
                    btn_box["x"] + btn_box["width"] * random.uniform(0.3, 0.7),
                    btn_box["y"] + btn_box["height"] * random.uniform(0.3, 0.7),
                )
            else:
                target_pos = (
                    random.uniform(vp["width"] * 0.3, vp["width"] * 0.7),
                    random.uniform(vp["height"] * 0.35, vp["height"] * 0.65),
                )

            human_click(page, target_pos)
            time.sleep(random.uniform(1.2, 2.2))

            if popups_opened:
                break

        # ── 4. Proses Tab Popunder / Iklan Terbuka (Dwell) ──
        if popups_opened:
            for idx, popup in enumerate(list(popups_opened)):
                try:
                    popup.bring_to_front()
                    time.sleep(1.0)
                    popup_url = str(popup.url or "")
                    dwell_time = random.uniform(
                        float(popunder_dwell_cfg.get("min", 10.0)),
                        float(popunder_dwell_cfg.get("max", 18.0)),
                    )
                    _emit(
                        event_callback,
                        "stepper_update",
                        worker_id=worker_id,
                        stage="📑 Popunder Dwell",
                        status=f"Dwell tab iklan ({dwell_time:.1f}s)...",
                    )
                    log(f"📑 Melakukan dwell di tab iklan ({idx+1}/{len(popups_opened)}): {_host(popup_url)} ({dwell_time:.1f}s)", "magenta")
                    human_wander(popup, duration_seconds=dwell_time)
                    log(f"✅ Selesai dwell iklan. Menutup tab iklan...", "green")
                    popup.close()
                    popunders_processed += 1
                except Exception as ex:
                    log(f"Peringatan proses popup: {ex}", "dim")
        else:
            log("ℹ️ Popunder tidak terbuka pada sesi ini (mungkin frequency capping).", "dim")

        # Kembali ke halaman utama
        try:
            page.bring_to_front()
            time.sleep(0.8)
        except Exception:
            pass

        # ── 5. Cek & Tutup Overlay Vignette Banner (Jika Muncul) ──
        try:
            vignette_close = page.locator(
                "button[aria-label*='close' i], .vignette-close, [id*='close' i], svg.close-icon"
            ).first
            if vignette_close.is_visible(timeout=1800):
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="🖼️ Vignette Ad",
                    status="Dwell vignette overlay...",
                )
                log("🖼️ Vignette overlay terdeteksi. Dwell sesaat lalu klik tutup...", "yellow")
                time.sleep(random.uniform(2.5, 4.0))
                human_click(page, vignette_close)
        except Exception:
            pass

        # ── 6. Direct Link Monetag (Cuan Tertinggi) ──
        if random.random() < direct_link_chance and direct_link_url:
            direct_dwell = random.uniform(
                float(direct_link_dwell_cfg.get("min", 12.0)),
                float(direct_link_dwell_cfg.get("max", 24.0)),
            )
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="🔗 Direct Link Dwell",
                status=f"Dwell Smartlink ({direct_dwell:.1f}s)...",
            )
            log(f"🔗 Membuka Direct Link Monetag di tab baru & dwell {direct_dwell:.1f}s...", "cyan")
            direct_page = None
            try:
                # Buka di tab baru di dalam jendela browser yang sama (bukan new window browser)
                try:
                    with context.expect_page(timeout=10000) as new_page_info:
                        page.evaluate(
                            """(url) => {
                                const a = document.createElement('a');
                                a.href = url;
                                a.target = '_blank';
                                a.rel = 'noopener noreferrer';
                                document.body.appendChild(a);
                                a.click();
                                a.remove();
                            }""",
                            direct_link_url,
                        )
                    direct_page = new_page_info.value
                except Exception:
                    # Fallback jika pembuatan tab gagal
                    direct_page = context.new_page()
                    direct_page.goto(direct_link_url, wait_until="domcontentloaded", timeout=45000)

                if direct_page:
                    try:
                        direct_page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    direct_page.bring_to_front()
                    human_wander(direct_page, duration_seconds=direct_dwell)
                    try:
                        direct_page.close()
                    except Exception:
                        pass
                    # Fokus kembali ke tab utama
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass

                direct_links_processed += 1
                log("✅ Direct Link dwell selesai dengan sukses!", "bold green")
            except Exception as e_dl:
                log(f"Peringatan proses Direct Link: {e_dl}", "dim")
        elif direct_link_url:
            log(f"ℹ️ Sesi ini fokus impresi MultiTag (Direct Link dilewati demi CTR organik ~{int(direct_link_chance * 100)}%).", "dim")

        duration = round(time.time() - session_start, 1)
        log(f"🎉 Sesi Monetag selesai dalam {duration}s! (Popunders: {popunders_processed}, DirectLinks: {direct_links_processed})", "bold green")

        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="✅ LOLOS",
            status=f"Selesai ({duration}s)",
        )
        _emit(event_callback, "session_completed", worker_id=worker_id, status="PASS")

        return {
            "worker_id": worker_id,
            "success": True,
            "duration_seconds": duration,
            "popunders_processed": popunders_processed,
            "direct_links_processed": direct_links_processed,
            "proxy": proxy_label,
        }


def monetag_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    reset_pool_callback: Optional[Callable[[], None]] = None,
) -> None:
    """
    Loop worker multi-sesi untuk Monetag dengan rotasi proxy residensial.
    Kompatibel penuh dengan GUI dashboard orchestration.
    """
    tag = f"[W{worker_id}]"

    def _log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"{tag} {msg}",
            style=style,
        )

    caller_prefix = f"monetag_w{worker_id}"
    _log("Browser Monetag siap — IP dirotasi tiap sesi.", "green")

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break
        if not budget.reserve():
            break

        target_name = "monetag"
        max_uses = int(config.get("max_uses_per_day", 2))
        cooldown_hrs = float(config.get("proxy_cooldown_hours", 6.0))
        caller_id = f"{caller_prefix}_{int(time.time() * 1000)}"

        proxy = proxy_manager.acquire_proxy(
            caller_id=caller_id,
            exclusive=True,
            verify_alive=False,
            target=target_name,
            max_uses_per_day=max_uses,
            cooldown_seconds=cooldown_hrs * 3600,
        )

        if not proxy:
            stats = proxy_manager.get_stats()
            if budget.unlimited and reset_pool_callback:
                reset_pool_callback()
                _log("Pool IP habis — direset untuk rotasi ulang.", "cyan")
                time.sleep(1.0)
                continue

            _log("Menunggu IP yang tersedia / selesai cooldown...", "dim")
            time.sleep(3.0)
            continue

        proxy_id = proxy.get("id") or proxy.get("proxy_url")
        ip = proxy.get("ip_detected") or proxy.get("host", "?")
        country = country_label(proxy.get("country"))
        expected_geo = resolve_geo_profile(proxy)

        # Surfaced to GUI table
        t_usage = proxy_manager.get_target_usage_summary(
            proxy, target=target_name, max_uses_per_day=max_uses, cooldown_seconds=cooldown_hrs * 3600
        )
        _emit(
            event_callback,
            "proxy_assigned",
            worker_id=worker_id,
            proxy_id=proxy_id,
            ip=ip,
            country=country,
            target_usage=t_usage.get("summary_text", "Hit 1/2"),
            hit_count=t_usage.get("current_hit", 1),
            timezone=expected_geo.get("timezone"),
            locale=expected_geo.get("locale"),
        )

        try:
            res = run_monetag_session(
                worker_id=worker_id,
                proxy_data=proxy,
                config=config,
                event_callback=event_callback,
            )
            proxy_manager.record_target_hit(proxy, target=target_name)
            budget.record("PASS")
            if proxy_id:
                budget.mark_proxy(proxy_id)
        except Exception as e_run:
            _log(f"❌ Error sesi Monetag: {e_run}", "bold red")
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="❌ GAGAL",
                status=str(e_run)[:40],
            )
            _emit(event_callback, "session_completed", worker_id=worker_id, status="FAIL")
            budget.record("FAIL")
            if proxy_id:
                budget.mark_proxy(proxy_id)
        finally:
            proxy_manager.release_proxy(proxy)

        # Jeda antar-sesi worker
        time.sleep(random.uniform(2.5, 5.0))
