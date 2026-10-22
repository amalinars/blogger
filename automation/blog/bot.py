#!/usr/bin/env python3
"""
traffic_bot.py - Synthetic Browser Emulation & Ad Viewability Engine
Designed for read.riztama.my.id (Chronicle Editorial Blog)

Complies with guidelines from docs/traffic.md:
- Native Playwright Chromium context with real Google Chrome binary
- Residential proxy rotation with country tracking
- Humanized scrolling & mouse movement for IAB viewability compliance (>1-2s in viewport)
- Coordinate-based physical mouse clicks (never bypasses ad overlays/popunders)
- Strict ad tab management: lets Popunder/Smartlink track, then closes tab cleanly before continuing
- Dwell time (35-50s) to capture the 25-second AdBanner auto-refresh cycles
- Multi-page internal navigation for low bounce rate & authentic Referers
"""

import os
import sys
import json
import time
import random
import socket
import threading
import argparse
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from playwright.sync_api import sync_playwright

try:
    from automation.core.browser import build_browser_args, format_proxy_dict, launch_browser, create_stealth_context
    from automation.core.stealth import get_geo_profile, get_fingerprint_profile, get_stealth_init_script
    from automation.core.proxy_manager import ProxyManager, ProxyUnavailableError, load_proxies, resolve_proxy_path
    from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from automation.core.browser import build_browser_args, format_proxy_dict, launch_browser, create_stealth_context
    from automation.core.stealth import get_geo_profile, get_fingerprint_profile, get_stealth_init_script
    from automation.core.proxy_manager import ProxyManager, ProxyUnavailableError, load_proxies, resolve_proxy_path
    from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause

_print_lock = threading.Lock()
_builtin_print = print

def print(*args, **kwargs):
    with _print_lock:
        _builtin_print(*args, **kwargs, flush=True)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "target_base_url": "https://read.riztama.my.id",
        "local_test_url": "http://localhost:3000",
        "use_local": False,
        "dwell_time": {"min_seconds": 35, "max_seconds": 50},
        "scroll_settings": {"step_pixels": 350, "pause_between_scrolls_min": 1.2, "pause_between_scrolls_max": 2.5},
        "proxy_source": "automation/proxies.json",
        "headless": False,
        "multi_page_navigation": True,
        "max_pages_per_session": 2,
        "smartlink_click_chance": 0.7,
        "use_organic_referers": True
    }


DEFAULT_REFERERS = [
    ("https://www.google.com/", 0.40),
    ("https://t.co/", 0.15),
    ("https://www.reddit.com/r/technology/", 0.10),
    ("https://l.facebook.com/", 0.05),
    ("https://www.bing.com/", 0.10),
    ("https://duckduckgo.com/", 0.05),
    ("https://news.ycombinator.com/", 0.05),
    (None, 0.10)
]

DEFAULT_SHORTLINK_SLUGS = [
    "in-defense-of-deliberate-slowness",
    "mechanical-sympathy-in-the-browser-runtime",
    "lost-art-of-digital-craftsmanship",
    "the-tactile-terminal-command-line-aesthetics",
    "the-death-of-digital-clutter-brutalist-clarity"
]


def get_organic_referer(custom_pool=None) -> str | None:
    """Mengembalikan referer acak terbobot (Google, Social, Search Engine, atau Direct)."""
    pool = custom_pool if custom_pool else DEFAULT_REFERERS
    urls = [item[0] for item in pool]
    weights = [float(item[1]) for item in pool]
    return random.choices(urls, weights=weights, k=1)[0]





def get_base_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def is_target_domain(url: str, target_base_url: str) -> bool:
    try:
        if not url:
            return True
        t_netloc = get_base_domain(target_base_url).lower()
        p_netloc = get_base_domain(url).lower()
        if not p_netloc or url.startswith("about:blank"):
            return True
        if "localhost" in t_netloc or "127.0.0.1" in t_netloc:
            return "localhost" in p_netloc or "127.0.0.1" in p_netloc
        if t_netloc in p_netloc or p_netloc in t_netloc:
            return True
        # Ekstrak brand / second-level domain (misal 'riztama' dari 'read.riztama.my.id')
        parts = t_netloc.split(".")
        if len(parts) >= 2:
            brand = parts[-3] if len(parts) >= 3 and parts[-2] in ["my", "co", "ac", "go", "or", "net", "com"] else parts[-2]
            if brand and brand in p_netloc:
                return True
        root = ".".join(parts[-2:]) if len(parts) >= 2 else t_netloc
        if root and p_netloc.endswith(root):
            return True
        return False
    except Exception:
        return True


# Melacak waktu terakhir tab guard mendeteksi tab agar tidak log-spam saat tab terus terbuka
_last_tab_guard_detection = {}

