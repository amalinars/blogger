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


def scroll_to_page_bottom(
    page: Any,
    dwell_at_bottom: float = 4.0,
    humanize: bool = True,
    click_callback: Optional[Callable[[], None]] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> None:
    """
    Scroll natural dari posisi atas hingga MENTOK ke viewport paling bawah (footer).
    Memastikan seluruh widget iklan ExoClick (Native Recommendation Banner 6066238,
    Sticky Banner 6066266, Display Banner 6066244, dan Outstream Video 6066272)
    berada dalam viewport dan mentrigger impresi ke server iklan.
    """
    try:
        max_steps = 45
        last_y = -1
        stuck_count = 0

        for step_i in range(1, max_steps + 1):
            if page.is_closed():
                break

            # Ukur posisi scroll dan tinggi total halaman secara realtime
            metrics = page.evaluate("""() => {
                const doc = document.documentElement;
                const body = document.body;
                const scrollY = window.scrollY || window.pageYOffset || 0;
                const scrollHeight = Math.max(doc.scrollHeight, body.scrollHeight, doc.offsetHeight, body.offsetHeight, 1000);
                const innerH = window.innerHeight || doc.clientHeight || 800;
                const atBottom = (scrollY + innerH) >= (scrollHeight - 40);
                return { scrollY, scrollHeight, innerH, atBottom };
            }""")

            cur_y = metrics.get("scrollY", 0)
            total_h = metrics.get("scrollHeight", 1000)
            at_bottom = metrics.get("atBottom", False)

            if at_bottom:
                if log_fn:
                    log_fn(f"📍 Posisi scroll mencapai viewport terbawah (~{int(cur_y + metrics.get('innerH', 800))}px / {int(total_h)}px).", "cyan")
                # Berikan wheel scroll tambahan agar benar-benar menyentuh batas paling bawah
                try:
                    page.mouse.wheel(0, 350)
                except Exception:
                    pass
                break

            if abs(cur_y - last_y) < 15:
                stuck_count += 1
                if stuck_count >= 3:
                    if log_fn:
                        log_fn(f"📍 Batas halaman terbawah tercapai ({int(cur_y)}px).", "cyan")
                    break
            else:
                stuck_count = 0

            last_y = cur_y

            # Scroll turun bertahap menyerupai membaca teks (chunk 280 - 520px)
            chunk = random.randint(280, 520)
            if humanize:
                human_scroll(page, scroll_amount=chunk, pause_range=(0.15, 0.35))
                # 35% kemungkinan gerakkan mouse santai
                if random.random() < 0.35:
                    human_wander(page, duration_seconds=random.uniform(0.6, 1.2))
            else:
                try:
                    page.mouse.wheel(0, chunk)
                except Exception:
                    break
                time.sleep(0.3)

            # Peluang klik interaktif saat sedang scrolling
            if click_callback and random.random() < 0.30:
                click_callback()

            time.sleep(random.uniform(0.3, 0.7))

        # Dwell di bagian bawah (area Native Banner widget dan Sticky Banner)
        if not page.is_closed():
            if humanize:
                human_wander(page, duration_seconds=random.uniform(1.2, 2.5))
            time.sleep(dwell_at_bottom)

            # Scroll naik sedikit seolah membaca widget artikel rekomendasi
            if humanize and random.random() < 0.75:
                human_scroll(page, scroll_amount=-random.randint(180, 350), pause_range=(0.2, 0.4))
                human_wander(page, duration_seconds=random.uniform(1.0, 1.8))
                # Lalu turun lagi mentok
                human_scroll(page, scroll_amount=random.randint(220, 380), pause_range=(0.15, 0.3))
                time.sleep(1.0)

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
                verifier = BrowserVerifier(strict_mode=False)
                # Proxy residensial FloppyData bersifat rotating (IP keluar berubah dinamis per sesi).
                # Jangan hukum skor (-40) jika IP keluar berganti, asalkan tidak leak WebRTC/bot.
                is_rotating = (
                    (proxy_data or {}).get("connection_type") == "residential"
                    or "floppydata" in str((proxy_data or {}).get("host", "")).lower()
                )
                exp_ip = None if is_rotating else ((proxy_data or {}).get("ip_detected") or (proxy_data or {}).get("host"))
                exp_country = None if is_rotating else (proxy_data or {}).get("country")

                report = verifier.verify(
                    page,
                    expected_ip=exp_ip,
                    expected_country=exp_country,
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
                if actual.get("webrtc_leak"):
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

        # Step 3: Scroll ke bawah sampai MENTOK dan picu seluruh format iklan ExoClick
        step("MEMICU IKLAN EXOCLICK", "Scroll mentok ke bawah & picu Native Banner...")
        log("📜 Membaca artikel & scrolling natural sampai mentok ke footer (Native & Outstream)...", "cyan")

        click_attempts = 0
        max_clicks = random.randint(
            config.get("popunder_click_count", {}).get("min", 1),
            config.get("popunder_click_count", {}).get("max", 2),
        )

        def on_scroll_click():
            nonlocal click_attempts
            if click_attempts < max_clicks and not page.is_closed():
                try:
                    vp = page.viewport_size or {"width": 1280, "height": 800}
                    click_x = random.randint(120, vp["width"] - 120)
                    click_y = random.randint(200, vp["height"] - 200)
                    human_click(page, (click_x, click_y))
                    click_attempts += 1
                    log(f"👆 Klik pemicu popunder ke-{click_attempts} di ({click_x}, {click_y})", "dim")
                    time.sleep(1.0)
                except Exception:
                    pass

        # Scroll bertahap dan pasti sampai mentok paling bawah
        scroll_to_page_bottom(
            page=page,
            dwell_at_bottom=random.uniform(4.0, 7.0),
            humanize=humanize_enabled,
            click_callback=on_scroll_click,
            log_fn=log,
        )

        # Pastikan klik pemicu popunder tereksekusi jika belum sempat terpencet saat scroll
        while click_attempts < max_clicks and not page.is_closed() and not popups_opened:
            on_scroll_click()
            time.sleep(1.0)

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
                            human_wander(p_page, duration_seconds=random.uniform(1.0, 2.0))
                            human_scroll(p_page, scroll_amount=random.randint(120, 320))
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
