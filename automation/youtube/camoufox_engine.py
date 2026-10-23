#!/usr/bin/env python3
"""
automation.youtube.camoufox_engine
Dedicated Camoufox Anti-Detect Browser Engine for YouTube Organic Views.

Keunggulan Camoufox untuk YouTube:
1. Firefox C++ Native Patch: Menghapus seluruh artefak automasi (navigator.webdriver=false, tanpa fingerprint flags).
2. Humanize Physics: Gerakan mouse bezier alami, typing cadence, dan pergerakan kursor yang realistis.
3. GeoIP Alignment: Sinkronisasi Timezone, Locale, dan Geolocation secara presisi dengan IP proksi residensial.
4. WebRTC Leak Protection: Memblokir kebocoran IP lokal/host asli melalui WebRTC.
5. Allowed Ads: Mengecualikan adblocker (uBlock Origin) agar tayangan iklan monetisasi YouTube aktif dan dapat dideteksi.
6. Media Autoplay & Audio Context: Mengaktifkan autoplay dan audio context agar video YouTube langsung terputar valid.
"""

import os
import sys
import random
from typing import Optional, Dict, Any, Tuple
import camoufox
from camoufox.sync_api import Camoufox
from camoufox import DefaultAddons

def get_proxy_credentials(proxy_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Mengonversi data proxy dari ProxyManager ke format dictionary Playwright/Camoufox."""
    if not proxy_data:
        return None

    host = proxy_data.get("host")
    port = proxy_data.get("port")
    username = proxy_data.get("username", "")
    password = proxy_data.get("password", "")

    if not host or not port:
        # Coba parse dari proxy_url jika ada
        p_url = proxy_data.get("proxy_url", "")
        if p_url:
            from urllib.parse import urlparse
            parsed = urlparse(p_url)
            host = parsed.hostname
            port = parsed.port
            username = parsed.username or ""
            password = parsed.password or ""

    if not host or not port:
        return None

    server = f"http://{host}:{port}"
    res = {"server": server}
    if username:
        res["username"] = username
    if password:
        res["password"] = password
    return res


def get_random_viewport() -> Dict[str, int]:
    """Mengembalikan dimensi layar browser yang umum dan natural."""
    viewports = [
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1280, "height": 800},
        {"width": 1920, "height": 1080},
    ]
    return random.choice(viewports)


def build_camoufox_kwargs(
    proxy_data: Optional[Dict[str, Any]] = None,
    headless: bool = True,
    humanize: bool = True,
    allow_ads: bool = True,
    extra_prefs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Menyiapkan seluruh konfigurasi peluncuran Camoufox dengan parameter anti-deteksi terkuat.
    """
    proxy_dict = get_proxy_credentials(proxy_data) if proxy_data else None

    # Pengaturan GeoIP: Gunakan IP yang sudah terdeteksi jika ada, atau True untuk query otomatis via proxy
    geoip_setting = True
    if proxy_data and proxy_data.get("ip_detected"):
        geoip_setting = proxy_data.get("ip_detected")

    # Firefox user preferences khusus media & YouTube
    user_prefs: Dict[str, Any] = {
        # Izinkan autoplay video & audio tanpa user gesture awal
        "media.autoplay.default": 0,
        "media.autoplay.blocking_policy": 0,
        "media.volume_scale": "1.0",
        # Matikan prompt notifikasi push web
        "dom.webnotifications.enabled": False,
        "dom.push.enabled": False,
        # Hemat RAM & optimasi background playback
        "dom.ipc.processCount": 4,
        "media.cache_size": 51200,
    }

    if extra_prefs:
        user_prefs.update(extra_prefs)

    kwargs: Dict[str, Any] = {
        "headless": headless,
        "humanize": humanize,
        "block_webrtc": True,
        "firefox_user_prefs": user_prefs,
    }

    if proxy_dict:
        kwargs["proxy"] = proxy_dict
        kwargs["geoip"] = geoip_setting

    # PENTING: Jika allow_ads=True, kecualikan uBlock Origin agar iklan YouTube bisa muncul dan dideteksi
    if allow_ads:
        kwargs["exclude_addons"] = [DefaultAddons.UBO]

    return kwargs


def create_camoufox_session(
    proxy_data: Optional[Dict[str, Any]] = None,
    headless: bool = True,
    humanize: bool = True,
    allow_ads: bool = True,
) -> Camoufox:
    """Membuat instance Camoufox context manager dengan konfigurasi lengkap."""
    kwargs = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize,
        allow_ads=allow_ads,
    )
    return Camoufox(**kwargs)