def enforce_single_target_tab(context, main_page, target_base_url, wait_seconds=3, worker_id=1):
    """
    STRICT SINGLE-TAB ENFORCER (DOMAIN-AWARE):
    Memastikan HANYA 1 tab yang terbuka di browser dan URL-nya adalah domain target sah.
    Jika ada tab iklan (apapun itu: smartlink, popunder, redirect ad Chaturbate dsb.),
    tab iklan akan ditutup bersih. Jika tab utama terbajak oleh redirect iklan,
    tab utama otomatis dinavigasikan kembali ke blog target.
    """
    tag = f"[B{worker_id}]"
    try:
        if not context:
            return main_page

        all_pages = [p for p in context.pages if not p.is_closed()]
        if not all_pages:
            return main_page

        target_pages = []
        ad_pages = []

        for p in all_pages:
            try:
                p_url = p.url or ""
                if is_target_domain(p_url, target_base_url):
                    target_pages.append(p)
                else:
                    ad_pages.append((p, p_url))
            except Exception:
                target_pages.append(p)

        now = time.time()
        last_detect = _last_tab_guard_detection.get(worker_id, 0)
        is_repeated = (now - last_detect) < 15
        _last_tab_guard_detection[worker_id] = now

        # Tutup semua tab iklan dengan jeda wajar agar impresi Monetag tercatat
        if ad_pages:
            if not is_repeated:
                print(f"{tag} [*] [TAB-GUARD] Terdeteksi {len(ad_pages)} tab iklan di luar domain target!")

            dwell_ad = max(wait_seconds, 4.5)
            if not is_repeated:
                print(f"{tag} 💰 [MONETAG POPUNDER] Menahan tab iklan selama {dwell_ad:.1f}s agar impresi sah tercatat...")
            time.sleep(dwell_ad)

            for ap, ap_url in ad_pages:
                try:
                    if not ap.is_closed():
                        if not is_repeated:
                            disp_url = ap_url[:60] if ap_url else "ad-tab"
                            print(f"{tag} [✓] [TAB-GUARD] Menutup tab smartlink/iklan: {disp_url}...")
                        ap.close(run_before_unload=False)
                except Exception as close_err:
                    print(f"{tag} [-] [TAB-GUARD-NOTICE] Gagal menutup tab iklan: {close_err}")

        # Tentukan halaman target aktif
        active_target = None
        if target_pages:
            if main_page in target_pages and not main_page.is_closed():
                active_target = main_page
            else:
                active_target = target_pages[0]
        else:
            # Kasus kritis: main_page dibajak iklan dan tidak ada tab target lain!
            if main_page and not main_page.is_closed():
                print(f"{tag} [!] [HOLD/RECOVERY] Halaman utama dibajak iklan ({main_page.url[:60]})! Mengembalikan layar ke blog target...")
                try:
                    main_page.goto(target_base_url, wait_until="domcontentloaded", timeout=20000)
                    active_target = main_page
                except Exception as nav_e:
                    print(f"{tag} [-] [HOLD/ERROR] Gagal memulihkan navigasi target: {nav_e}")
                    active_target = main_page

        # Kembalikan fokus utama ke halaman target
        if active_target and not active_target.is_closed():
            try:
                active_target.bring_to_front()
            except Exception:
                pass
            if ad_pages and not is_repeated:
                t_domain = get_base_domain(target_base_url)
                print(f"{tag} [✓] [TAB-GUARD] Selesai: Hanya 1 tab aktif tersisa ({t_domain}). Layar kembali ke blog.")

        return active_target if active_target else main_page
    except Exception as e:
        print(f"{tag} [-] [TAB-GUARD] Notice: {e}")
        return main_page


def dismiss_vignette_if_present(page, dwell_seconds=5, worker_id=1):
    """
    Menangani iklan Monetag Vignette/Interstitial secara pintar:
    1. Memberikan waktu tayang wajar (dwell_seconds, default 4-6 detik) agar impresi sah
       tercatat di server Monetag (tidak terdeteksi sebagai misclick/adblocker).
    2. Mencoba mengklik tombol 'Close' di dalam frame Monetag.
    3. Jika overlay masih menutupi layar setelah waktu jeda, sembunyikan layer agar
       tidak memblokir klik tombol Shortlink Gateway ('Continue' / 'Next Step').
    """
    tag = f"[B{worker_id}]"
    try:
        if not page or page.is_closed():
            return page

        # Cek apakah ada overlay Vignette (iframe fullscreen dengan z-index tinggi)
        has_vignette = page.evaluate("""() => {
            const iframes = Array.from(document.querySelectorAll('iframe'));
            return iframes.some(ifr => {
                const s = window.getComputedStyle(ifr);
                return (s.position === 'fixed' || s.position === 'absolute') &&
                       parseInt(s.zIndex, 10) > 1000000 &&
                       ifr.getBoundingClientRect().height > 300;
            });
        }""")

        if has_vignette:
            print(f"{tag} 📢 [MONETAG VIGNETTE] Terdeteksi iklan interstitial overlay. Memberikan waktu tayang {dwell_seconds}s (impresi sah)...")
            time.sleep(dwell_seconds)

            # Coba klik tombol Close di dalam frame Monetag
            for f in page.frames:
                if f != page.main_frame:
                    try:
                        btn = f.locator("text='Close'")
                        if btn.count() > 0:
                            btn.first.click(timeout=2000)
                            print(f"{tag} [✓] [MONETAG VIGNETTE] Tombol 'Close' di dalam frame berhasil diklik.")
                            break
                    except Exception:
                        pass

            time.sleep(1.0)
            # Hilangkan overlay jika masih menempel agar tombol navigasi tidak terhalang
            page.evaluate("""() => {
                const iframes = Array.from(document.querySelectorAll('iframe'));
                iframes.forEach(ifr => {
                    const s = window.getComputedStyle(ifr);
                    if ((s.position === 'fixed' || s.position === 'absolute') &&
                        parseInt(s.zIndex, 10) > 1000000 &&
                        ifr.getBoundingClientRect().height > 300) {
                        ifr.style.display = 'none';
                    }
                });
            }""")
    except Exception:
        pass
    return page






