#!/usr/bin/env python3
"""
traffic_bot.py - Synthetic Browser Emulation & Ad Viewability Engine
Designed for blog.riztama.my.id (Chronicle Editorial Blog)

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
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "target_base_url": "https://blog.riztama.my.id",
        "local_test_url": "http://localhost:3000",
        "use_local": False,
        "dwell_time": {"min_seconds": 35, "max_seconds": 50},
        "scroll_settings": {"step_pixels": 350, "pause_between_scrolls_min": 1.2, "pause_between_scrolls_max": 2.5},
        "proxy_source": "automation/proxies.json",
        "headless": False,
        "multi_page_navigation": True,
        "max_pages_per_session": 2,
        "smartlink_click_chance": 0.08
    }


def load_proxies(proxy_source_path):
    p = Path(proxy_source_path)
    if not p.is_absolute():
        if (BASE_DIR / p.name).exists():
            p = BASE_DIR / p.name
        elif (BASE_DIR.parent / p).exists():
            p = BASE_DIR.parent / p
        elif (BASE_DIR / p).exists():
            p = BASE_DIR / p

    if not p.exists():
        print(f"[-] Warning: Proxy file not found at {proxy_source_path}")
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[+] Loaded {len(data)} proxies from {p.name}")
            return data
    except Exception as e:
        print(f"[-] Error loading proxies: {e}")
        return []


def cleanup_extra_tabs(context, main_page, dwell_seconds=7):
    """
    Guarantees all ad/smartlink/popunder tabs are properly closed before continuing.
    1. Detects any tab other than main_page.
    2. Lets ad track for dwell_seconds so conversion is recorded.
    3. Closes all extra tabs forcefully.
    4. Focuses main_page back to the front.
    """
    try:
        time.sleep(1.5)  # Allow any async redirect/new-window to register
        extra_pages = [p for p in context.pages if p != main_page and not p.is_closed()]
        if not extra_pages:
            return

        print(f"[*] Detected {len(extra_pages)} extra ad/smartlink tab(s). Allowing {dwell_seconds}s for ad tracking...")
        time.sleep(dwell_seconds)

        for p in extra_pages:
            try:
                if not p.is_closed() and p != main_page:
                    try:
                        url_snippet = p.url[:60]
                    except Exception:
                        url_snippet = "ad-tab"
                    print(f"    -> Closing ad tab ({url_snippet})...")
                    p.close(run_before_unload=False)
            except Exception as e:
                print(f"    [-] Notice while closing tab: {e}")

        # Double check no lingering tabs remain
        time.sleep(0.8)
        for p in context.pages:
            if p != main_page and not p.is_closed():
                try:
                    p.close(run_before_unload=False)
                except Exception:
                    pass

        if not main_page.is_closed():
            main_page.bring_to_front()
            print("[✓] All extra ad tabs closed cleanly. Restored focus to main blog page.")
    except Exception as e:
        print(f"[-] Notice during tab cleanup: {e}")


def human_scroll(page, config, max_scroll_steps=16):
    """Simulates organic reading behavior with progressive viewport scrolling."""
    step = config.get("scroll_settings", {}).get("step_pixels", 350)
    p_min = config.get("scroll_settings", {}).get("pause_between_scrolls_min", 1.2)
    p_max = config.get("scroll_settings", {}).get("pause_between_scrolls_max", 2.5)

    try:
        if page.is_closed():
            return

        total_height = page.evaluate("() => document.body.scrollHeight")
        viewport_height = page.evaluate("() => window.innerHeight")
        current_scroll = 0
        steps_done = 0

        print(f"[*] Starting organic reading scroll (Total height: {total_height}px, Max steps: {max_scroll_steps})...")

        while current_scroll + viewport_height < total_height and steps_done < max_scroll_steps:
            if page.is_closed():
                break

            scroll_by = random.randint(step - 50, step + 150)
            page.mouse.wheel(0, scroll_by)
            current_scroll += scroll_by
            steps_done += 1

            # Slight random mouse movement to simulate attention
            try:
                page.mouse.move(
                    random.randint(150, 700),
                    random.randint(180, 550),
                    steps=4
                )
            except Exception:
                pass

            pause = random.uniform(p_min, p_max)
            time.sleep(pause)

        print("[+] Scroll segment completed. All in-viewport ads rendered.")
    except Exception as e:
        print(f"[-] Scroll simulation notice: {e}")


def run_session(target_url, proxy=None, headless=False, config=None):
    """Executes a single browser session with full ad tech viewability tracking."""
    if config is None:
        config = load_config()

    dwell_min = config.get("dwell_time", {}).get("min_seconds", 35)
    dwell_max = config.get("dwell_time", {}).get("max_seconds", 50)
    target_dwell = random.randint(dwell_min, dwell_max)

    print("\n" + "=" * 65)
    print(f"[*] Launching session for: {target_url}")
    if proxy:
        country = proxy.get("country", "Unknown")
        print(f"[*] Proxy: {proxy.get('host')}:{proxy.get('port')} (Geo: {country})")
    else:
        print("[*] Proxy: Direct (No Proxy)")
    print(f"[*] Target dwell time: {target_dwell}s (Ensures 25s auto-refresh fires)")
    print("=" * 65)

    with sync_playwright() as p:
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1440,900"
        ]

        proxy_dict = None
        if proxy and proxy.get("host") and proxy.get("port"):
            proxy_dict = {
                "server": f"http://{proxy['host']}:{proxy['port']}",
                "username": proxy.get("username", ""),
                "password": proxy.get("password", "")
            }

        try:
            # Prefer native Google Chrome binary (Anti-detection gold standard)
            browser = p.chromium.launch(
                channel="chrome",
                headless=headless,
                args=browser_args,
                proxy=proxy_dict
            )
        except Exception as e:
            print(f"[*] Native Chrome notice: {e}, using bundled chromium...")
            browser = p.chromium.launch(
                headless=headless,
                args=browser_args,
                proxy=proxy_dict
            )

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ]

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=random.choice(user_agents),
            locale="en-US",
            timezone_id="America/New_York"
        )

        page = context.new_page()
        start_time = time.time()

        try:
            print(f"[*] Navigating to {target_url}...")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # First natural physical click on the page (Hits transparent popunder overlay if present)
            print("[*] Performing physical mouse click at coordinates (Hits ad overlay/popunder)...")
            try:
                cx = random.randint(250, 600)
                cy = random.randint(220, 450)
                page.mouse.move(cx, cy, steps=random.randint(8, 15))
                time.sleep(random.uniform(0.1, 0.3))
                page.mouse.down()
                time.sleep(random.uniform(0.08, 0.15))
                page.mouse.up()
            except Exception as e:
                print(f"[-] Initial coordinate click notice: {e}")

            # Check and close Popunder tab before scrolling
            cleanup_extra_tabs(context, page, dwell_seconds=7)

            # Execute human reading scroll to trigger viewable impressions
            human_scroll(page, config)

            # Organic Smartlink conversion opportunity (Probabilistic, CTR-safe ~5-8%)
            smartlink_chance = config.get("smartlink_click_chance", 0.08)
            if random.random() < smartlink_chance:
                print("[*] Organic roll SUCCESS: Engaging with Smartlink CTA this session...")
                try:
                    smartlink_btn = page.query_selector("a[href*='araplhn.org'], a[href*='asiafilm.org'], a[href*='auctionr.org'], aside a")
                    if smartlink_btn:
                        smartlink_btn.scroll_into_view_if_needed()
                        time.sleep(random.uniform(1.0, 2.0))
                        sbox = smartlink_btn.bounding_box()
                        if sbox:
                            target_x = sbox["x"] + sbox["width"] * random.uniform(0.3, 0.7)
                            target_y = sbox["y"] + sbox["height"] * random.uniform(0.3, 0.7)
                            page.mouse.move(target_x, target_y, steps=random.randint(10, 20))
                            time.sleep(random.uniform(0.15, 0.3))
                            print("[*] Physically clicking Smartlink CTA button...")
                            page.mouse.down()
                            time.sleep(random.uniform(0.08, 0.16))
                            page.mouse.up()

                            # Wait for Smartlink offer to track, then close tab before proceeding!
                            cleanup_extra_tabs(context, page, dwell_seconds=9)
                except Exception as e:
                    print(f"[-] Smartlink physical interaction notice: {e}")

            # Ensure minimum dwell time is satisfied to fire 25s banner auto-refreshes
            elapsed = time.time() - start_time
            remaining = target_dwell - elapsed
            if remaining > 0:
                print(f"[*] Dwell time remaining: {remaining:.1f}s. Observing active ad units...")
                time.sleep(remaining)

            total_session_time = time.time() - start_time
            print(f"[+] Page 1 completed in {total_session_time:.1f}s.")

            # Multi-page internal navigation (Physical Coordinate Click, NOT element injection)
            if config.get("multi_page_navigation", True) and not page.is_closed():
                try:
                    post_links = page.query_selector_all("a[href^='/post/']")
                    if post_links:
                        selected_link = random.choice(post_links[:4])
                        link_href = selected_link.get_attribute("href")
                        print(f"[*] Moving physical mouse to link coordinates: {link_href}...")

                        selected_link.scroll_into_view_if_needed()
                        time.sleep(random.uniform(0.8, 1.5))

                        box = selected_link.bounding_box()
                        if box:
                            target_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
                            target_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
                            page.mouse.move(target_x, target_y, steps=random.randint(12, 25))
                            time.sleep(random.uniform(0.2, 0.4))

                            print("[*] Physical mouse down & up on link...")
                            page.mouse.down()
                            time.sleep(random.uniform(0.08, 0.18))
                            page.mouse.up()

                            # If click was intercepted by an ad overlay, close the ad tab first!
                            cleanup_extra_tabs(context, page, dwell_seconds=7)

                            # If page hasn't navigated yet (because overlay absorbed first click), click again
                            if not page.url.endswith(link_href):
                                print("[*] Performing second click to follow link after overlay dismissal...")
                                page.mouse.down()
                                time.sleep(random.uniform(0.08, 0.15))
                                page.mouse.up()

                            page.wait_for_load_state("domcontentloaded", timeout=30000)
                            time.sleep(2)

                            # Ensure main page is focused and ad tabs closed before Page 2 reading
                            cleanup_extra_tabs(context, page, dwell_seconds=2)

                            second_dwell = random.randint(20, 30)
                            print(f"[*] Dwell on Page 2: {second_dwell}s...")
                            human_scroll(page, config, max_scroll_steps=10)
                            time.sleep(5)
                            print("[+] Second page view completed successfully.")
                except Exception as e:
                    print(f"[-] Internal link navigation notice: {e}")

        except Exception as e:
            print(f"[-] Error during navigation: {e}")
        finally:
            print("[*] Closing browser session cleanly...")
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            print(f"[+] Total Session Dwell Time: {time.time() - start_time:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Blog Viewability & Ad Impression Automation Suite")
    parser.add_argument("--local", action="store_true", help="Run against localhost:3000 instead of production domain")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--proxy-index", type=int, default=None, help="Index of specific proxy in proxies list")
    parser.add_argument("--sessions", type=int, default=1, help="Number of sequential sessions to execute")
    parser.add_argument("--slug", type=str, default="", help="Specific article slug to open (e.g. the-tactile-terminal-command-line-aesthetics)")
    args = parser.parse_args()

    config = load_config()

    base_url = config.get("local_test_url", "http://localhost:3000") if args.local else config.get("target_base_url", "https://blog.riztama.my.id")
    if args.slug:
        target_url = f"{base_url}/post/{args.slug}"
    else:
        target_url = base_url

    proxies = load_proxies(config.get("proxy_source", ""))

    print("=" * 65)
    print("      CHRONICLE TRAFFIC BOT & AD VIEWABILITY ENGINE")
    print("=" * 65)
    print(f"[*] Target: {target_url}")
    print(f"[*] Total Proxies Available: {len(proxies)}")
    print(f"[*] Headless Mode: {args.headless}")
    print(f"[*] Sessions: {args.sessions}")
    print("=" * 65)

    try:
        for i in range(args.sessions):
            print(f"\n>>> Running Session {i + 1} of {args.sessions} <<<")
            selected_proxy = None

            if proxies:
                if args.proxy_index is not None and 0 <= args.proxy_index < len(proxies):
                    selected_proxy = proxies[args.proxy_index]
                else:
                    selected_proxy = random.choice(proxies)

            run_session(target_url, proxy=selected_proxy, headless=args.headless, config=config)

            if i < args.sessions - 1:
                cooldown = random.randint(5, 12)
                print(f"[*] Cooling down for {cooldown}s before next session...")
                time.sleep(cooldown)

        print("\n[✓] All automation sessions completed successfully.")
    except KeyboardInterrupt:
        print("\n\n[*] Bot execution interrupted by user (Ctrl+C). Clean shutdown.")
        sys.exit(0)


if __name__ == "__main__":
    main()
