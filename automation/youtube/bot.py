#!/usr/bin/env python3
"""
automation.youtube.bot - YouTube Organic View & Engagement Automation
Reuses automation.core for high-stealth Playwright execution, residential proxy rotation,
and natural human interaction physics (randomized watch time, organic scrolling).
"""

import sys
import json
import time
import random
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

try:
    from automation.core.browser import build_browser_args, format_proxy_dict, launch_browser, create_stealth_context
    from automation.core.proxy_manager import ProxyManager, load_proxies
    from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause
except ImportError:
    sys.path.insert(0, str(PROJECT_ROOT))
    from automation.core.browser import build_browser_args, format_proxy_dict, launch_browser, create_stealth_context
    from automation.core.proxy_manager import ProxyManager, load_proxies
    from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause


def load_config() -> dict:
    cfg_file = BASE_DIR / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "target_video_url": "https://www.youtube.com",
        "search_keywords": ["programming tutorial"],
        "watch_duration": {"min_seconds": 60, "max_seconds": 180},
        "headless": False,
        "concurrency": 1
    }


def watch_video(page, target_url: str, watch_duration: int = 60, tag: str = "[YT]"):
    """
    Menonton video YouTube secara alami:
    - Membuka URL video
    - Melewati cookie consent / pop-up jika muncul
    - Memastikan video play
    - Sesekali scroll santai ke kolom komentar / rekomendasi
    - Menunggu hingga durasi watch time terpenuhi
    """
    print(f"{tag} [*] Membuka video: {target_url}...")
    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    random_pause(2.0, 4.0)

    # 1. Tangani cookie dialog jika muncul
    try:
        consent_btn = page.query_selector("button[aria-label*='Accept'], button[aria-label*='Setuju'], button:has-text('Accept all'), button:has-text('I agree')")
        if consent_btn:
            print(f"{tag} [*] Menyetujui cookie dialog YouTube...")
            consent_btn.click()
            random_pause(1.5, 3.0)
    except Exception:
        pass

    # 2. Coba klik play jika video belum autoplay
    try:
        play_btn = page.query_selector("button.ytp-play-button")
        if play_btn:
            aria_label = play_btn.get_attribute("aria-label") or ""
            if "Play" in aria_label or "Putar" in aria_label:
                print(f"{tag} [*] Mengklik tombol play video...")
                play_btn.click()
    except Exception:
        pass

    # 3. Nonton video dengan scrolling alami sesekali
    print(f"{tag} 🎬 Menonton video selama {watch_duration} detik...")
    start_time = time.time()
    end_time = start_time + watch_duration
    last_scroll = time.time()

    while time.time() < end_time and not page.is_closed():
        now = time.time()
        # Setiap 15-25 detik, scroll sedikit untuk melihat deskripsi / komentar
        if now - last_scroll > random.uniform(15.0, 25.0):
            direction = random.choice([1, 1, -1]) # Lebih sering ke bawah
            scroll_amt = random.randint(150, 350) * direction
            smooth_scroll(page, scroll_amt, steps=random.randint(6, 12))
            last_scroll = now

            # Gerakkan mouse santai
            natural_mouse_move(page, random.randint(300, 800), random.randint(300, 600), steps=8)

        time.sleep(1.0)

    print(f"{tag} ✅ Selesai menonton ({watch_duration}s).")


def run_youtube_session(
    target_url: str,
    proxy: dict = None,
    headless: bool = False,
    watch_seconds: int = 60,
    worker_id: int = 1,
):
    tag = f"[YT-W{worker_id}]"
    print("\n" + "=" * 60)
    print(f"{tag} [*] Target YouTube: {target_url}")
    if proxy:
        print(f"{tag} [*] Proksi: {proxy.get('host')}:{proxy.get('port')} (Geo: {proxy.get('country', 'Unknown')})")
    else:
        print(f"{tag} [*] Proksi: Direct (Tanpa Proksi)")
    print(f"{tag} [*] Rencana Durasi Tonton: {watch_seconds} detik")
    print("=" * 60)

    with sync_playwright() as p:
        browser_args = build_browser_args(
            window_size=(1280, 800),
            extra_args=["--autoplay-policy=no-user-gesture-required"]
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
        try:
            watch_video(page, target_url=target_url, watch_duration=watch_seconds, tag=tag)
        except Exception as e:
            print(f"{tag} [-] Sesi YouTube error: {e}")
        finally:
            context.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="YouTube Automation Engine powered by automation.core")
    parser.add_argument("--url", type=str, default="", help="Target YouTube video URL")
    parser.add_argument("--watch-seconds", type=int, default=60, help="Durasi menonton video per sesi")
    parser.add_argument("--sessions", type=int, default=1, help="Total sesi kunjungan")
    parser.add_argument("--headless", action="store_true", help="Jalankan di balik layar tanpa jendela")
    parser.add_argument("--no-proxy", action="store_true", help="Gunakan koneksi internet langsung")
    args = parser.parse_args()

    cfg = load_config()
    target_url = args.url or cfg.get("target_video_url", "https://www.youtube.com")
    headless = args.headless or cfg.get("headless", False)
    watch_seconds = args.watch_seconds

    proxies = []
    if not args.no_proxy:
        proxies = load_proxies(cfg.get("proxy_source", "automation/proxies.json"))
        proxy_mgr = ProxyManager(proxies=proxies) if proxies else None
    else:
        proxy_mgr = None

    for i in range(args.sessions):
        print(f"\n>>> Meluncurkan Sesi YouTube {i + 1} dari {args.sessions} <<<")
        selected_proxy = None
        selected_proxy_idx = None
        if proxy_mgr:
            selected_proxy, selected_proxy_idx = proxy_mgr.get_valid_proxy(target_url=target_url, worker_id=1)
            if selected_proxy is None:
                print("[!] [ANTI-LEAK GUARD] Tidak ada proksi valid. Sesi YouTube dibatalkan.")
                break

        try:
            run_youtube_session(
                target_url=target_url,
                proxy=selected_proxy,
                headless=headless,
                watch_seconds=watch_seconds,
                worker_id=1,
            )
        finally:
            if proxy_mgr and selected_proxy_idx is not None:
                proxy_mgr.release_proxy(selected_proxy_idx, worker_id=1)


if __name__ == "__main__":
    main()