def handle_smartlink_click(context, main_page, smartlink_btn, target_base_url, worker_id: int = 1):
    """
    Interaksi klik Smartlink / Advertiser CTA:
    1. Klik tombol CTA secara fisik alami.
    2. Tunggu tab smartlink terbuka dan beralih fokus ke tab advertiser.
    3. Lakukan authentic engagement (dwell 15-24 detik + scrolling & mouse movement) di landing page pengiklan.
       Hal ini penting agar pengiklan tidak mencatat traffic sebagai 0s bounce / click fraud.
    4. Tutup tab iklan secara bersih dan kembalikan fokus ke artikel target.
    """
    tag = f"[B{worker_id}]"
    try:
        print(f"{tag} [*] Physically clicking Smartlink CTA button...")
        click_element_naturally(main_page, smartlink_btn)

        # Tunggu kemunculan tab smartlink baru (polling hingga 3.5 detik)
        new_tab = None
        start_wait = time.time()
        while time.time() - start_wait < 3.5:
            extra = [p for p in context.pages if p != main_page and not p.is_closed()]
            if extra:
                new_tab = extra[0]
                break
            time.sleep(0.3)

        if new_tab:
            try:
                tab_url = new_tab.url[:70]
            except Exception:
                tab_url = "Smartlink Ad Page"

            dwell_ad = int(random.uniform(14.0, 24.0))
            print(f"{tag} [✓] [SMARTLINK] Tab iklan/smartlink terbuka ({tab_url}). Melakukan authentic engagement di landing page ({dwell_ad}s)...")
            try:
                new_tab.bring_to_front()
                time.sleep(random.uniform(2.0, 3.5))

                ad_start = time.time()
                last_ad_log = time.time()
                while time.time() - ad_start < dwell_ad:
                    if new_tab.is_closed():
                        break
                    now = time.time()
                    if now - last_ad_log >= 5.0:
                        rem = max(0, int(dwell_ad - (now - ad_start)))
                        if rem > 0:
                            print(f"{tag} [*] ⏳ Smartlink ad dwell remaining: {rem}s...")
                        last_ad_log = now
                    try:
                        rx = random.randint(150, 750)
                        ry = random.randint(150, 550)
                        new_tab.mouse.move(rx, ry, steps=random.randint(6, 14))
                        scroll_amount = random.choice([150, 250, 320, -120])
                        smooth_scroll(new_tab, scroll_amount, steps=8)
                    except Exception:
                        pass
                    time.sleep(random.uniform(1.5, 3.0))

                print(f"{tag} [✓] [SMARTLINK] Selesai membaca landing page pengiklan ({dwell_ad}s). Menutup tab iklan...")
                new_tab.close(run_before_unload=False)
            except Exception as ad_err:
                print(f"{tag} [-] [SMARTLINK] Notice interaksi tab iklan: {ad_err}")
                try:
                    new_tab.close(run_before_unload=False)
                except Exception:
                    pass

        # Bersihkan jika masih ada tab popup lain yang tersisa
        main_page = enforce_single_target_tab(context, main_page, target_base_url, wait_seconds=1, worker_id=worker_id)

        # Pastikan layar kembali fokus ke artikel
        if main_page and not main_page.is_closed():
            try:
                main_page.bring_to_front()
            except Exception:
                pass
            print(f"{tag} [✓] [SMARTLINK] Tab smartlink telah ditutup bersih. Layar kembali fokus di artikel untuk dwell time!")

        return main_page
    except Exception as e:
        print(f"{tag} [-] [HOLD/ERROR] Smartlink click handler notice: {e}")
        return main_page


def human_dwell(page, context, target_url, duration: int, worker_id: int = 1, label: str = "artikel"):
    """
    Simulasi Dwell Time Aktif:
    Tidak diam membeku, melainkan scrolling santai ke atas dan ke bawah sesekali (membaca ulang paragraf),
    disertai gerakan mouse alami dan penjagaan tab tunggal sambil menunggu auto-refresh iklan 35s.
    """
    tag = f"[B{worker_id}]"
    # Guard: halaman None (bisa terjadi jika human_scroll mengembalikan None saat page sudah closed)
    if page is None:
        print(f"{tag} [-] [DWELL-NOTICE] Dwell dibatalkan: halaman browser adalah None (sudah ditutup sebelumnya).")
        return page
    page_desc = "Artikel" if label == "artikel" else "Beranda"
    dwell_scope = f"di {page_desc}" if label == "beranda" else "aktif"
    print(f"{tag} [*] Dwell time {dwell_scope}: {duration}s (Membaca santai & scrolling naik-turun {page_desc} sambil menunggu auto-refresh iklan 35s)...")
    end_time = time.time() + duration
    last_scroll_time = time.time()
    last_tab_guard_time = 0  # Cooldown agar tab guard tidak dipanggil setiap detik
    last_countdown_log = time.time()

    while time.time() < end_time and not page.is_closed():
        now = time.time()

        # Tab guard dengan cooldown 8 detik — mencegah loop spam deteksi tab berulang
        if now - last_tab_guard_time > 8.0:
            page = enforce_single_target_tab(context, page, target_url, wait_seconds=1, worker_id=worker_id)
            last_tab_guard_time = time.time()

        # Countdown heartbeat log setiap 5-6 detik agar realtime status terbaca di console log
        if now - last_countdown_log >= 5.0:
            rem = max(0, int(end_time - now))
            if rem > 0:
                print(f"{tag} [*] ⏳ Dwell time remaining: {rem}s ({page_desc} viewability aktif)...")
            last_countdown_log = now

        # Setiap 6 - 9 detik, lakukan scrolling aktif naik-turun alami
        if now - last_scroll_time > random.uniform(6.0, 9.5):
            try:
                if not page.is_closed():
                    direction = random.choice([-1, 1, -1, 1, 1])
                    scroll_amount = random.randint(140, 280) * direction
                    smooth_scroll(page, distance=scroll_amount, steps=random.randint(8, 14))
                    last_scroll_time = time.time()

                    # Mouse bergerak ke teks artikel/banner
                    page.mouse.move(
                        random.randint(200, 750),
                        random.randint(200, 580),
                        steps=random.randint(4, 9)
                    )
            except Exception as scroll_err:
                print(f"{tag} [-] [DWELL-NOTICE] Interaksi scroll santai dilewati: {scroll_err}")

        time.sleep(1.0)

    if page.is_closed():
        print(f"{tag} [-] [DWELL-NOTICE] Dwell time dihentikan karena halaman browser ditutup.")
    else:
        print(f"{tag} [✓] Dwell time selesai ({duration}s). Melanjutkan flow...")
    return page


