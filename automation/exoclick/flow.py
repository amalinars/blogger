#!/usr/bin/env python3
"""
automation.exoclick.flow
Workflow automasi khusus ExoClick Ads:
- Memuat website target dengan parameter ?ad_network=exoclick.
- Membuka halaman dan memicu format ExoClick: Popunder (6066234), In-Page Push (6066246),
  Native Banner (6066238), Display Banner (6066244), Sticky Banner (6066266), dan Outstream Video (6066272).
- Interaksi ultra-humanized: kurva Bézier, micro-tremor, variasi kecepatan, scroll naik-turun, dan klik acak.
- Penanganan multi-tab popunder: mendeteksi tab baru yang terbuka, dwell natural, lalu menutup tabnya.
- Terintegrasi penuh dengan GUI dashboard, event stepper, budget session, dan ProxyManager target usage.
"""

import json
import os
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from camoufox.sync_api import Camoufox

from automation.adsterra.engine import build_camoufox_kwargs, resolve_geo_profile
from automation.adsterra.qa import SessionBudget, country_label
from automation.browser_verifier import BrowserVerifier
from automation.monetag.humanizer import human_click, human_move, human_scroll, human_wander
from core.proxy_manager import ProxyManager


def _emit(callback: Optional[Callable[[str, Dict[str, Any]], None]], event_type: str, **kwargs: Any) -> None:
    if callback:
        try:
            callback(event_type, kwargs)
        except Exception:
            pass


