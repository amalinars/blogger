import pytest
from automation.stealth import get_geo_profile, get_fingerprint_profile, get_stealth_init_script

def test_geo_profile_known_countries():
    us = get_geo_profile("United States")
    assert "America/" in us["timezone"]
    assert us["locale"] == "en-US"

    au = get_geo_profile("Australia")
    assert au["timezone"] in ["Australia/Sydney", "Australia/Melbourne"]
    assert au["locale"] == "en-AU"

    gb = get_geo_profile("United Kingdom")
    assert gb["timezone"] == "Europe/London"
    assert gb["locale"] == "en-GB"

    fr = get_geo_profile("France")
    assert fr["timezone"] == "Europe/Paris"
    assert fr["locale"] == "fr-FR"

def test_geo_profile_fallback():
    unknown = get_geo_profile("UnknownCountry")
    assert "timezone" in unknown
    assert "locale" in unknown

def test_fingerprint_profile_consistency():
    profile = get_fingerprint_profile()
    assert "user_agent" in profile
    assert "platform" in profile
    if "Windows" in profile["user_agent"]:
        assert profile["platform"] == "Win32"
    elif "Macintosh" in profile["user_agent"]:
        assert profile["platform"] == "MacIntel"

def test_stealth_init_script():
    profile = get_fingerprint_profile()
    script = get_stealth_init_script(profile)
    assert "navigator.webdriver" in script
    assert "window.chrome" in script
    assert "plugins" in script
    assert "mediaDevices" in script
    assert "RTCPeerConnection" in script