def human_scroll(page, config, context=None, target_url="", max_scroll_steps=12, worker_id=1, label="artikel"):
    """Simulates organic reading behavior with continuous tab guard protection."""
    tag = f"[B{worker_id}]"
    step = config.get("scroll_settings", {}).get("step_pixels", 320)
    p_min = config.get("scroll_settings", {}).get("pause_between_scrolls_min", 1.2)
    p_max = config.get("scroll_settings", {}).get("pause_between_scrolls_max", 2.4)

    try:
        if page is None or page.is_closed():
            print(f"{tag} [-] [SCROLL-NOTICE] Scroll dibatalkan: halaman tidak tersedia (closed/None).")
            return page

        total_height = page.evaluate("() => document.body.scrollHeight")
        viewport_height = page.evaluate("() => window.innerHeight")
        current_scroll = 0
        steps_done = 0

        if label == "beranda":
            print(f"{tag} [*] 📜 [BERANDA] Menjelajahi Beranda santai (Scroll bertahap agar iklan header, feed, dan sidebar terlihat)...")
        else:
            print(f"{tag} [*] Membaca artikel perlahan (Scroll bertahap agar seluruh banner masuk viewport)...")

        last_guard_step = -1  # Cooldown: tab guard setiap 3 langkah scroll, bukan setiap langkah

        while current_scroll + viewport_height < total_height and steps_done < max_scroll_steps:
            if page.is_closed():
                break

            # Tab guard setiap 3 langkah scroll agar tidak memperlambat setiap step
            if context and target_url and (steps_done - last_guard_step >= 3):
                page = enforce_single_target_tab(context, page, target_url, wait_seconds=1, worker_id=worker_id)
                last_guard_step = steps_done

            scroll_by = random.randint(step - 40, step + 80)
            smooth_scroll(page, distance=scroll_by, steps=random.randint(5, 8))
            current_scroll += scroll_by
            steps_done += 1

            # Gerakan mouse alami
            try:
                if not page.is_closed():
                    page.mouse.move(
                        random.randint(180, 750),
                        random.randint(180, 580),
                        steps=random.randint(3, 6)
                    )
            except Exception:
                pass

            pause = random.uniform(p_min, p_max)
            time.sleep(pause)

        # Final check di akhir scroll
        if context and target_url and not page.is_closed():
            page = enforce_single_target_tab(context, page, target_url, wait_seconds=1, worker_id=worker_id)

        if label == "beranda":
            print(f"{tag} [+] Scroll Beranda selesai. Seluruh posisi banner iklan di Beranda telah dirender.")
        else:
            print(f"{tag} [+] Scroll artikel selesai. Posisi iklan telah dirender.")
        return page
    except Exception as e:
        print(f"{tag} [-] [SCROLL-NOTICE] Scroll simulation notice: {e}")
        if context and target_url:
            try:
                page = enforce_single_target_tab(context, page, target_url, wait_seconds=1, worker_id=worker_id)
            except Exception:
                pass
        return page


def click_element_naturally(page, element, worker_id=1):
    """Moves mouse naturally to element's bounding box and clicks with safe timeout."""
    tag = f"[B{worker_id}]"
    try:
        element.scroll_into_view_if_needed(timeout=7000)
        time.sleep(random.uniform(0.4, 0.9))
        box = element.bounding_box()
        if not box:
            return False
        target_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
        target_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
        page.mouse.move(target_x, target_y, steps=random.randint(8, 16))
        time.sleep(random.uniform(0.12, 0.25))
        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.16))
        page.mouse.up()
        return True
    except Exception as click_err:
        print(f"{tag} [-] [CLICK-NOTICE] Klik alami dialihkan: {click_err}")
        return False


def is_shortlink_gateway_present(page) -> bool:
    """
    Mendeteksi apakah halaman saat ini merupakan artikel dengan sistem 4-Layer Shortlink Gateway.
    Mengecek indikator unik seperti countdown timer, layer progress, status pill, atau tombol unlock.
    """
    try:
        if not page or page.is_closed():
            return False
        if "/post/" not in (page.url or ""):
            return False
        gateway = page.query_selector(
            "button:has-text('Please Wait'), a[href*='step='], a[href*='modapk.org'], "
            "div:has-text('Verifying Integrity Protocols'), div:has-text('Audit Complete'), "
            "div:has-text('Destination Gateway Unlocked')"
        )
        return gateway is not None
    except Exception:
        return False