def run_exoclick_session(
    worker_id: int,
    proxy_data: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan 1 sesi automasi ExoClick secara utuh dan humanized.
    """
    raw_target_url = config.get("target_url", "https://article.riztama.my.id/")
    parsed = urlparse(raw_target_url)
    qs = parse_qs(parsed.query)
    qs["ad_network"] = ["exoclick"]
    target_url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    enable_verifier = bool(config.get("run_browser_verifier", True))

    popunder_dwell_cfg = config.get("dwell_popup_seconds", {}) or {"min": 10.0, "max": 20.0}
    dwell_page_cfg = config.get("dwell_page_seconds", {}) or {"min": 6.0, "max": 14.0}

    session_start = time.time()
    popups_opened: List[Any] = []
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

    def step(stage: str, status: str) -> None:
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage=stage,
            status=status,
        )

    log(f"🚀 Memulai sesi ExoClick via proxy {proxy_label}...", "bold cyan")
    step("INITIALIZE", f"Mempersiapkan browser ({proxy_label})")

    # Format profil Camoufox
    geo = resolve_geo_profile(proxy_data or {})
    camoufox_opts = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize_enabled,
        allow_ads=True,
    )

    with Camoufox(**camoufox_opts) as browser:
        context = browser.new_context()

        # Tangkap popunder / tab baru yang dibuka skrip ExoClick
        def on_page_opened(new_page: Any) -> None:
            popups_opened.append(new_page)
            try:
                new_url = new_page.url
                log(f"🎯 Tab Popunder ExoClick terdeteksi: {new_url[:60]}...", "cyan")
            except Exception:
                pass

        context.on("page", on_page_opened)
        page = context.new_page()

        # Step 1: Opsional Verifikasi Browser
        if enable_verifier:
            step("VERIFIKASI IP", "Memeriksa kebocoran WebRTC & fingerprint...")
            try:
                verifier = BrowserVerifier(page=page)
                v_res = verifier.verify(expected_country=geo.get("country"))
                if v_res.get("webrtc_leaked"):
                    log("⚠️ Peringatan: WebRTC terdeteksi leak", "yellow")
                else:
                    log("🛡️ Browser verifier: Bersih dari kebocoran", "green")
            except Exception as e_v:
                log(f"Verifier info: {e_v}", "dim")

        # Step 2: Buka Website Target (dengan ?ad_network=exoclick)
        step("MEMUAT SITUS", f"Navigasi ke {target_url[:55]}...")
        log(f"🌐 Membuka website: {target_url}", "white")

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(2.0)
        except Exception as e_nav:
            log(f"⚠️ Gagal navigasi primer: {e_nav}, mencoba reload...", "yellow")
            try:
                page.reload(timeout=30000)
            except Exception:
                pass

        # Step 3: Humanized interaction pada halaman utama untuk memicu tag iklan ExoClick
        step("MEMICU IKLAN EXOCLICK", "Interaksi humanized, banner & popunder trigger...")
        dwell_page = random.uniform(
            dwell_page_cfg.get("min", 6.0),
            dwell_page_cfg.get("max", 14.0),
        )

        page_end_time = time.time() + dwell_page
        click_attempts = 0
        max_clicks = random.randint(
            config.get("popunder_click_count", {}).get("min", 1),
            config.get("popunder_click_count", {}).get("max", 2),
        )

        while time.time() < page_end_time and not page.is_closed():
            if humanize_enabled:
                # Gerakan kursor santai kurva Bézier
                human_wander(page, duration=random.uniform(1.0, 2.0))
                # Scrolling alami naik-turun (memicu viewability banner & native widget)
                human_scroll(page, delta_y=random.randint(180, 420))

            # Lakukan klik acak pada area konten untuk memicu Popunder ExoClick
            if click_attempts < max_clicks and random.random() < 0.70:
                try:
                    vp = page.viewport_size or {"width": 1280, "height": 800}
                    click_x = random.randint(100, vp["width"] - 100)
                    click_y = random.randint(180, vp["height"] - 180)
                    human_click(page, click_x, click_y)
                    click_attempts += 1
                    log(f"👆 Klik pemicu popunder ke-{click_attempts} di ({click_x}, {click_y})", "dim")
                    time.sleep(1.0)
                except Exception:
                    pass

            time.sleep(random.uniform(0.6, 1.4))

        # Step 4: Menangani Popunder yang terbuka
        if popups_opened:
            step("DWELL POPUNDER", f"Memproses {len(popups_opened)} tab iklan ExoClick")
            for idx, p_page in enumerate(list(popups_opened), start=1):
                try:
                    if p_page.is_closed():
                        continue
                    p_url = p_page.url or ""
                    log(f"📄 Menjelajahi tab popunder #{idx} ({p_url[:50]}...)", "cyan")

                    pop_dwell = random.uniform(
                        popunder_dwell_cfg.get("min", 10.0),
                        popunder_dwell_cfg.get("max", 20.0),
                    )
                    end_pop = time.time() + pop_dwell

                    while time.time() < end_pop and not p_page.is_closed():
                        if humanize_enabled:
                            human_wander(p_page, duration=random.uniform(1.0, 2.0))
                            human_scroll(p_page, delta_y=random.randint(120, 320))
                        time.sleep(1.0)

                    popunders_processed += 1
                    try:
                        p_page.close()
                    except Exception:
                        pass
                except Exception as e_pop:
                    log(f"Tab popunder notice: {e_pop}", "dim")

        step("SELESAI", "Sesi ExoClick selesai sukses")
        duration = round(time.time() - session_start, 1)
        log(f"✅ Sesi ExoClick tuntas ({duration}s). Popunder diproses: {popunders_processed}", "bold green")

        _emit(
            event_callback,
            "session_completed",
            worker_id=worker_id,
            status="PASS",
            duration=duration,
            popunders=popunders_processed,
            direct_links=0,
        )

        return {
            "status": "PASS",
            "duration": duration,
            "popunders_processed": popunders_processed,
        }


def exoclick_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    reset_pool_callback: Optional[Callable[[], None]] = None,
    caller_prefix: str = "exoclick_worker",
) -> None:
    """
    Loop worker thread multi-sesi untuk automasi ExoClick.
    Kompatibel penuh dengan GUI dashboard controller dan status pemakaian proxy.
    """
    def _log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"[W{worker_id}] {msg}",
            style=style,
        )

    _log("Browser ExoClick siap — IP dirotasi tiap sesi.", "green")

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break
        if not budget.reserve():
            break

        target_name = "exoclick"
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
            if budget.unlimited and reset_pool_callback:
                reset_pool_callback()
                _log("Pool IP habis — direset untuk rotasi ulang.", "cyan")
                time.sleep(1.0)
                continue

            _log("Menunggu IP yang tersedia / selesai cooldown ExoClick...", "dim")
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
            target_network="🎯 ExoClick",
            timezone=expected_geo.get("timezone"),
            locale=expected_geo.get("locale"),
        )

        try:
            res = run_exoclick_session(
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
            _log(f"❌ Error sesi ExoClick: {e_run}", "bold red")
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
