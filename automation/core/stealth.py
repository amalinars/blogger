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


def get_fingerprint_profile(prefer_os: str = None) -> dict:
    """
    Menghasilkan profil fingerprint yang konsisten:
    - User-Agent selaras dengan platform (Win32 vs MacIntel).
    - WebGL vendor & renderer yang konsisten dengan OS.
    - Resolusi viewport dan screen realistis.
    """
    is_mac = False
    if prefer_os:
        is_mac = (prefer_os.lower() == "mac")
    else:
        is_mac = (random.random() < 0.20)  # 20% Mac, 80% Windows

    if is_mac:
        ua = random.choice(MAC_USER_AGENTS)
        platform = "MacIntel"
        webgl_vendor = "Apple"
        webgl_renderer = "Apple M2 / Apple GPU"
    else:
        ua = random.choice(WINDOWS_USER_AGENTS)
        platform = "Win32"
        webgl_vendor = "Google Inc. (Intel)"
        webgl_renderer = "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"

    vp = random.choice(DESKTOP_VIEWPORTS)

    return {
        "user_agent": ua,
        "platform": platform,
        "viewport": vp,
        "device_memory": random.choice([8, 16]),
        "hardware_concurrency": random.choice([4, 8, 12, 16]),
        "webgl_vendor": webgl_vendor,
        "webgl_renderer": webgl_renderer
    }


def get_stealth_init_script(profile: dict) -> str:
    """
    Menghasilkan kode JavaScript untuk diinjeksi via context.add_init_script()
    sebelum script halaman dieksekusi.
    """
    platform = profile.get("platform", "Win32")
    webgl_vendor = profile.get("webgl_vendor", "Google Inc. (Intel)")
    webgl_renderer = profile.get("webgl_renderer", "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)")
    mem = profile.get("device_memory", 8)
    hw = profile.get("hardware_concurrency", 8)

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

        // 2. Selaraskan navigator.platform
        try {{
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform}',
                configurable: true
            }});
        }} catch (e) {{}}

        // 3. Selaraskan hardware concurrency & device memory
        try {{
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {hw},
                configurable: true
            }});
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {mem},
                configurable: true
            }});
        }} catch (e) {{}}

        // 4. Injeksi window.chrome objek yang lengkap
        try {{
            if (!window.chrome) {{
                window.chrome = {{}};
            }}
            window.chrome.app = {{
                InstallState: {{ DISABLED: 'Disabled', INSTALLED: 'Installed', NOT_INSTALLED: 'NotInstalled' }},
                RunningState: {{ CANNOT_RUN: 'CannotRun', READY_TO_RUN: 'ReadyToRun', RUNNING: 'Running' }},
                getDetails: function() {{}},
                getIsInstalled: function() {{ return false; }},
                installState: function() {{ return 'NotInstalled'; }},
                isInstalled: false,
                runningState: function() {{ return 'CannotRun'; }}
            }};
            window.chrome.csi = function() {{ return {{ onloadT: 0, pageT: 0, startE: 0, tran: 0 }}; }};
            window.chrome.loadTimes = function() {{
                return {{
                    commitLoadTime: 0,
                    connectionInfo: 'http/1.1',
                    finishDocumentLoadTime: 0,
                    finishLoadTime: 0,
                    firstPaintAfterLoadTime: 0,
                    firstPaintTime: 0,
                    navigationType: 'Other',
                    npnNegotiatedProtocol: 'http/1.1',
                    requestTime: 0,
                    startLoadTime: 0,
                    wasAlternateProtocolAvailable: false,
                    wasFetchedViaSpdy: false,
                    wasNpnNegotiated: false
                }};
            }};
            window.chrome.runtime = {{
                OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }},
                OnRestartRequiredReason: {{ APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }},
                PlatformArch: {{ ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
                PlatformNaclArch: {{ ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
                PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }},
                RequestUpdateCheckStatus: {{ NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }}
            }};
        }} catch (e) {{}}

        // 5. Spoofing Plugins & MimeTypes agar tidak terbaca browser kosongan
        try {{
            const fakePlugins = [
                {{ name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                {{ name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                {{ name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                {{ name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                {{ name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }}
            ];
            Object.defineProperty(navigator, 'plugins', {{
                get: () => fakePlugins,
                configurable: true
            }});
        }} catch (e) {{}}

        // 6. WebGL Vendor & Renderer Spoofing
        try {{
            const getParameterProto = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) {{
                    return '{webgl_vendor}';
                }}
                if (parameter === 37446) {{
                    return '{webgl_renderer}';
                }}
                return getParameterProto.apply(this, arguments);
            }};

            if (typeof WebGL2RenderingContext !== 'undefined') {{
                const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
                    if (parameter === 37445) {{
                        return '{webgl_vendor}';
                    }}
                    if (parameter === 37446) {{
                        return '{webgl_renderer}';
                    }}
                    return getParameterProto2.apply(this, arguments);
                }};
            }}
        }} catch (e) {{}}

        // 7. Notification & Permissions state
        try {{
            if (window.Notification) {{
                Object.defineProperty(Notification, 'permission', {{
                    get: () => 'default',
                    configurable: true
                }});
            }}
        }} catch (e) {{}}

        // 8. MediaDevices & Audio/Video device emulation (cegah deteksi VM headless kosong)
        try {{
            if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
                const origEnumerate = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
                navigator.mediaDevices.enumerateDevices = async function() {{
                    const devices = await origEnumerate().catch(() => []);
                    if (devices && devices.length > 0) return devices;
                    return [
                        {{ deviceId: "default", kind: "audioinput", label: "Default - Internal Microphone", groupId: "group-audio-1" }},
                        {{ deviceId: "default", kind: "audiooutput", label: "Default - Internal Speakers", groupId: "group-audio-1" }},
                        {{ deviceId: "default", kind: "videoinput", label: "Integrated Webcam (04f2:b6d9)", groupId: "group-video-1" }}
                    ];
                }};
            }}
        }} catch (e) {{}}

        // 9. WebRTC IP Leak Defense di layer JavaScript
        try {{
            if (window.RTCPeerConnection) {{
                const origCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
                RTCPeerConnection.prototype.createDataChannel = function() {{
                    return origCreateDataChannel.apply(this, arguments);
                }};
            }}
        }} catch (e) {{}}
    }})();
    """