def traverse_shortlink_flow(page, context, target_base_url, config, worker_id: int = 1):
    """
    Menjelajahi Alur 4-Layer Shortlink Gateway Organik:
    1. Membaca artikel teknis pada setiap layer (Step 1 s/d 4) dengan scroll bertahap & pergerakan mouse alami.
    2. Menunggu countdown timer (8 detik) sampai tombol unlock aktif.
    3. Memberikan jeda reaksi manusiawi (1.5 - 3.5 detik).
    4. Mengklik tombol unlock secara fisik alami (memicu impresi/onclick Monetag).
    5. Menjaga tab dari popunder yang terbuka (memberi dwell sejenak lalu menutup bersih).
    6. Pada Layer 4 (final), mengklik link ke tujuan akhir 'modapk.org', melakukan authentic engagement di landing page, lalu menyelesaikan alur.
    """
    tag = f"[B{worker_id}]"
    if page is None or page.is_closed():
        return page

    sl_settings = config.get("shortlink_settings", {})
    max_steps = sl_settings.get("max_steps", 4)
    buffer_min = sl_settings.get("step_dwell_buffer_seconds", {}).get("min", 1.5)
    buffer_max = sl_settings.get("step_dwell_buffer_seconds", {}).get("max", 3.5)
    click_final = sl_settings.get("click_final_destination", True)
    smartlink_chance = config.get("smartlink_click_chance", 0.7)
    smartlink_clicked_in_flow = False

    print(f"\n{tag} 🛡️ [SHORTLINK] Terdeteksi 4-Layer Shortlink Gateway. Memulai penelusuran (Target Maks: {max_steps} Layer)...")

    # Ambil step awal dari query string URL (?step=X), default 1
    try:
        current_url = page.url or ""
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query)
        step_start = int(qs.get("step", [1])[0])
    except Exception:
        step_start = 1

    for step in range(step_start, max_steps + 1):
        if page is None or page.is_closed():
            break

        is_final_layer = (step >= max_steps)
        layer_desc = f"Layer {step}/{max_steps}" + (" (Final Handshake -> modapk.org)" if is_final_layer else "")
        print(f"\n{tag} 📖 [SHORTLINK] Membaca artikel {layer_desc} pada: {page.url}...")

        # 1. Authentic Reading & Scrolling di Layer ini
        # Scroll bertahap membaca artikel teknis (dan memicu inisialisasi tag Monetag / in-page push / vignette)
        try:
            scroll_count = random.randint(3, 5)
            for _ in range(scroll_count):
                if page.is_closed():
                    break
                scroll_px = random.randint(200, 380)
                smooth_scroll(page, distance=scroll_px, steps=random.randint(6, 10))
                page.mouse.move(
                    random.randint(220, 680),
                    random.randint(220, 520),
                    steps=random.randint(4, 8)
                )
                time.sleep(random.uniform(1.0, 1.8))
        except Exception as sc_err:
            print(f"{tag} [-] [SHORTLINK-NOTICE] Scroll step {step}: {sc_err}")

        # 1b. Interaksi Monetag Direct Link Sponsor Mirror jika tersedia dan peluang aktif
        if not smartlink_clicked_in_flow and random.random() < smartlink_chance:
            try:
                dl_selector = "a[data-directlink='true'], a[href*='uplcm.com']"
                direct_btn = page.query_selector(dl_selector)
                if direct_btn and direct_btn.is_visible():
                    print(f"\n{tag} ⚡ [DIRECT-LINK] Menemukan Monetag Direct Link Sponsor Mirror pada Layer {step} (Peluang {smartlink_chance*100:.0f}%). Memulai interaksi landing page...")
                    page = handle_smartlink_click(context, page, direct_btn, target_base_url, worker_id=worker_id)
                    smartlink_clicked_in_flow = True
                    time.sleep(1.5)
            except Exception as dl_err:
                print(f"{tag} [-] [DIRECT-LINK-NOTICE] Interaksi direct link: {dl_err}")

        # 2. Tunggu countdown timer selesai dan tombol unlock aktif
        target_selector = "a[href*='modapk.org'], a:has-text('Proceed to modapk.org'), a:has-text('Get Link')" if is_final_layer else f"a[href*='step={step + 1}'], a:has-text('Continue to Layer {step + 1}')"

        print(f"{tag} ⏳ [SHORTLINK] Menunggu countdown verifikasi Layer {step} (8s) hingga tombol unlock aktif...")
        unlocked_btn = None
        wait_start = time.time()
        timeout_sec = 20.0

        while time.time() - wait_start < timeout_sec:
            if page.is_closed():
                break

            # Cek apakah tombol unlock sudah ada di DOM dan terlihat
            try:
                candidate = page.query_selector(target_selector)
                if candidate and candidate.is_visible():
                    unlocked_btn = candidate
                    break
            except Exception:
                pass

            # Gerakan mouse halus sesekali
            try:
                rx = random.randint(280, 620)
                ry = random.randint(260, 480)
                page.mouse.move(rx, ry, steps=random.randint(3, 6))
            except Exception:
                pass

            time.sleep(1.0)

        if not unlocked_btn and not page.is_closed():
            # Fallback jika selector ketat belum match
            try:
                if is_final_layer:
                    unlocked_btn = page.query_selector("a[href*='modapk.org'], a:has-text('Get Link')")
                else:
                    unlocked_btn = page.query_selector(f"a[href*='step={step + 1}']")
            except Exception:
                pass

        if not unlocked_btn:
            print(f"{tag} [!] [SHORTLINK] Tombol unlock Layer {step} tidak ditemukan setelah {int(time.time() - wait_start)}s. Melanjutkan alur...")
            break

        # 3. Jeda Reaksi Manusiawi (Human Reaction Delay)
        reaction_delay = random.uniform(buffer_min, buffer_max)
        print(f"{tag} [✓] [SHORTLINK] Tombol Layer {step} telah aktif! Jeda reaksi membaca: {reaction_delay:.1f}s...")
        time.sleep(reaction_delay)

        # 3b. Pastikan jika ada Monetag Vignette overlay, beri waktu tayang lalu tutup agar tidak memblokir tombol
        page = dismiss_vignette_if_present(page, dwell_seconds=4, worker_id=worker_id)

        # 4. Klik Alami ke Tombol
        if not is_final_layer:
            print(f"{tag} 👆 [SHORTLINK] Mengklik tombol navigasi ke Layer {step + 1}...")
            click_element_naturally(page, unlocked_btn, worker_id=worker_id)

            # Jeda agar event click & popunder Monetag terpicu jika ada
            time.sleep(1.5)

            # Jaga tab: jika Monetag memicu popunder, biarkan tercatat lalu tutup bersih
            page = enforce_single_target_tab(context, page, target_base_url, wait_seconds=2, worker_id=worker_id)

            # Pastikan halaman sudah pindah ke step berikutnya
            try:
                expected_query = f"step={step + 1}"
                if not page.is_closed() and expected_query not in (page.url or ""):
                    href = unlocked_btn.get_attribute("href")
                    if href:
                        next_url = urljoin(target_base_url, href)
                        print(f"{tag} [*] ➡️ [SHORTLINK-RECOVERY] Navigasi step tertahan overlay, memuat URL langsung: {next_url}...")
                        page.goto(next_url, wait_until="domcontentloaded", timeout=25000)
                        page = enforce_single_target_tab(context, page, target_base_url, wait_seconds=1.5, worker_id=worker_id)
            except Exception as nav_chk_err:
                print(f"{tag} [-] [SHORTLINK-NOTICE] Navigasi step check: {nav_chk_err}")

        else:
            # Layer 4 Final -> Menuju modapk.org
            if click_final:
                print(f"{tag} 🎯 [SHORTLINK-DESTINATION] Mengklik tombol final clearance ke modapk.org...")
                try:
                    prev_pages = list(context.pages)
                    click_element_naturally(page, unlocked_btn, worker_id=worker_id)
                    time.sleep(2.5)

                    dest_tab = None
                    dest_wait_start = time.time()
                    while time.time() - dest_wait_start < 6.0:
                        current_pages = [p for p in context.pages if not p.is_closed()]
                        for cp in current_pages:
                            if cp not in prev_pages and "modapk.org" in (cp.url or "").lower():
                                dest_tab = cp
                                break
                        if dest_tab:
                            break
                        time.sleep(0.5)

                    if dest_tab:
                        print(f"{tag} [✓] [DESTINATION] Tab tujuan modapk.org terbuka ({dest_tab.url})! Melakukan authentic reader engagement...")
                        try:
                            dest_tab.bring_to_front()
                            dest_dwell = random.randint(5, 8)
                            d_start = time.time()
                            while time.time() - d_start < dest_dwell and not dest_tab.is_closed():
                                smooth_scroll(dest_tab, distance=random.randint(180, 320), steps=6)
                                time.sleep(random.uniform(1.5, 2.5))
                            print(f"{tag} [✓] [DESTINATION] Selesai berinteraksi di landing page modapk.org ({dest_dwell}s). Menutup tab tujuan...")
                            dest_tab.close(run_before_unload=False)
                        except Exception as dest_err:
                            print(f"{tag} [-] [DESTINATION-NOTICE] Interaksi tab modapk: {dest_err}")
                    else:
                        print(f"{tag} [*] [DESTINATION] Tombol final telah diklik.")
                except Exception as final_click_err:
                    print(f"{tag} [-] [DESTINATION-NOTICE] Klik final link notice: {final_click_err}")

            # Bersihkan tab popunder jika ada
            page = enforce_single_target_tab(context, page, target_base_url, wait_seconds=2, worker_id=worker_id)
            print(f"{tag} [✓] [SHORTLINK] Seluruh 4 Layer Gateway & Landing Target selesai ditelusuri dengan sempurna!")

    return page


