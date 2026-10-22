#!/usr/bin/env python3
"""
stealth.py - Anti-Detection & Synthetic Fingerprint Spoofing Engine
Provides dynamic geolocation/timezone synchronization, CDP stealth overrides,
and consistent hardware/platform emulation for Playwright browsers.
"""

import random

# Mapping negara ke profil Geolocation, Timezone, dan Locale
GEO_PROFILES = {
    "united states": {
        "timezones": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
        "locale": "en-US",
        "currency": "USD",
        "coords": {"latitude": 40.7128, "longitude": -74.0060}
    },
    "us": {
        "timezones": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
        "locale": "en-US",
        "currency": "USD",
        "coords": {"latitude": 40.7128, "longitude": -74.0060}
    },
    "united kingdom": {
        "timezones": ["Europe/London"],
        "locale": "en-GB",
        "currency": "GBP",
        "coords": {"latitude": 51.5074, "longitude": -0.1278}
    },
    "gb": {
        "timezones": ["Europe/London"],
        "locale": "en-GB",
        "currency": "GBP",
        "coords": {"latitude": 51.5074, "longitude": -0.1278}
    },
    "uk": {
        "timezones": ["Europe/London"],
        "locale": "en-GB",
        "currency": "GBP",
        "coords": {"latitude": 51.5074, "longitude": -0.1278}
    },
    "australia": {
        "timezones": ["Australia/Sydney", "Australia/Melbourne"],
        "locale": "en-AU",
        "currency": "AUD",
        "coords": {"latitude": -33.8688, "longitude": 151.2093}
    },
    "au": {
        "timezones": ["Australia/Sydney", "Australia/Melbourne"],
        "locale": "en-AU",
        "currency": "AUD",
        "coords": {"latitude": -33.8688, "longitude": 151.2093}
    },
    "canada": {
        "timezones": ["America/Toronto", "America/Vancouver"],
        "locale": "en-CA",
        "currency": "CAD",
        "coords": {"latitude": 43.6532, "longitude": -79.3832}
    },
    "ca": {
        "timezones": ["America/Toronto", "America/Vancouver"],
        "locale": "en-CA",
        "currency": "CAD",
        "coords": {"latitude": 43.6532, "longitude": -79.3832}
    },
    "france": {
        "timezones": ["Europe/Paris"],
        "locale": "fr-FR",
        "currency": "EUR",
        "coords": {"latitude": 48.8566, "longitude": 2.3522}
    },
    "fr": {
        "timezones": ["Europe/Paris"],
        "locale": "fr-FR",
        "currency": "EUR",
        "coords": {"latitude": 48.8566, "longitude": 2.3522}
    },
    "germany": {
        "timezones": ["Europe/Berlin"],
        "locale": "de-DE",
        "currency": "EUR",
        "coords": {"latitude": 52.5200, "longitude": 13.4050}
    },
    "de": {
        "timezones": ["Europe/Berlin"],
        "locale": "de-DE",
        "currency": "EUR",
        "coords": {"latitude": 52.5200, "longitude": 13.4050}
    },
    "indonesia": {
        "timezones": ["Asia/Jakarta"],
        "locale": "id-ID",
        "currency": "IDR",
        "coords": {"latitude": -6.2088, "longitude": 106.8456}
    },
    "id": {
        "timezones": ["Asia/Jakarta"],
        "locale": "id-ID",
        "currency": "IDR",
        "coords": {"latitude": -6.2088, "longitude": 106.8456}
    }
}

DEFAULT_GEO = {
    "timezones": ["America/New_York"],
    "locale": "en-US",
    "currency": "USD",
    "coords": {"latitude": 40.7128, "longitude": -74.0060}
}


def get_geo_profile(country_str: str) -> dict:
    """Mengembalikan profil Geo (timezone, locale, koordinat) sesuai negara proksi."""
    if not country_str:
        chosen = DEFAULT_GEO
    else:
        norm = str(country_str).strip().lower()
        chosen = GEO_PROFILES.get(norm, DEFAULT_GEO)

    tz = random.choice(chosen["timezones"])
    coords = chosen["coords"]
    # Sedikit perturbasi acak koordinat (+- 0.05 derajat) agar tidak persis di titik yang sama
    lat = coords["latitude"] + random.uniform(-0.03, 0.03)
    lon = coords["longitude"] + random.uniform(-0.03, 0.03)

    return {
        "timezone": tz,
        "locale": chosen["locale"],
        "currency": chosen["currency"],
        "coords": {"latitude": lat, "longitude": lon}
    }


DESKTOP_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768}
]

WINDOWS_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
]

MAC_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
]


def get_installed_chrome_version() -> str:
    """Mendeteksi versi Google Chrome yang terpasang di sistem untuk mencegah ketidaksinkronan Client Hints."""
    try:
        import subprocess
        out = subprocess.check_output(["google-chrome", "--version"], text=True)
        for part in out.strip().split():
            if "." in part and part[0].isdigit():
                return part.split(".")[0]
    except Exception:
        pass
    return "143"


