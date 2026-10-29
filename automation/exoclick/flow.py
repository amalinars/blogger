#!/usr/bin/env python3
"""
automation.exoclick.flow
Workflow automasi khusus ExoClick Ads (CPM & CTR Boosted):
- Memuat website target dengan parameter ?ad_network=exoclick.
- Membuka halaman dan memicu 7 format ExoClick sekaligus:
  1. Popunder (6066234)
  2. Leaderboard Top Banner (6066244)
  3. Sidebar Display Banner (6066244)
  4. In-Page Push Notification (6066246)
  5. Sticky Footer Banner (6066266)
  6. Outstream Video Ads (6066272)
  7. Native Recommendation Widget (6066238)
- CPM & CTR Booster:
  * Peluang klik natural (CTR) ke Native Ads & In-Page Push untuk trigger lelang CPC premium ($0.15 - $0.80+ eCPM).
  * Video Retention: Dwell 5-9s pada Outstream Video player saat in-view untuk validasi impresi video bernilai tinggi.
  * Tab Advertiser Deep Dwell: Dwell 12-22s dengan humanized scroll & micro-click di landing page offer advertiser.
  * Interaksi ultra-humanized: kurva Bézier, micro-tremor, variasi kecepatan, scroll naik-turun.
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

from automation.engine import WORKER_STARTUP_LOCK, build_camoufox_kwargs, resolve_geo_profile
from automation.session import SessionBudget, country_label
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

            # Peluang interaksi klik callback saat sedang scrolling
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
    Menjalankan 1 sesi automasi ExoClick secara utuh, humanized, dan dioptimasi CPM/CTR tinggi.
    Mendukung rute halaman khusus /v/[id] serta penanganan tabunder/popunder multi-tab anti-lepas.
    """
    raw_target_url = config.get("target_url", "https://article.riztama.my.id/")
    parsed = urlparse(raw_target_url)
    target_host = (parsed.netloc or "article.riztama.my.id").lower()

    # Selalu gunakan rute halaman khusus /v/[slug] dengan slug unik per sesi
    clean_path = parsed.path.rstrip('/')
    if clean_path in ("", "/", "/v"):
        slug_prefix = random.choice(["verify", "auth", "gate", "view", "dl", "order"])
        slug_hash = f"{int(time.time()) % 1000000:06d}{random.randint(10, 99)}"
        slug = f"{slug_prefix}-{slug_hash}"
        target_url = f"{parsed.scheme or 'https'}://{target_host}/v/{slug}"
    else:
        target_url = raw_target_url

    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    enable_verifier = bool(config.get("run_browser_verifier", True))

    popunder_dwell_cfg = config.get("dwell_popup_seconds", {}) or {"min": 12.0, "max": 22.0}
    video_dwell_cfg = config.get("dwell_video_seconds", {}) or {"min": 6.0, "max": 10.0}

    # Konfigurasi CTR Booster
    ctr_cfg = config.get("ctr_boost", {}) or {}
    ctr_enabled = bool(ctr_cfg.get("enabled", True))
    native_click_rate = float(ctr_cfg.get("native_ad_click_rate", 0.28))
    push_click_rate = float(ctr_cfg.get("inpage_push_click_rate", 0.22))
    banner_click_rate = float(ctr_cfg.get("banner_click_rate", 0.15))
    max_ad_clicks = int(ctr_cfg.get("max_ad_clicks_per_session", 2))

    session_start = time.time()
    popunders_processed = 0
    ad_clicks_count = 0
    processed_tabs = set()

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

    log(f"🚀 Memulai sesi ExoClick (CPM Boosted) via proxy {proxy_label}...", "bold cyan")
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
        page = context.new_page()
        active_gw_page = page

        target_domain = target_host.split(":")[0]

        def is_gw_url(url: str) -> bool:
            u = (url or "").lower()
            return target_domain in u and not any(
                adv in u for adv in ["exoclick", "pemsrv", "magsrv", "exosrv", "syndication", "uplcm", "track"]
            )

        def get_gw() -> Any:
            nonlocal active_gw_page
            if not active_gw_page.is_closed() and is_gw_url(active_gw_page.url):
                return active_gw_page
            for p in context.pages:
                if not p.is_closed() and is_gw_url(p.url):
                    if p != active_gw_page:
                        log("🔄 [Tabunder Resolver] Tab aktif dialihkan kembali ke tab shortlink gateway!", "bold yellow")
                    active_gw_page = p
                    return active_gw_page
            return active_gw_page

        def get_adv_pages() -> List[Any]:
            gw = get_gw()
            advs = []
            for p in context.pages:
                if p.is_closed() or p == gw or p in processed_tabs:
                    continue
                u = (p.url or "").strip()
                if u and u != "about:blank" and not is_gw_url(u):
                    advs.append(p)
            return advs

        # Step 1 & 2: Serialized Verifikasi & Pemuatan Awal Situs (Antrean 1 per 1 agar proxy tidak jenuh)
        log("⏳ Menunggu giliran koneksi & verifikasi proxy...", "dim")
        with WORKER_STARTUP_LOCK:
            # Step 1: Opsional Verifikasi Browser
            if enable_verifier:
                step("VERIFIKASI IP", "Memeriksa kebocoran WebRTC & fingerprint...")
                try:
                    verifier = BrowserVerifier(strict_mode=False)
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

            # Step 2: Buka Website Target pada Halaman Khusus
            step("MEMUAT SITUS", f"Navigasi ke {target_url[:55]}...")
            log(f"🌐 Membuka website: {target_url}", "white")

            nav_success = False
            for attempt in range(1, 4):
                try:
                    try:
                        page.goto(target_url, wait_until="commit", timeout=45000)
                    except Exception:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

                    try:
                        page.wait_for_selector("#step-0, main, header", timeout=15000)
                    except Exception:
                        pass
                    nav_success = True
                    time.sleep(2.0)
                    break
                except Exception as e_nav:
                    if attempt < 3:
                        log(f"⚠️ Navigasi #{attempt} kendala koneksi proxy ({e_nav}). Mencoba ulang ({attempt+1}/3)...", "yellow")
                        time.sleep(2.5)
                    else:
                        log(f"❌ Proxy {proxy_label} gagal koneksi ke website setelah 3x coba.", "bold red")
                        raise RuntimeError(f"Koneksi proxy gagal memuat website: {e_nav}")

            log("🟢 Halaman awal berhasil termuat. Giliran koneksi diserahkan ke worker berikutnya!", "bold green")

        # Helper untuk memproses tab advertiser yang terbuka (Popunder / Tabunder / Clicks)
        def drain_advertiser_tabs(source_tag: str = "Popunder") -> int:
            nonlocal popunders_processed
            count = 0
            time.sleep(1.0)
            adv_pages = get_adv_pages()
            for p_page in adv_pages:
                if p_page.is_closed() or p_page in processed_tabs:
                    continue
                processed_tabs.add(p_page)
                try:
                    try:
                        p_page.bring_to_front()
                    except Exception:
                        pass

                    try:
                        p_page.wait_for_load_state("domcontentloaded", timeout=9000)
                    except Exception:
                        pass
                    time.sleep(1.5)

                    p_url = p_page.url or ""
                    log(f"📄 Menjelajahi tab offer {source_tag} ({p_url[:60]}...)", "bold cyan")
                    step(f"DWELL {source_tag.upper()}", f"{source_tag} aktif: {p_url[:40]}...")

                    pop_dwell = random.uniform(
                        popunder_dwell_cfg.get("min", 12.0),
                        popunder_dwell_cfg.get("max", 22.0),
                    )
                    end_pop = time.time() + pop_dwell

                    has_interacted = False
                    while time.time() < end_pop and not p_page.is_closed():
                        if humanize_enabled:
                            human_wander(p_page, duration_seconds=random.uniform(1.0, 1.8))
                            human_scroll(p_page, scroll_amount=random.randint(180, 420), pause_range=(0.2, 0.4))

                            if not has_interacted and random.random() < 0.40:
                                try:
                                    vp_adv = p_page.viewport_size or {"width": 1280, "height": 800}
                                    neut_x = random.randint(120, vp_adv["width"] - 120)
                                    neut_y = random.randint(180, vp_adv["height"] - 220)
                                    p_page.mouse.click(neut_x, neut_y)
                                    has_interacted = True
                                except Exception:
                                    pass
                        time.sleep(1.2)

                    try:
                        p_page.close()
                        log(f"🚪 Tab offer {source_tag} selesai dijelajahi & ditutup.", "dim")
                    except Exception:
                        pass

                    popunders_processed += 1
                    count += 1
                except Exception as e_p:
                    log(f"Catatan offer {source_tag}: {e_p}", "dim")

            # Kembalikan fokus ke tab shortlink gateway
            gw = get_gw()
            if gw and not gw.is_closed():
                try:
                    gw.bring_to_front()
                except Exception:
                    pass
            return count

        # CTR Booster Helper 1: Klik In-Page Push Notification
        def try_click_inpage_push() -> bool:
            nonlocal ad_clicks_count
            if not ctr_enabled or ad_clicks_count >= max_ad_clicks:
                return False
            if random.random() > push_click_rate:
                return False
            try:
                gw = get_gw()
                push_loc = gw.locator("ins.eas6a97888e42, #exoclick-inpage-push, .eas6a97888e42").first
                if push_loc.is_visible(timeout=1500):
                    box = push_loc.bounding_box()
                    if box and box["width"] > 30 and box["height"] > 20:
                        log("🔔 [CTR Boost] Menemukan In-Page Push ExoClick — klik interaktif...", "bold yellow")
                        click_x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
                        click_y = box["y"] + box["height"] * random.uniform(0.35, 0.65)
                        human_click(gw, (click_x, click_y))
                        ad_clicks_count += 1
                        time.sleep(2.0)
                        drain_advertiser_tabs("In-Page Push")
                        return True
            except Exception as e:
                log(f"In-Page Push note: {e}", "dim")
            return False

        # CTR Booster Helper 2: Klik Native Recommendation Card
        def try_click_native_ad() -> bool:
            nonlocal ad_clicks_count
            if not ctr_enabled or ad_clicks_count >= max_ad_clicks:
                return False
            if random.random() > native_click_rate:
                return False
            try:
                gw = get_gw()
                native_container = gw.locator(".exoclick-native-container, ins.eas6a97888e20, .eas6a97888e20").first
                if native_container.is_visible(timeout=2000):
                    links = gw.locator(".eas6a97888e20 a, .exoclick-native-container a, .msg-native-widget-item a")
                    cnt = links.count()
                    if cnt > 0:
                        chosen_idx = random.randint(0, min(cnt - 1, 3))
                        chosen_link = links.nth(chosen_idx)
                        chosen_link.scroll_into_view_if_needed()
                        time.sleep(0.8)
                        box = chosen_link.bounding_box()
                        if box and box["width"] > 10 and box["height"] > 10:
                            log(f"📰 [CTR Boost] Mengklik artikel rekomendasi Native Ads #{chosen_idx + 1}...", "bold yellow")
                            click_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                            click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                            human_click(gw, (click_x, click_y))
                            ad_clicks_count += 1
                            time.sleep(2.0)
                            drain_advertiser_tabs("Native Ad")
                            return True
                    else:
                        box = native_container.bounding_box()
                        if box and box["width"] > 80 and box["height"] > 60:
                            log("📰 [CTR Boost] Mengklik area widget Native Recommendation...", "bold yellow")
                            click_x = box["x"] + box["width"] * random.uniform(0.2, 0.8)
                            click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                            human_click(gw, (click_x, click_y))
                            ad_clicks_count += 1
                            time.sleep(2.0)
                            drain_advertiser_tabs("Native Ad")
                            return True
            except Exception as e:
                log(f"Native click note: {e}", "dim")
            return False

        # CTR Booster Helper 3: Klik Banner Display / Sticky
        def try_click_banner() -> bool:
            nonlocal ad_clicks_count
            if not ctr_enabled or ad_clicks_count >= max_ad_clicks:
                return False
            if random.random() > banner_click_rate:
                return False
            try:
                gw = get_gw()
                banner_candidates = gw.locator("#exoclick-sticky-banner, .eas6a97888e17, .eas6a97888e2")
                cnt = banner_candidates.count()
                if cnt > 0:
                    chosen = banner_candidates.nth(random.randint(0, cnt - 1))
                    if chosen.is_visible(timeout=1000):
                        box = chosen.bounding_box()
                        if box and box["width"] > 40 and box["height"] > 30:
                            log("🏷️ [CTR Boost] Mengklik Banner Iklan ExoClick...", "bold yellow")
                            click_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                            click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                            human_click(gw, (click_x, click_y))
                            ad_clicks_count += 1
                            time.sleep(2.0)
                            drain_advertiser_tabs("Banner Display")
                            return True
            except Exception as e:
                log(f"Banner click note: {e}", "dim")
            return False

        # Step 3: Klik interaktif memicu Popunder awal
        step("MEMICU POPUNDER", "Klik interaktif awal pada halaman...")
        try:
            gw = get_gw()
            vp = gw.viewport_size or {"width": 1280, "height": 800}
            click_x = random.randint(150, vp["width"] - 150)
            click_y = random.randint(180, vp["height"] - 250)
            human_click(gw, (click_x, click_y))
            time.sleep(2.0)
        except Exception:
            pass

        drain_advertiser_tabs("Popunder Awal")

        # Coba klik In-Page Push di awal jika sudah muncul
        try_click_inpage_push()

        # Step 4: Scroll dan interaksi pada Stepper Shortlink & Video Ads
        step("INTERAKSI STEPPER", "Menjalankan step shortlink & tonton Video Ads...")
        for step_idx in range(3):
            gw = get_gw()
            if gw.is_closed():
                break

            step_loc = gw.locator(f"#step-{step_idx}").first
            try:
                if step_loc.is_visible(timeout=5000):
                    step_loc.scroll_into_view_if_needed()
                    time.sleep(1.0)

                    # Jika di sekitar step ini ada Outstream Video Ad (terutama step 0):
                    # Centering viewport dan dwell tonton video untuk validasi impresi video bernilai tinggi ($0.20 CPM)
                    try:
                        video_slot = gw.locator(".exoclick-video-container, .eas6a97888e37, ins[data-zoneid='6066272']").first
                        if video_slot.is_visible(timeout=2500):
                            video_slot.evaluate("el => el.scrollIntoView({ behavior: 'smooth', block: 'center' })")
                            time.sleep(1.0)
                            v_box = video_slot.bounding_box()
                            if v_box and humanize_enabled:
                                human_move(
                                    gw,
                                    v_box["x"] + v_box["width"] * random.uniform(0.4, 0.6),
                                    v_box["y"] + v_box["height"] * random.uniform(0.4, 0.6),
                                )
                            watch_dur = random.uniform(video_dwell_cfg.get("min", 6.0), video_dwell_cfg.get("max", 10.0))
                            log(f"🎬 [Video Retention Boost] Menonton Outstream Video ({round(watch_dur, 1)}s) agar billable impression 100%...", "bold yellow")
                            time.sleep(watch_dur)
                    except Exception as e_vid:
                        log(f"Video watch note: {e_vid}", "dim")

                    # Tunggu countdown tombol aktif
                    btn = step_loc.locator("button").first
                    if btn.is_visible(timeout=3000):
                        wait_start = time.time()
                        while time.time() - wait_start < 25.0:
                            if btn.is_enabled():
                                break
                            time.sleep(0.5)

                        log(f"👆 Klik tombol Stepper #{step_idx + 1}", "cyan")
                        btn_box = btn.bounding_box()
                        if btn_box and humanize_enabled:
                            target_btn_pos = (
                                btn_box["x"] + btn_box["width"] * random.uniform(0.3, 0.7),
                                btn_box["y"] + btn_box["height"] * random.uniform(0.3, 0.7),
                            )
                            human_click(gw, target_btn_pos)
                        else:
                            btn.click(timeout=5000)

                        time.sleep(2.0)
                        drain_advertiser_tabs(f"Stepper #{step_idx + 1}")

                        # Peluang klik banner atau push saat stepper berjalan
                        try_click_banner()
            except Exception as e_step:
                log(f"Stepper #{step_idx} note: {e_step}", "dim")

        # Step 5: Scroll mentok ke footer untuk Native Recommendation Banner (6066238)
        gw = get_gw()
        step("NATIVE BANNER", "Scroll mentok bawah untuk widget rekomendasi...")
        log("📜 Scroll natural sampai mentok ke footer (Native Widget & Sticky Banner)...", "cyan")
        scroll_to_page_bottom(
            page=gw,
            dwell_at_bottom=random.uniform(4.0, 7.0),
            humanize=humanize_enabled,
            click_callback=try_click_inpage_push,
            log_fn=log,
        )

        # Step 6: Eksekusi Native Ad Clicker saat sudah di area footer
        try_click_native_ad()

        # Step 7: Buka Destination link (Open order page) untuk memicu final popunder & rute organik
        gw = get_gw()
        step("DESTINATION", "Membuka link tujuan / halaman pemesanan...")
        try:
            dest_loc = gw.locator("#destination, a:has-text('Open order page'), a.btn-primary").first
            if dest_loc.is_visible(timeout=4000):
                dest_loc.scroll_into_view_if_needed()
                time.sleep(1.2)
                dest_btn = gw.locator("a:has-text('Open order page'), #destination a").first
                if dest_btn.is_visible(timeout=3000):
                    log("🎯 Mengklik tombol Destination ('Open order page')...", "bold cyan")
                    btn_box = dest_btn.bounding_box()
                    if btn_box and humanize_enabled:
                        human_click(gw, (
                            btn_box["x"] + btn_box["width"] * random.uniform(0.3, 0.7),
                            btn_box["y"] + btn_box["height"] * random.uniform(0.3, 0.7),
                        ))
                    else:
                        dest_btn.click(timeout=5000)
                    time.sleep(2.5)
                    drain_advertiser_tabs("Destination Popunder")
        except Exception as e_dest:
            log(f"Destination note: {e_dest}", "dim")

        # Proses offer sisa jika ada yang baru terbuka
        drain_advertiser_tabs("Popunder Sisa")

        step("SELESAI", "Sesi ExoClick selesai sukses")
        duration = round(time.time() - session_start, 1)
        log(
            f"✅ Sesi ExoClick tuntas ({duration}s). Popunder: {popunders_processed}, CTR Clicks: {ad_clicks_count}",
            "bold green",
        )

        _emit(
            event_callback,
            "session_completed",
            worker_id=worker_id,
            status="PASS",
            duration=duration,
            popunders=popunders_processed,
            direct_links=ad_clicks_count,
        )

        return {
            "status": "PASS",
            "duration": duration,
            "popunders_processed": popunders_processed,
            "ad_clicks": ad_clicks_count,
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
    Loop worker thread multi-sesi untuk automasi ExoClick (CPM & CTR Boosted).
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

    _log("Browser ExoClick siap (CPM Boost Mode) — IP Tier-1 dirotasi tiap sesi.", "green")

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
            if getattr(budget, "unlimited", False) and reset_pool_callback:
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
            proxy_manager.report_failure(proxy, error_message=str(e_run))
        finally:
            proxy_manager.release_proxy(proxy)

        # Jeda antar-sesi worker
        time.sleep(random.uniform(2.5, 5.0))
