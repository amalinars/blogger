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
from urllib.parse import urlparse
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
        "smartlink_click_chance": 0.04,
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

        # Tutup semua tab iklan
        if ad_pages:
            if not is_repeated:
                print(f"{tag} [*] [TAB-GUARD] Terdeteksi {len(ad_pages)} tab iklan di luar domain target!")

            if wait_seconds > 0:
                time.sleep(wait_seconds)

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
            visited_urls = set()
            visited_urls.add(target_url)

            # Gunakan Organic Referer Engine
            referer = get_organic_referer(config.get("organic_referer_pool")) if config.get("use_organic_referers", True) else None
            ref_label = referer if referer else "Direct (None)"
            print(f"{tag} [*] Navigating to {target_url} (Referer: {ref_label})...")
            if referer:
                page.goto(target_url, referer=referer, wait_until="domcontentloaded", timeout=60000)
            else:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(random.uniform(2.5, 4.0))

            # Trigger klik fisik koordinat awal (memicu popunder/ad overlay Adsterra di beranda jika ada)
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

            # Enforce single tab guard jika popunder terbuka
            page = enforce_single_target_tab(context, page, target_url, wait_seconds=2, worker_id=worker_id)

            # =========================================================
            # TAHAP 1: EKSPLORASI BERANDA (JANGAN LANGSUNG BUKA ARTIKEL)
            # =========================================================
            is_initial_home = "/post/" not in page.url
            if is_initial_home:
                # Scroll santai beranda agar seluruh posisi iklan feed, header, dan sidebar terlihat
                page = human_scroll(page, config, context=context, target_url=target_url, max_scroll_steps=random.randint(5, 8), worker_id=worker_id, label="beranda")

                # Interaksi klik smartlink alami di Beranda (rasio wajar ~4%)
                smartlink_chance = config.get("smartlink_click_chance", 0.04)
                if random.random() < smartlink_chance:
                    print(f"{tag} [*] 🎯 [SMARTLINK BERANDA] Melakukan interaksi klik alami di Beranda...")
                    try:
                        smartlink_btn = page.query_selector("a[href*='profitableratecpmnetwork.com'], a[href*='araplhn.org'], a[href*='asiafilm.org'], aside a, .smartlink-cta, header a")
                        if smartlink_btn:
                            page = handle_smartlink_click(context, page, smartlink_btn, target_url, worker_id=worker_id)
                    except Exception as e:
                        print(f"{tag} [-] [HOLD/ERROR] Smartlink beranda notice: {e}")

                # Dwell time beranda terukur (~16-24s, cukup untuk viewability & auto-refresh)
                home_dwell = random.randint(16, 24)
                page = human_dwell(page, context, target_url, home_dwell, worker_id=worker_id, label="beranda")

                print(f"{tag} [✓] [BERANDA] Seluruh iklan di Beranda telah ter-render & tercatat impresi. Siap memilih artikel!")

            # =========================================================
            # TAHAP 2: EKSPLORASI ARTIKEL BERTINGKAT (Hop 1 .. max_pages)
            # =========================================================
            smartlink_chance = config.get("smartlink_click_chance", 0.04)

            for hop in range(1, max_pages + 1):
                if page.is_closed():
                    break

                # Navigasi ke artikel yang belum dikunjungi dari Beranda
                print(f"\n{tag} [*] ➡️ Menyiapkan navigasi ke Artikel {hop} dari total {max_pages} artikel...")
                try:
                    all_post_links = page.query_selector_all("a[href^='/post/']")
                    candidates = []
                    for pl in all_post_links:
                        href = pl.get_attribute("href")
                        if href and href not in visited_urls:
                            candidates.append((pl, href))

                    # Jika DOM tidak menampilkan artikel (terhalang overlay/redirect)
                    if not candidates and not all_post_links:
                        print(f"{tag} [!] [HOLD/RECOVERY] Link artikel tidak terdeteksi di DOM (mungkin tertutup overlay). Memuat ulang beranda: {target_url}...")
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                            time.sleep(2.0)
                            all_post_links = page.query_selector_all("a[href^='/post/']")
                            for pl in all_post_links:
                                href = pl.get_attribute("href")
                                if href and href not in visited_urls:
                                    candidates.append((pl, href))
                        except Exception as reload_err:
                            print(f"{tag} [-] [HOLD/ERROR] Gagal memuat ulang beranda: {reload_err}")

                    if not candidates and all_post_links:
                        sel = random.choice(all_post_links)
                        candidates = [(sel, sel.get_attribute("href"))]

                    if candidates:
                        chosen_el, chosen_href = random.choice(candidates[:6])
                        visited_urls.add(chosen_href)
                        print(f"{tag} [*] ➡️ Memilih artikel #{hop}: {chosen_href}")

                        # Klik alami masuk ke artikel (sering memicu redirect/popunder smartlink)
                        click_element_naturally(page, chosen_el, worker_id=worker_id)
                        page = enforce_single_target_tab(context, page, target_url, wait_seconds=2, worker_id=worker_id)

                        # Verifikasi apakah sudah masuk ke artikel target
                        if not page.is_closed() and chosen_href not in page.url:
                            # Jika klik tertahan overlay iklan/popunder, navigasi langsung ke URL artikel
                            from urllib.parse import urljoin
                            full_article_url = urljoin(target_url, chosen_href)
                            print(f"{tag} [*] ➡️ [HOLD/RECOVERY] Klik artikel tertahan overlay iklan. Memuat URL artikel langsung: {full_article_url}...")
                            try:
                                page.goto(full_article_url, wait_until="domcontentloaded", timeout=25000)
                            except Exception as nav_e:
                                print(f"{tag} [-] [NAV-NOTICE] Navigasi fallback artikel: {nav_e}")

                        page = enforce_single_target_tab(context, page, target_url, wait_seconds=1.5, worker_id=worker_id)
                    else:
                        # Fallback jika DOM sama sekali tidak memuat link artikel: navigasi langsung ke slug artikel sah
                        known_slugs = [
                            "/post/in-defense-of-deliberate-slowness",
                            "/post/mechanical-sympathy-in-the-browser-runtime",
                            "/post/lost-art-of-digital-craftsmanship",
                            "/post/the-tactile-terminal-command-line-aesthetics",
                            "/post/the-death-of-digital-clutter-brutalist-clarity"
                        ]
                        unvisited = [s for s in known_slugs if s not in visited_urls]
                        fallback_slug = random.choice(unvisited if unvisited else known_slugs)
                        visited_urls.add(fallback_slug)
                        from urllib.parse import urljoin
                        full_article_url = urljoin(target_url, fallback_slug)
                        print(f"{tag} [*] ➡️ [NAV-FALLBACK] Navigasi langsung ke artikel blog: {fallback_slug}...")
                        try:
                            page.goto(full_article_url, wait_until="domcontentloaded", timeout=25000)
                        except Exception as nav_e:
                            print(f"{tag} [-] [NAV-NOTICE] Navigasi fallback artikel: {nav_e}")
                        page = enforce_single_target_tab(context, page, target_url, wait_seconds=1.5, worker_id=worker_id)
                except Exception as e:
                    print(f"{tag} [-] [HOLD/ERROR] Navigasi artikel notice: {e}")
                    break

                current_post_url = page.url
                print(f"\n{tag} >>> 📖 [Artikel {hop}/{max_pages}] Membaca artikel: {current_post_url} <<<")

                # A. Di artikel scroll natural bertahap (smooth & gesit)
                page = human_scroll(page, config, context=context, target_url=target_url, max_scroll_steps=random.randint(6, 10), worker_id=worker_id, label="artikel")

                # B. Trigger / Klik Smartlink CTA di artikel (seringkan interaksi klik manusia)
                if random.random() < smartlink_chance:
                    print(f"{tag} [*] 🎯 [SMARTLINK] Engaging with Smartlink CTA pada Artikel {hop} (Tercatat klik advertiser)...")
                    try:
                        smartlink_btn = page.query_selector("a[href*='profitableratecpmnetwork.com'], a[href*='araplhn.org'], a[href*='asiafilm.org'], aside a, .smartlink-cta, a[target='_blank']")
                        if smartlink_btn:
                            page = handle_smartlink_click(context, page, smartlink_btn, target_url, worker_id=worker_id)
                    except Exception as e:
                        print(f"{tag} [-] [HOLD/ERROR] Smartlink article notice: {e}")

                # C. Dwell time santai di artikel (membaca santai & scrolling naik-turun menunggu auto-refresh iklan 35s)
                post_dwell = random.randint(dwell_min, dwell_max)
                page = human_dwell(page, context, target_url, post_dwell, worker_id=worker_id, label="artikel")

                print(f"{tag} [+] Artikel {hop}/{max_pages} selesai dinikmati.")

                # Selesai jika ini adalah hop terakhir
                if hop >= max_pages or page.is_closed():
                    break

                # =========================================================
                # TAHAP 3: KEMBALI KE BERANDA (RETURN HOME) ANTAR ARTIKEL
                # =========================================================
                if return_home:
                    try:
                        print(f"\n{tag} [*] 🏠 Pola Pembaca Organik: Kembali ke Beranda sebelum memilih artikel baru...")
                        home_link = page.query_selector(
                            "a[href='/'], header a[href='/'], a:has-text('CHRONICLE'), a:has-text('Return to Journal Frontpage')"
                        )
                        if home_link:
                            click_element_naturally(page, home_link, worker_id=worker_id)
                            page = enforce_single_target_tab(context, page, target_url, wait_seconds=2, worker_id=worker_id)
                            # Verifikasi apakah sudah di beranda
                            if not page.is_closed() and "/post/" in page.url:
                                print(f"{tag} [*] [HOLD/RECOVERY] Klik beranda tertahan overlay, memuat URL beranda langsung: {target_url}...")
                                try:
                                    page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                                except Exception as he:
                                    print(f"{tag} [-] [NAV-NOTICE] Navigasi beranda fallback: {he}")
                            else:
                                try:
                                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                                except Exception:
                                    pass
                            time.sleep(random.uniform(2.0, 3.5))
                        else:
                            print(f"{tag} [*] 🏠 Memuat URL beranda langsung: {target_url}...")
                            try:
                                page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                            except Exception as he:
                                print(f"{tag} [-] [NAV-NOTICE] Navigasi beranda fallback: {he}")
                            time.sleep(random.uniform(2.0, 3.5))

                        # Di beranda santai scroll lagi sampai semua iklan terlihat
                        print(f"{tag} [*] 📜 [BERANDA FEED] Menjelajahi kembali feed Beranda santai agar seluruh posisi iklan ter-refresh...")
                        page = human_scroll(page, config, context=context, target_url=target_url, max_scroll_steps=random.randint(4, 7), worker_id=worker_id, label="beranda")

                        # Dwell santai di beranda antar artikel (~12 - 18 detik dengan scrolling naik-turun)
                        mid_dwell = random.randint(12, 18)
                        page = human_dwell(page, context, target_url, mid_dwell, worker_id=worker_id, label="beranda")

                        print(f"{tag} [✓] Iklan di Beranda siap & ter-refresh. Bersiap memilih artikel selanjutnya...")
                    except Exception as e:
                        print(f"{tag} [-] [RETURN-HOME-NOTICE] Notice returning home: {e}")

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
    if args.slug:
        target_url = f"{base_url}/post/{args.slug}"
    else:
        target_url = base_url

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