def get_fingerprint_profile(prefer_os: str = None) -> dict:
    """
    Menghasilkan profil fingerprint yang konsisten:
    - User-Agent selaras dengan versi Chromium sistem (mencegah bentrok dengan header Sec-CH-UA).
    - Menghindari penimpaan palsu yang memicu deteksi bot anti-fraud jaringan iklan.
    """
    chrome_ver = get_installed_chrome_version()
    is_mac = False
    is_windows = False

    if prefer_os:
        if prefer_os.lower() == "mac":
            is_mac = True
        elif prefer_os.lower() == "windows":
            is_windows = True

    if is_mac:
        ua = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver}.0.0.0 Safari/537.36"
        platform = "MacIntel"
        webgl_vendor = "Apple"
        webgl_renderer = "Apple M2 / Apple GPU"
    elif is_windows:
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver}.0.0.0 Safari/537.36"
        platform = "Win32"
        webgl_vendor = "Google Inc. (Intel)"
        webgl_renderer = "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"
    else:
        # Gunakan profil bawaan sistem (Linux native Chrome) agar 100% konsisten dengan Sec-CH-UA
        ua = None
        platform = "Linux x86_64"
        webgl_vendor = "Google Inc. (Intel)"
        webgl_renderer = "ANGLE (Intel, Mesa Intel(R) HD Graphics 530 (SKL GT2), OpenGL 4.6)"

    vp = random.choice(DESKTOP_VIEWPORTS)

    return {
        "user_agent": ua,
        "platform": platform,
        "viewport": vp,
        "device_memory": random.choice([8, 16]),
        "hardware_concurrency": random.choice([4, 8, 12, 16]),
        "webgl_vendor": webgl_vendor,
        "webgl_renderer": webgl_renderer,
        "chrome_version": chrome_ver
    }


def get_stealth_init_script(profile: dict) -> str:
    """
    Menghasilkan kode JavaScript untuk diinjeksi via context.add_init_script()
    sebelum script halaman dieksekusi.
    
    PERBAIKAN KRUSIAL UNTUK AD NETWORKS:
    - Hapus navigator.webdriver secara bersih dari prototype.
    - JANGAN menimpa window.chrome dengan objek tiruan (karena fungsi C++ native Chrome
      menghasilkan [native code]; fungsi tiruan JS langsung terdeteksi fraud).
    - JANGAN menimpa navigator.plugins dengan array biasa (karena anti-bot mengecek
      'plugins instanceof PluginArray'). Native Chrome sudah memiliki PluginArray yang sah.
    - Selaraskan WebRTC IP leak defense tanpa merusak network streaming.
    """
    platform = profile.get("platform", "Linux x86_64")
    chrome_ver = profile.get("chrome_version", "143")
    uadata_platform = "macOS" if "Mac" in platform else ("Windows" if "Win" in platform else "Linux")

    script_parts = [
        """
        // 1. Hapus indikator otomatisasi navigator.webdriver secara bersih
        try {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            delete Object.getPrototypeOf(navigator).webdriver;
        } catch (e) {}
        """
    ]

    # Jika platform dipalsukan (Windows/Mac) saat prefer_os aktif
    if profile.get("user_agent"):
        script_parts.append(f"""
        // 2. Selaraskan navigator.platform & userAgentData jika User-Agent di-override
        try {{
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform}',
                configurable: true
            }});
        }} catch (e) {{}}

        try {{
            if (navigator.userAgentData) {{
                Object.defineProperty(navigator, 'userAgentData', {{
                    get: () => ({{
                        brands: [
                            {{ brand: 'Google Chrome', version: '{chrome_ver}' }},
                            {{ brand: 'Chromium', version: '{chrome_ver}' }},
                            {{ brand: 'Not_A Brand', version: '24' }}
                        ],
                        mobile: false,
                        platform: '{uadata_platform}',
                        getHighEntropyValues: async () => ({{
                            platform: '{uadata_platform}',
                            platformVersion: '15.0.0',
                            architecture: 'x86',
                            model: '',
                            uaFullVersion: '{chrome_ver}.0.0.0'
                        }})
                    }}),
                    configurable: true
                }});
            }}
        }} catch (e) {{}}
        """)

    # Proteksi dasar Notification & WebRTC
    script_parts.append("""
        // 3. Pastikan permission notifikasi bernilai default (wajar untuk pengunjung baru)
        try {
            if (window.Notification) {
                Object.defineProperty(Notification, 'permission', {
                    get: () => 'default',
                    configurable: true
                });
            }
        } catch (e) {}

        // 4. Pastikan window.chrome eksis secara alami tanpa merusak fungsi native
        try {
            if (!window.chrome) {
                window.chrome = { runtime: {} };
            }
        } catch (e) {}

        // 5. WebRTC leak defense di layer JavaScript
        try {
            if (window.RTCPeerConnection) {
                const origCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
                RTCPeerConnection.prototype.createDataChannel = function() {
                    return origCreateDataChannel.apply(this, arguments);
                };
            }
        } catch (e) {}
    """)

    combined = "\n".join(script_parts)
    return f"(() => {{\n{combined}\n}})();"

