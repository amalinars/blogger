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

from automation.engine import build_camoufox_kwargs, resolve_geo_profile
from automation.session import SessionBudget, country_label
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
    raw_target_url = config.get("target_url", "https://article.riztama.my.id/")
    parsed = urlparse(raw_target_url)
    target_host = (parsed.netloc or "article.riztama.my.id").lower()

    clean_path = parsed.path.rstrip('/')
    if clean_path in ("", "/", "/m"):
        slug_prefix = random.choice(["article", "news", "story", "read", "post"])
        slug_hash = f"{int(time.time()) % 1000000:06d}{random.randint(10, 99)}"
        slug = f"{slug_prefix}-{slug_hash}"
        target_url = f"{parsed.scheme or 'https'}://{target_host}/m/{slug}"
    else:
        target_url = raw_target_url

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

        target_domain = target_host.split(":")[0]

        direct_page: Optional[Any] = None

        # Listener deteksi pembukaan popup / tab iklan baru
        def on_popup(popup_page: Any) -> None:
            if popup_page == page or popup_page in popups_opened or (direct_page and popup_page == direct_page):
                return
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

        context.on("page", on_popup)
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
        log("Membaca konten & scrolling santai untuk memicu tag Monetag...", "cyan")
        vp = page.viewport_size or {"width": 1366, "height": 768}
        human_wander(page, duration_seconds=random.uniform(3.0, 5.0))
        human_scroll(page, scroll_amount=random.randint(240, 480))

        def get_gw() -> Any:
            """Mencari tab yang memuat target gateway / shortlink."""
            for p in context.pages:
                if not p.is_closed() and target_domain in str(p.url):
                    return p
            return page

        def get_adv_pages() -> List[Any]:
            """Mencari semua tab yang BUKAN target gateway (tab iklan/popunder/advertiser)."""
            advs = []
            for p in context.pages:
                if not p.is_closed() and p != page and target_domain not in str(p.url):
                    advs.append(p)
            return advs

        processed_popups = set()

        def drain_popups(tag_name: str = "Popunder") -> int:
            nonlocal popunders_processed
            count = 0
            time.sleep(1.0)

            # Gabungkan tab dari on_popup dan tab dari context.pages yang bukan gateway
            candidate_tabs: List[Any] = []
            for p in list(popups_opened) + get_adv_pages():
                if p not in candidate_tabs and not p.is_closed() and p != get_gw() and (not direct_page or p != direct_page):
                    candidate_tabs.append(p)


            for idx, popup in enumerate(candidate_tabs):
                if popup in processed_popups or popup.is_closed():
                    continue
                processed_popups.add(popup)
                try:
                    popup.bring_to_front()
                    # Tunggu jika URL masih about:blank sebelum navigasi selesai
                    for _ in range(8):
                        if popup.is_closed() or (popup.url and popup.url != "about:blank"):
                            break
                        time.sleep(0.5)

                    try:
                        popup.wait_for_load_state("domcontentloaded", timeout=9000)
                    except Exception:
                        pass
                    time.sleep(1.2)
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
                    log(f"📑 Melakukan dwell di tab iklan ({count+1}): {_host(popup_url)} ({dwell_time:.1f}s)", "magenta")

                    end_dwell = time.time() + dwell_time
                    has_interacted = False
                    while time.time() < end_dwell and not popup.is_closed():
                        if humanize_enabled:
                            human_wander(popup, duration_seconds=random.uniform(1.0, 1.8))
                            human_scroll(popup, scroll_amount=random.randint(180, 420), pause_range=(0.2, 0.4))
                            if not has_interacted and random.random() < 0.40:
                                try:
                                    vp_adv = popup.viewport_size or {"width": 1280, "height": 800}
                                    neut_x = random.randint(120, vp_adv["width"] - 120)
                                    neut_y = random.randint(180, vp_adv["height"] - 220)
                                    popup.mouse.click(neut_x, neut_y)
                                    has_interacted = True
                                except Exception:
                                    pass
                        time.sleep(1.2)

                    log(f"✅ Selesai dwell iklan {tag_name} ({_host(popup_url)}). Menutup tab...", "green")
                    try:
                        popup.close()
                    except Exception:
                        pass
                    popunders_processed += 1
                    count += 1
                except Exception as ex:
                    log(f"Peringatan proses popup: {ex}", "dim")

            # Kembalikan fokus ke tab shortlink gateway
            gw = get_gw()
            if gw and not gw.is_closed():
                try:
                    gw.bring_to_front()
                except Exception:
                    pass
            return count

        # ── 3. Interaksi Stepper Shortlink & Memicu Popunder Monetag ──
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="🎯 Interaksi Stepper",
            status="Menjalankan shortlink step...",
        )
        log("Memulai interaksi stepper shortlink untuk memicu Popunder Monetag...", "bold yellow")

        # Coba klik awal area netral untuk trigger OnClick jika tag sudah aktif
        gw = get_gw()
        if gw and not gw.is_closed():
            try:
                banner_area = gw.locator("header, main h1").first
                if banner_area.is_visible(timeout=2000):
                    human_click(gw, banner_area)
                    time.sleep(1.2)
                    drain_popups("Klik Awal")
            except Exception:
                pass

        for step_idx in range(3):
            gw = get_gw()
            if gw.is_closed():
                break

            step_loc = gw.locator(f"#step-{step_idx}").first
            try:
                if step_loc.is_visible(timeout=5000):
                    step_loc.scroll_into_view_if_needed()
                    time.sleep(1.0)

                    # Baca / wander sebentar di area step
                    if humanize_enabled:
                        human_wander(gw, duration_seconds=random.uniform(1.5, 3.0))

                    btn = step_loc.locator("button").first
                    if btn.is_visible(timeout=3000):
                        # Tunggu countdown tombol aktif
                        wait_start = time.time()
                        while time.time() - wait_start < 25.0:
                            if btn.is_enabled():
                                break
                            time.sleep(0.5)

                        log(f"👆 Klik tombol Stepper #{step_idx + 1}", "cyan")
                        time.sleep(random.uniform(0.15, 0.35))
                        btn.click(force=True, delay=random.randint(65, 140))
                        time.sleep(1.0)
                        # Jika stepper belum berpindah (klik pertama diserap overlay Monetag), klik tombol sekali lagi
                        try:
                            if btn.is_visible() and btn.is_enabled():
                                btn.click(force=True, delay=random.randint(60, 100))
                        except Exception:
                            pass

                        # Jika testing di localhost dan skrip Monetag tidak aktif karena domain lokal,
                        # simulasi trigger popunder ke direct link Monetag agar seluruh alur dwell teruji
                        if target_domain in ("localhost", "127.0.0.1") and not popups_opened and step_idx == 0:
                            try:
                                gw.evaluate("(url) => window.open(url, '_blank')", direct_link_url or "https://uplcm.com/4/12124796")
                            except Exception:
                                pass

                        # Beri jeda agar Monetag OnClick script membuka tab popunder
                        time.sleep(2.5)
                        drain_popups(f"Stepper #{step_idx + 1}")

            except Exception as e_step:
                log(f"Stepper #{step_idx} note: {e_step}", "dim")

        # ── 4. Klik Destination Link (Final Order Page) ──
        gw = get_gw()
        if gw and not gw.is_closed():
            try:
                dest_btn = gw.locator("#destination a.btn-primary, #destination-card a.btn-primary, a.btn-primary").first
                if dest_btn.is_visible(timeout=5000):
                    dest_btn.scroll_into_view_if_needed()
                    time.sleep(1.0)
                    log("🎯 Klik tombol Destination Link...", "cyan")
                    dest_btn.click(force=True, delay=random.randint(65, 140))
                    time.sleep(2.5)
                    drain_popups("Destination Click")
            except Exception as e_dest:
                log(f"Destination note: {e_dest}", "dim")



        # ── 5. Cek & Tutup Overlay Vignette Banner (Jika Muncul) ──
        gw = get_gw()
        if gw and not gw.is_closed():
            try:
                vignette_close = gw.locator(
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
                    human_click(gw, vignette_close)
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
                gw = get_gw()
                try:
                    with context.expect_page(timeout=10000) as new_page_info:
                        gw.evaluate(
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
                    direct_page = context.new_page()
                    direct_page.goto(direct_link_url, wait_until="domcontentloaded", timeout=45000)

                if direct_page:
                    try:
                        direct_page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    direct_page.bring_to_front()
                    end_dl = time.time() + direct_dwell
                    has_dl_interacted = False
                    while time.time() < end_dl and not direct_page.is_closed():
                        if humanize_enabled:
                            human_wander(direct_page, duration_seconds=random.uniform(1.0, 1.8))
                            human_scroll(direct_page, scroll_amount=random.randint(180, 420), pause_range=(0.2, 0.4))
                            if not has_dl_interacted and random.random() < 0.40:
                                try:
                                    vp_dl = direct_page.viewport_size or {"width": 1280, "height": 800}
                                    neut_x = random.randint(120, vp_dl["width"] - 120)
                                    neut_y = random.randint(180, vp_dl["height"] - 220)
                                    direct_page.mouse.click(neut_x, neut_y)
                                    has_dl_interacted = True
                                except Exception:
                                    pass
                        time.sleep(1.2)
                    try:
                        direct_page.close()
                    except Exception:
                        pass

                    gw = get_gw()
                    if gw and not gw.is_closed():
                        try:
                            gw.bring_to_front()
                        except Exception:
                            pass

                direct_links_processed += 1
                log("✅ Direct Link dwell selesai dengan sukses!", "bold green")
            except Exception as e_dl:
                log(f"Peringatan proses Direct Link: {e_dl}", "dim")

            # Kuras popunder yang mungkin terbuka saat klik direct link
            drain_popups("Post Direct Link")
        elif direct_link_url:
            log(f"ℹ️ Sesi ini fokus impresi MultiTag (Direct Link dilewati demi CTR organik ~{int(direct_link_chance * 100)}%).", "dim")

        # Pembersihan akhir untuk popunder yang tertunda
        drain_popups("Final Cleanup")


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
            if getattr(budget, "unlimited", False) and reset_pool_callback:
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
            proxy_manager.report_failure(proxy, error_message=str(e_run))
        finally:
            proxy_manager.release_proxy(proxy)

        # Jeda antar-sesi worker
        time.sleep(random.uniform(2.5, 5.0))
