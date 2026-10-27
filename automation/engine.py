#!/usr/bin/env python3
"""Unified Camoufox browser setup and launch engine for bot automation."""

import random
from functools import lru_cache
from typing import Any, Dict, Optional

from camoufox import DefaultAddons
from camoufox.sync_api import Camoufox

# Fallback country -> (timezone, locale) map used when GeoIP lookup is unavailable.
COUNTRY_GEO_FALLBACK: Dict[str, tuple] = {
    "US": ("America/New_York", "en-US"),
    "USA": ("America/New_York", "en-US"),
    "UNITED STATES": ("America/New_York", "en-US"),
    "GB": ("Europe/London", "en-GB"),
    "UK": ("Europe/London", "en-GB"),
    "UNITED KINGDOM": ("Europe/London", "en-GB"),
    "CA": ("America/Toronto", "en-CA"),
    "CANADA": ("America/Toronto", "en-CA"),
    "AU": ("Australia/Sydney", "en-AU"),
    "AUSTRALIA": ("Australia/Sydney", "en-AU"),
    "DE": ("Europe/Berlin", "de-DE"),
    "GERMANY": ("Europe/Berlin", "de-DE"),
    "FR": ("Europe/Paris", "fr-FR"),
    "FRANCE": ("Europe/Paris", "fr-FR"),
    "NL": ("Europe/Amsterdam", "nl-NL"),
    "NETHERLANDS": ("Europe/Amsterdam", "nl-NL"),
    "SG": ("Asia/Singapore", "en-SG"),
    "SINGAPORE": ("Asia/Singapore", "en-SG"),
    "ID": ("Asia/Jakarta", "id-ID"),
    "INDONESIA": ("Asia/Jakarta", "id-ID"),
    "IN": ("Asia/Kolkata", "en-IN"),
    "INDIA": ("Asia/Kolkata", "en-IN"),
    "JP": ("Asia/Tokyo", "ja-JP"),
    "JAPAN": ("Asia/Tokyo", "ja-JP"),
    "BR": ("America/Sao_Paulo", "pt-BR"),
    "BRAZIL": ("America/Sao_Paulo", "pt-BR"),
}


@lru_cache(maxsize=512)
def _lookup_ip_geo(ip: str) -> Optional[Dict[str, Any]]:
    """Resolve timezone/locale/coordinates for an exit IP via Camoufox GeoIP."""
    try:
        from camoufox.geolocation import get_geolocation

        geo = get_geolocation(ip)
        locale = geo.locale
        return {
            "timezone": geo.timezone,
            "locale": f"{locale.language}-{locale.region}",
            "country_code": locale.region,
            "latitude": geo.latitude,
            "longitude": geo.longitude,
            "source": "geoip",
        }
    except Exception:
        return None