def run_single_session_safe(target_url="https://read.riztama.my.id", use_proxy=True, proxy=None, proxy_idx=None, headless=False, config=None, max_pages=2, return_home=False, worker_id=1, proxy_manager=None):
    """
    Wrapper aman untuk menjalankan 1 sesi.
    Memeriksa kepatuhan anti-leak: jika use_proxy=True tetapi proxy is None,
    sesi langsung dibatalkan tanpa pernah memuat target URL dengan IP lokal.
    """
    tag = f"[B{worker_id}]"
    if use_proxy and not proxy:
        print(f"{tag} [!] [ANTI-LEAK GUARD] Sesi dibatalkan! Mode proksi aktif tetapi tidak ada proksi valid yang tersedia. Mencegah kebocoran IP lokal asli.")
        return False

    try:
        run_session(
            target_url=target_url,
            proxy=proxy,
            proxy_idx=proxy_idx,
            headless=headless,
            config=config,
            max_pages=max_pages,
            return_home=return_home,
            worker_id=worker_id,
            proxy_manager=proxy_manager
        )
        return True
    except ProxyUnavailableError as pe:
        print(f"{tag} [!] [ANTI-LEAK GUARD] {pe}")
        return False
    except Exception as e:
        print(f"{tag} [-] Session error: {e}")
        return False


