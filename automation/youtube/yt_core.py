#!/usr/bin/env python3
"""
automation.youtube.yt_core - Dedicated Core Engine for YouTube Organic Views
Dibangun khusus untuk YouTube tanpa interferensi konfigurasi bot blog/ads.

Fitur Utama:
1. Protokol Modern Aktif Penuh: HTTP/2 dan QUIC diizinkan (sangat krusial untuk YouTube videoplayback & stats/watchtime).
2. Anti-Detection Stealth Bersih: Hapus navigator.webdriver tanpa merusak fungsi native Chrome C++.
3. Konsistensi Geo & Timezone: Sinkronisasi Timezone, Locale, Geolocation sesuai negara proksi residensial.
4. Pure Organic Playback: Tidak memanggil API terlarang/deprecated (seperti setPlaybackQualityRange) yang memicu flag bot fraud.
5. Natural Human Interaction: Gerakan mouse bezier alami, organic scroll, dan retensi tinggi (80%-95% durasi).
"""

import os
import sys
import time
import random
from typing import Optional, Dict, Any, Tuple, List
from playwright.sync_api import Playwright, Browser, BrowserContext, Page

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from automation.core.stealth import get_geo_profile, get_installed_chrome_version
from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause


def build_yt_browser_args(
    window_position: Optional[Tuple[int, int]] = None,
    window_size: Tuple[int, int] = (1280, 800),
    headless: bool = False,
    extra_args: Optional[List[str]] = None,
) -> List[str]:
    """
    Argumen Chromium murni untuk YouTube.
    CATATAN: HTTP/2 dan QUIC TIDAK PERNAH DIMATIKAN di sini karena YouTube
    memerlukan HTTP/2 untuk memvalidasi sesi streaming video yang sah.
    """
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--enforce-webrtc-ip-permission-check",
        "--autoplay-policy=no-user-gesture-required",
        # Izinkan rendering grafis wajar agar video player berjalan mulus
        "--enable-features=NetworkService,NetworkServiceInProcess",
    ]

    if window_position:
        args.append(f"--window-position={window_position[0]},{window_position[1]}")

    if window_size:
        args.append(f"--window-size={window_size[0]},{window_size[1]}")

    if extra_args:
        args.extend(extra_args)

    return args


def launch_yt_browser(
    playwright_instance: Playwright,
    proxy_dict: Optional[Dict[str, str]] = None,
    headless: bool = False,
    browser_args: Optional[List[str]] = None,
    tag: str = "[YT]",
) -> Browser:
    """Meluncurkan browser dengan prioritas Google Chrome asli sistem."""
    if browser_args is None:
        browser_args = build_yt_browser_args(headless=headless)

    try:
        return playwright_instance.chromium.launch(
            channel="chrome",
            headless=headless,
            args=browser_args,
            ignore_default_args=["--enable-automation"],
            proxy=proxy_dict,
        )
    except Exception as e:
        print(f"{tag} [*] Google Chrome native notice: {e}, menggunakan bundled chromium...")
        return playwright_instance.chromium.launch(
            headless=headless,
            args=browser_args,
            ignore_default_args=["--enable-automation"],
            proxy=proxy_dict,
        )


def get_yt_stealth_script(platform: str = "Linux x86_64") -> str:
    """
    Script injeksi stealth murni khusus YouTube:
    - Menghapus navigator.webdriver secara bersih.
    - Menjaga window.chrome agar selaras dengan browser Google Chrome asli.
    - Menghindari modifikasi berlebihan yang memicu deteksi anti-cheat YouTube.
    """
    return f"""
    (() => {{
        // 1. Hapus navigator.webdriver
        try {{
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined,
                configurable: true
            }});
            delete Object.getPrototypeOf(navigator).webdriver;
        }} catch (e) {{}}

        // 2. Selaraskan platform
        try {{
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform}',
                configurable: true
            }});
        }} catch (e) {{}}

        // 3. Pastikan window.chrome eksis secara alami
        try {{
            if (!window.chrome) {{
                window.chrome = {{ runtime: {{}} }};
            }}
        }} catch (e) {{}}

        // 4. Pastikan Notification permission normal
        try {{
            if (window.Notification) {{
                Object.defineProperty(Notification, 'permission', {{
                    get: () => 'default',
                    configurable: true
                }});
            }}
        }} catch (e) {{}}
    }})();
    """


def create_yt_context(
    browser: Browser,
    proxy_country: str = "",
    tag: str = "[YT]",
) -> Tuple[BrowserContext, Dict[str, Any]]:
    """Membuat browser context stealth yang sinkron dengan IP proksi."""
    geo_profile = get_geo_profile(proxy_country)
    chrome_ver = get_installed_chrome_version()

    # User Agent native yang konsisten dengan sistem
    ua = (
        f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{chrome_ver}.0.0.0 Safari/537.36"
    )

    viewports = [
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 800},
    ]
    vp = random.choice(viewports)

    context = browser.new_context(
        viewport=vp,
        user_agent=ua,
        locale=geo_profile["locale"],
        timezone_id=geo_profile["timezone"],
        geolocation=geo_profile["coords"],
        permissions=["geolocation"],
    )

    # Injeksi stealth script
    stealth_code = get_yt_stealth_script(platform="Linux x86_64")
    context.add_init_script(stealth_code)

    return context, geo_profile