def resolve_geo_profile(proxy_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the timezone/locale profile that matches the proxy exit IP."""
    proxy_data = proxy_data or {}
    raw_country = str(
        proxy_data.get("country_code")
        or proxy_data.get("country")
        or ""
    ).strip()
    country_code = raw_country.upper()

    profile: Dict[str, Any] = {
        "country": raw_country or "Unknown",
        "country_code": country_code if len(country_code) in (2, 3) else "",
        "timezone": None,
        "locale": None,
        "latitude": None,
        "longitude": None,
        "source": "unknown",
    }

    ip = proxy_data.get("ip_detected") or proxy_data.get("ip")
    if ip:
        geo = _lookup_ip_geo(str(ip))
        if geo:
            profile.update(geo)

    if not profile.get("timezone"):
        key = raw_country.upper().strip()
        fallback = COUNTRY_GEO_FALLBACK.get(key)
        if fallback:
            profile["timezone"], profile["locale"] = fallback
            profile["source"] = "country-map"

    if profile.get("locale") and not profile.get("country_code"):
        region = str(profile["locale"]).split("-")[-1]
        if len(region) == 2:
            profile["country_code"] = region.upper()

    return profile


def get_proxy_credentials(proxy_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Convert a ProxyManager record into Camoufox/Playwright proxy settings."""
    if not proxy_data:
        return None

    host = proxy_data.get("host")
    port = proxy_data.get("port")
    username = proxy_data.get("username", "")
    password = proxy_data.get("password", "")

    if not host or not port:
        proxy_url = proxy_data.get("proxy_url", "")
        if proxy_url:
            from urllib.parse import urlparse

            parsed = urlparse(proxy_url)
            host = parsed.hostname
            port = parsed.port
            username = parsed.username or ""
            password = parsed.password or ""

    if not host or not port:
        return None

    result = {"server": f"http://{host}:{port}"}
    if username:
        result["username"] = username
    if password:
        result["password"] = password
    return result


def get_random_viewport() -> Dict[str, int]:
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
    allow_third_party_cookies: bool = True,
    extra_prefs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build launch options that keep ad networks reachable and popunders permitted."""
    proxy_dict = get_proxy_credentials(proxy_data) if proxy_data else None
    geo_profile = resolve_geo_profile(proxy_data)

    geoip_setting: Any = True
    if proxy_data and (proxy_data.get("ip_detected") or proxy_data.get("ip")):
        geoip_setting = proxy_data.get("ip_detected") or proxy_data.get("ip")

    user_prefs: Dict[str, Any] = {
        "dom.webnotifications.enabled": False,
        "dom.push.enabled": False,
        "media.autoplay.default": 0,
        "media.autoplay.blocking_policy": 0,
        "privacy.trackingprotection.enabled": False,
        "privacy.trackingprotection.pbmode.enabled": False,
        "privacy.trackingprotection.socialtracking.enabled": False,
        "privacy.trackingprotection.cryptomining.enabled": False,
        "privacy.trackingprotection.fingerprinting.enabled": False,
        "privacy.trackingprotection.emailtracking.enabled": False,
        "privacy.donottrackheader.enabled": False,
        "dom.disable_open_during_load": False,
        "dom.block_multiple_popups": False,
        "privacy.popups.showBrowserMessage": False,
        "browser.link.open_newwindow": 3,
        "browser.link.open_newwindow.restriction": 0,
    }
    if allow_third_party_cookies:
        user_prefs.update({
            "network.cookie.cookieBehavior": 0,
            "network.cookie.lifetimePolicy": 0,
            "network.cookie.thirdparty.sessionOnly": False,
            "network.cookie.thirdparty.nonsecureSessionOnly": False,
            "network.cookie.sameSite.laxByDefault": False,
            "network.cookie.sameSite.noneRequiresSecure": False,
            "privacy.partition.network_state": False,
            "privacy.restrict3rdpartystorage.enabled": False,
            "privacy.restrict3rdpartystorage.userInteractionRequiredForHosts": "",
            "privacy.firstparty.isolate": False,
            "dom.storage_access.enabled": True,
        })
    if extra_prefs:
        user_prefs.update(extra_prefs)

    kwargs: Dict[str, Any] = {
        "headless": headless,
        "humanize": humanize,
        "block_webrtc": True,
        "firefox_user_prefs": user_prefs,
    }

    if geo_profile.get("locale"):
        kwargs["locale"] = geo_profile["locale"]
    if geo_profile.get("timezone") and geo_profile.get("source") != "geoip":
        kwargs["config"] = {"timezone": geo_profile["timezone"]}

    if proxy_dict:
        kwargs["proxy"] = proxy_dict
        try:
            from camoufox.geolocation import geoip_allowed
            geoip_allowed()
            kwargs["geoip"] = geoip_setting
        except Exception:
            # Fallback jika modul camoufox[geoip] belum terpasang
            kwargs["geoip"] = False
            kwargs["i_know_what_im_doing"] = True

    if allow_ads:
        kwargs["exclude_addons"] = [DefaultAddons.UBO]

    return kwargs


def create_camoufox_session(
    proxy_data: Optional[Dict[str, Any]] = None,
    headless: bool = True,
    humanize: bool = True,
    allow_ads: bool = True,
    allow_third_party_cookies: bool = True,
) -> Camoufox:
    kwargs = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize,
        allow_ads=allow_ads,
        allow_third_party_cookies=allow_third_party_cookies,
    )
    return Camoufox(**kwargs)


def load_config() -> Dict[str, Any]:
    import json
    from pathlib import Path
    cfg_file = Path(__file__).resolve().parent / "monetag" / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "target_url": "https://article.riztama.my.id/m/",
        "headless": True,
        "humanize": True,
        "run_browser_verifier": True,
        "concurrency": 2,
        "max_sessions_per_run": 8,
    }

