import pytest
from automation.traffic_bot import get_organic_referer

def test_get_organic_referer_distribution():
    sample = [get_organic_referer() for _ in range(500)]
    # Ensure Google is represented
    google_count = sum(1 for r in sample if r and "google.com" in r)
    assert google_count > 50  # Around ~40%
    # Ensure Direct (None) is represented
    direct_count = sum(1 for r in sample if r is None)
    assert direct_count > 10  # Around ~10-15%
    # Ensure Social is represented
    social_count = sum(1 for r in sample if r and ("t.co" in r or "reddit.com" in r or "facebook.com" in r))
    assert social_count > 30

def test_get_organic_referer_custom_pool():
    custom = [("https://custom.source.com/", 1.0)]
    res = get_organic_referer(custom_pool=custom)
    assert res == "https://custom.source.com/"
