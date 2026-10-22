#!/usr/bin/env python3
"""
automation.core.browser - Reusable Playwright Browser and Context Factory
Provides standardized anti-bot flags, WebRTC leak defense, proxy integration,
and automatic CDP stealth injection across all automation targets.
"""

from typing import Optional, Tuple, Dict, Any, List
from playwright.sync_api import Playwright, Browser, BrowserContext

from .stealth import (
    get_geo_profile,
    get_fingerprint_profile,
    get_stealth_init_script,
)


def build_browser_args(
    window_position: Optional[Tuple[int, int]] = None,
    window_size: Tuple[int, int] = (1260, 820),
    extra_args: Optional[List[str]] = None,
) -> List[str]:
    """Menghasilkan argumen peluncuran Chromium standar dengan proteksi anti-deteksi & WebRTC."""
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-quic",
        "--disable-http2",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--enforce-webrtc-ip-permission-check",
    ]

    if window_position:
        args.append(f"--window-position={window_position[0]},{window_position[1]}")

    if window_size:
        args.append(f"--window-size={window_size[0]},{window_size[1]}")

    if extra_args:
        args.extend(extra_args)

    return args


def format_proxy_dict(proxy: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Mengubah dictionary proksi internal menjadi format yang didukung Playwright."""
    if not proxy or not proxy.get("host") or not proxy.get("port"):
        return None

    return {
        "server": f"http://{proxy['host']}:{proxy['port']}",
        "username": proxy.get("username", ""),
        "password": proxy.get("password", ""),
    }


def launch_browser(
    playwright_instance: Playwright,
    proxy_dict: Optional[Dict[str, str]] = None,
    headless: bool = False,
    browser_args: Optional[List[str]] = None,
    tag: str = "[*]",
) -> Browser:
    """
    Meluncurkan browser Chromium.
    Memprioritaskan binary Google Chrome asli jika terpasang di sistem,
    dan otomatis beralih ke Chromium bawaan Playwright jika Chrome tidak ada.
    """
    if browser_args is None:
        browser_args = build_browser_args()

    try:
        return playwright_instance.chromium.launch(
            channel="chrome",
            headless=headless,
            args=browser_args,
            ignore_default_args=["--enable-automation"],
            proxy=proxy_dict,
        )
    except Exception as e:
        print(f"{tag} [*] Native Chrome notice: {e}, using bundled chromium...")
        return playwright_instance.chromium.launch(
            headless=headless,
            args=browser_args,
            ignore_default_args=["--enable-automation"],
            proxy=proxy_dict,
        )


def create_stealth_context(
    browser: Browser,
    proxy_country: str = "",
    prefer_os: Optional[str] = None,
    custom_viewport: Optional[Dict[str, int]] = None,
    tag: str = "[*]",
) -> Tuple[BrowserContext, Dict[str, Any]]:
    """
    Membuat BrowserContext yang disinkronkan secara menyeluruh:
    - Timezone, Locale, dan Geolocation selaras dengan negara proksi.
    - User-Agent, Platform, WebGL, dan MediaDevices konsisten.
    - Script CDP stealth disuntikkan secara otomatis sebelum script web manapun dieksekusi.
    """
    geo_profile = get_geo_profile(proxy_country)
    fp_profile = get_fingerprint_profile(prefer_os=prefer_os)

    vp = custom_viewport or fp_profile["viewport"]

    print(
        f"{tag} 🛡️ [STEALTH] Profil Browser: OS={fp_profile['platform']} | "
        f"Timezone={geo_profile['timezone']} | Locale={geo_profile['locale']}"
    )

    context_kwargs: Dict[str, Any] = {
        "viewport": vp,
        "locale": geo_profile["locale"],
        "timezone_id": geo_profile["timezone"],
        "geolocation": geo_profile["coords"],
        "permissions": ["geolocation", "notifications"],
    }
    if fp_profile.get("user_agent"):
        context_kwargs["user_agent"] = fp_profile["user_agent"]

    context = browser.new_context(**context_kwargs)


    # Injeksi stealth script (penghapusan navigator.webdriver, WebGL, MediaDevices, runtime mock)
    stealth_script = get_stealth_init_script(fp_profile)
    context.add_init_script(stealth_script)

    # Batasi timeout default agar aksi Playwright (click, waitFor, dll) tidak nge-hang selamanya
    context.set_default_timeout(15000)             # Maks 15 detik untuk interaksi elemen
    context.set_default_navigation_timeout(25000)  # Maks 25 detik untuk navigasi halaman

    # Otomatis dismiss dialog tak terduga (alert/prompt/confirm/beforeunload) agar worker tidak macet
    try:
        context.on("dialog", lambda dialog: dialog.dismiss())
    except Exception:
        pass

    # Pasang proteksi timeout & dialog dismissal pada setiap tab/popup baru yang terbuka
    def _guard_new_tab(new_p):
        try:
            new_p.set_default_timeout(15000)
            new_p.set_default_navigation_timeout(25000)
            new_p.on("dialog", lambda d: d.dismiss())
        except Exception:
            pass

    try:
        context.on("page", _guard_new_tab)
    except Exception:
        pass

    metadata = {
        "geo": geo_profile,
        "fingerprint": fp_profile,
    }

    return context, metadata