def run_session(target_url, proxy=None, proxy_idx=None, headless=False, config=None, max_pages=3, return_home=True, worker_id=1, proxy_manager=None):
    """Executes an organic multi-hop browsing session with full ad tech viewability tracking."""
    if config is None:
        config = load_config()

    dwell_min = config.get("dwell_time", {}).get("min_seconds", 35)
    dwell_max = config.get("dwell_time", {}).get("max_seconds", 55)
    tag = f"[B{worker_id}]"

    print("\n" + "=" * 65)
    print(f"{tag} [*] Target Awal: {target_url}")
    if proxy and proxy_idx is not None:
        country = proxy.get("country", "Unknown")
        print(f"{tag} [*] Proxy: [PX#{proxy_idx + 1}] {proxy.get('host')}:{proxy.get('port')} (Geo: {country})")
    elif proxy:
        country = proxy.get("country", "Unknown")
        print(f"{tag} [*] Proxy: {proxy.get('host')}:{proxy.get('port')} (Geo: {country})")
    else:
        print(f"{tag} [*] Proxy: Direct (No Proxy)")
    print(f"{tag} [*] Multi-Hop Exploration: {max_pages} Halaman per Sesi (Return Home: {return_home})")
    print("=" * 65)

    with sync_playwright() as p:
        browser = None
        context = None
        session_failed = False
        start_time = time.time()

        try:
            # Menghitung posisi jendela bertingkat (cascade) agar setiap browser terlihat terpisah jelas di layar (hingga 20 browser)
            col = (worker_id - 1) % 5
            row = (worker_id - 1) // 5
            x_offset = col * 75 + row * 25 + 30
            y_offset = row * 60 + col * 25 + 30

            browser_args = build_browser_args(
                window_position=(x_offset, y_offset),
                window_size=(1260, 820),
            )
            proxy_dict = format_proxy_dict(proxy)
            browser = launch_browser(
                p,
                proxy_dict=proxy_dict,
                headless=headless,
                browser_args=browser_args,
                tag=tag,
            )

            proxy_country = proxy.get("country", "") if proxy else ""
            context, meta = create_stealth_context(
                browser,
                proxy_country=proxy_country,
                tag=tag,
            )

            page = context.new_page()
            page.set_default_timeout(15000)
            page.set_default_navigation_timeout(25000)
            try:
                page.on("dialog", lambda dialog: dialog.dismiss())
            except Exception:
                pass
            # Direct Shortlink Routing:
            # Jika target_url belum mengarah ke link artikel shortlink (/post/...), arahkan langsung!
            if "/post/" not in target_url:
                chosen_slug = random.choice(DEFAULT_SHORTLINK_SLUGS)
                clean_base = target_url.rstrip("/")
                target_url = f"{clean_base}/post/{chosen_slug}?step=1"
                print(f"{tag} 🎯 [SHORTLINK MODE] Navigasi langsung ke link Gateway Shortlink: {target_url}")
            elif "?step=" not in target_url:
                target_url = f"{target_url}?step=1"

            visited_urls = set()
            visited_urls.add(target_url)

            # Gunakan Organic Referer Engine
            referer = get_organic_referer(config.get("organic_referer_pool")) if config.get("use_organic_referers", True) else None
            ref_label = referer if referer else "Direct (None)"
            print(f"{tag} [*] Navigating directly to Shortlink: {target_url} (Referer: {ref_label})...")
            if referer:
                page.goto(target_url, referer=referer, wait_until="domcontentloaded", timeout=60000)
            else:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(random.uniform(2.0, 3.5))

            # Trigger klik fisik koordinat awal (memicu popunder/ad overlay Monetag jika ada)
            print(f"{tag} [*] Performing physical mouse click at coordinates (Hits ad overlay/popunder)...")
            try:
                cx = random.randint(250, 650)
                cy = random.randint(220, 480)
                page.mouse.move(cx, cy, steps=random.randint(10, 18))
                time.sleep(random.uniform(0.15, 0.3))
                page.mouse.down()
                time.sleep(random.uniform(0.08, 0.16))
                page.mouse.up()
            except Exception:
                pass

            # Enforce single tab guard jika popunder terbuka, lalu tangani vignette overlay jika ada
            page = enforce_single_target_tab(context, page, target_url, wait_seconds=3, worker_id=worker_id)
            page = dismiss_vignette_if_present(page, dwell_seconds=5, worker_id=worker_id)

            # =========================================================
            # PENELUSURAN SHORTLINK GATEWAY (Hop 1 .. max_pages)
            # =========================================================
            for hop in range(1, max_pages + 1):
                if page.is_closed():
                    break

                # Jika hop > 1 atau halaman belum di /post/, navigasi ke slug shortlink berikutnya
                if hop > 1 or "/post/" not in page.url:
                    known_slugs = [f"/post/{s}?step=1" for s in DEFAULT_SHORTLINK_SLUGS]
                    unvisited = [s for s in known_slugs if s not in visited_urls]
                    chosen_slug_url = random.choice(unvisited if unvisited else known_slugs)
                    visited_urls.add(chosen_slug_url)
                    full_article_url = urljoin(target_url, chosen_slug_url)
                    print(f"\n{tag} [*] ➡️ [SHORTLINK HOP #{hop}] Memuat URL Gateway Shortlink berikutnya: {full_article_url}...")
                    try:
                        page.goto(full_article_url, wait_until="domcontentloaded", timeout=25000)
                    except Exception as nav_e:
                        print(f"{tag} [-] [NAV-NOTICE] Navigasi shortlink hop #{hop}: {nav_e}")
                    page = enforce_single_target_tab(context, page, target_url, wait_seconds=2, worker_id=worker_id)
                    page = dismiss_vignette_if_present(page, dwell_seconds=4, worker_id=worker_id)
                else:
                    visited_urls.add(page.url)

                current_post_url = page.url
                print(f"\n{tag} >>> 📖 [Shortlink {hop}/{max_pages}] Membaca artikel gateway: {current_post_url} <<<")

                # Cek apakah artikel memiliki alur 4-Layer Shortlink Gateway
                if is_shortlink_gateway_present(page):
                    page = traverse_shortlink_flow(page, context, target_url, config, worker_id=worker_id)
                else:
                    # Fallback jika halaman artikel biasa tanpa gateway
                    page = human_scroll(page, config, context=context, target_url=target_url, max_scroll_steps=random.randint(6, 10), worker_id=worker_id, label="artikel")
                    post_dwell = random.randint(dwell_min, dwell_max)
                    page = human_dwell(page, context, target_url, post_dwell, worker_id=worker_id, label="artikel")

                print(f"{tag} [+] Shortlink #{hop}/{max_pages} selesai dinikmati.")

                # Selesai jika ini adalah hop terakhir
                if hop >= max_pages or page.is_closed():
                    break

        except Exception as e:
            session_failed = True
            err_msg = str(e).splitlines()[0] if str(e) else "Unknown error"
            # Hanya error yang jelas berasal dari proksi yang dihitung sebagai
            # kegagalan proksi. Timeout/reset generik bisa berasal dari target,
            # jadi tidak boleh membunuh proksi yang sehat.
            is_proxy_err = any(code in err_msg for code in [
                "ERR_PROXY", "ERR_TUNNEL", "ERR_SOCKS",
                "ERR_PROXY_CONNECTION_FAILED", "ERR_PROXY_AUTH_UNSUPPORTED",
                "ERR_INVALID_AUTH_CREDENTIALS",
            ])
            if is_proxy_err and proxy:
                print(f"{tag} [-] Proksi Timeout/Down saat navigasi: {err_msg}")
                if proxy_manager:
                    if proxy_idx is not None:
                        proxy_manager.mark_dead(
                            proxy_idx,
                            reason="Navigation Timeout / Proxy Failure",
                            target_url=target_url,
                        )
                    else:
                        proxy_manager.remove_dead_proxy(
                            proxy,
                            reason="Navigation Timeout / Proxy Failure",
                            target_url=target_url,
                        )
            else:
                print(f"{tag} [-] Error during navigation: {err_msg}")
        finally:
            print(f"{tag} [*] Closing browser session cleanly...")
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if proxy_manager and proxy_idx is not None:
                if not session_failed:
                    proxy_manager.report_session_success(proxy_idx, worker_id=worker_id)
                proxy_manager.release_proxy(proxy_idx, worker_id=worker_id)
            print(f"{tag} [+] Total Session Dwell Time: {time.time() - start_time:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Blog Viewability & Ad Impression Automation Suite")
    parser.add_argument("--local", action="store_true", help="Run against localhost:3000 instead of production domain")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--proxy-index", type=int, default=None, help="Index of specific proxy in proxies list")
    parser.add_argument("--no-proxy", action="store_true", help="Run directly without proxy")
    parser.add_argument("--sessions", type=int, default=1, help="Number of sequential sessions to execute")
    parser.add_argument("--concurrency", "-c", type=int, default=1, help="Number of browser instances to run simultaneously")
    parser.add_argument("--pages-per-session", type=int, default=None, help="Number of blog articles/pages to explore in one session")
    parser.add_argument("--return-home", action="store_true", help="Return to homepage between articles like a real human reader")
    parser.add_argument("--slug", type=str, default="", help="Specific article slug to open (e.g. the-tactile-terminal-command-line-aesthetics)")
    parser.add_argument("--loop", action="store_true", help="Run continuously in automated cycles (Unlimited loop)")
    args = parser.parse_args()

    config = load_config()

    base_url = config.get("local_test_url", "http://localhost:3000") if args.local else config.get("target_base_url", "https://read.riztama.my.id")
    clean_base = base_url.rstrip("/")
    if args.slug:
        slug_clean = args.slug.strip()
        target_url = f"{clean_base}/post/{slug_clean}" + ("" if "?step=" in slug_clean else "?step=1")
    else:
        chosen_slug = random.choice(DEFAULT_SHORTLINK_SLUGS)
        target_url = f"{clean_base}/post/{chosen_slug}?step=1"

    proxy_file = resolve_proxy_path(config.get("proxy_source", "automation/proxies.json"))
    raw_proxies = [] if args.no_proxy else load_proxies(proxy_file)
    concurrency = max(1, args.concurrency)
    proxy_manager = ProxyManager(proxy_file_path=proxy_file, proxies=raw_proxies, target_concurrency=concurrency) if (raw_proxies and not args.no_proxy) else None

    max_pages = args.pages_per_session if args.pages_per_session is not None else config.get("max_pages_per_session", 3)
    return_home = args.return_home or config.get("return_home_between_posts", True)

    print("=" * 65)
    print("      CHRONICLE TRAFFIC BOT & AD VIEWABILITY ENGINE")
    print("=" * 65)
    print(f"[*] Target: {target_url}")
    print(f"[*] Total Proxies Available: {len(raw_proxies)}")
    print(f"[*] Real-time Proxy Guard: {'ACTIVE (Auto-prune dead proxies)' if proxy_manager else 'DISABLED'}")
    print(f"[*] Headless Mode: {args.headless}")
    print(f"[*] Total Sessions per Cycle: {args.sessions}")
    print(f"[*] Parallel Browsers (Concurrency): {concurrency}")
    print(f"[*] Pages per Session: {max_pages} (Return Home: {return_home})")
    print(f"[*] Non-Stop Loop Mode: {args.loop}")
    print("=" * 65)

    try:
        cycle_num = 1

        while True:
            if args.loop:
                print(f"\n{'='*20} 🔄 MEMULAI PUTARAN KE-{cycle_num} {'='*20}\n")

            if concurrency <= 1:
                for i in range(args.sessions):
                    print(f"\n>>> Running Session {i + 1} of {args.sessions} <<<")
                    selected_proxy = None
                    selected_proxy_idx = None

                    if proxy_manager:
                        selected_proxy, selected_proxy_idx = proxy_manager.get_valid_proxy(
                            target_url=target_url,
                            preferred_index=args.proxy_index if (args.proxy_index is not None and 0 <= args.proxy_index < len(proxy_manager.proxies)) else None,
                            worker_id=1
                        )
                        if not selected_proxy and not args.no_proxy and raw_proxies:
                            print("[!] 🛑 [ANTI-LEAK GUARD] Seluruh proksi residensial mati! Sesi DIBATALKAN demi keamanan untuk mencegah kebocoran IP lokal asli ke jaringan iklan.")
                            break

                    run_single_session_safe(
                        target_url=target_url,
                        use_proxy=(not args.no_proxy and bool(raw_proxies)),
                        proxy=selected_proxy,
                        proxy_idx=selected_proxy_idx,
                        headless=args.headless,
                        config=config,
                        max_pages=max_pages,
                        return_home=return_home,
                        worker_id=1,
                        proxy_manager=proxy_manager
                    )

                    if i < args.sessions - 1:
                        cooldown = random.randint(5, 12)
                        print(f"[*] Cooling down for {cooldown}s before next session...")
                        time.sleep(cooldown)
            else:
                print(f"\n[*] 🚀 Meluncurkan {args.sessions} sesi dengan {concurrency} browser paralel sekaligus (Browser #1 s/d Browser #{concurrency})...\n")

                session_counter_lock = threading.Lock()
                current_session = 0

                def worker_loop(worker_id: int):
                    nonlocal current_session
                    # Jeda awal bertingkat saat peluncuran
                    time.sleep((worker_id - 1) * 0.3)

                    while True:
                        with session_counter_lock:
                            if current_session >= args.sessions:
                                break
                            current_session += 1
                            session_num = current_session

                        selected_proxy = None
                        selected_proxy_idx = None
                        if proxy_manager:
                            selected_proxy, selected_proxy_idx = proxy_manager.get_valid_proxy(
                                target_url=target_url,
                                preferred_index=args.proxy_index if (args.proxy_index is not None and 0 <= args.proxy_index < len(proxy_manager.proxies)) else None,
                                worker_id=worker_id
                            )
                            if not selected_proxy and not args.no_proxy and raw_proxies:
                                print(f"[B{worker_id}] 🛑 [ANTI-LEAK GUARD] Proksi pool habis/mati! Sesi dibatalkan demi keamanan IP asli Anda.")
                                break

                        print(f"[B{worker_id}] >>> Running Session {session_num} of {args.sessions} <<<")

                        run_single_session_safe(
                            target_url=target_url,
                            use_proxy=(not args.no_proxy and bool(raw_proxies)),
                            proxy=selected_proxy,
                            proxy_idx=selected_proxy_idx,
                            headless=args.headless,
                            config=config,
                            max_pages=max_pages,
                            return_home=return_home,
                            worker_id=worker_id,
                            proxy_manager=proxy_manager
                        )

                        with session_counter_lock:
                            has_more = current_session < args.sessions
                        if has_more:
                            cooldown = random.randint(3, 7)
                            print(f"[B{worker_id}] [*] Cooling down for {cooldown}s before next session...")
                            time.sleep(cooldown)

                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    futures = [executor.submit(worker_loop, w_id) for w_id in range(1, concurrency + 1)]
                    for f in as_completed(futures):
                        try:
                            f.result()
                        except Exception as e:
                            print(f"[-] Worker pool notice: {e}")

            if not args.loop:
                print("\n[✓] All automation sessions completed successfully.")
                break

            cycle_num += 1
            print(f"\n[✓] Putaran {cycle_num - 1} selesai. Istirahat 15 detik sebelum putaran ke-{cycle_num}...\n")
            time.sleep(15)
    except KeyboardInterrupt:
        print("\n\n[*] Bot execution interrupted by user (Ctrl+C). Clean shutdown.")
        sys.exit(0)


if __name__ == "__main__":
    main()
