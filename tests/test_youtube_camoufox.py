#!/usr/bin/env python3
"""
Unit and integration tests for automation.youtube module.
"""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.youtube.bot import (
    load_config,
    format_time,
    get_country_badge,
    parse_time_str,
    check_page_offline_or_error,
    AdTracker,
)
from automation.youtube.camoufox_engine import (
    build_camoufox_kwargs,
    get_proxy_credentials,
)
from automation.youtube.tui import TUIManager
from core.proxy_manager import ProxyManager


def test_load_config():
    cfg = load_config()
    assert "search_keyword" in cfg
    assert cfg["search_keyword"] == "horrornologi"
    assert "channel_latest_video_weight" in cfg["flow_balance"]
    assert cfg["flow_balance"]["channel_latest_video_weight"] == 1.0


def test_format_time():
    assert format_time(0) == "00:00"
    assert format_time(65) == "01:05"
    assert format_time(3600) == "01:00:00"
    assert format_time(3665) == "01:01:05"


def test_get_country_badge():
    assert "🇨🇦" in get_country_badge("Canada")
    assert "🇺🇸" in get_country_badge("United States")
    assert "🇮🇩" in get_country_badge("Indonesia")
    assert "🌍" in get_country_badge("UnknownCountry")


def test_build_camoufox_kwargs():
    proxy_sample = {
        "host": "geo.floppydata.com",
        "port": 10080,
        "username": "user123",
        "password": "pass123",
        "ip_detected": "184.162.86.23",
        "country": "Canada",
    }
    kwargs = build_camoufox_kwargs(proxy_data=proxy_sample, headless=True, allow_ads=True)

    assert kwargs["headless"] is True
    assert kwargs["humanize"] is True
    assert kwargs["block_webrtc"] is True
    assert "proxy" in kwargs
    assert kwargs["proxy"]["server"] == "http://geo.floppydata.com:10080"
    assert kwargs["proxy"]["username"] == "user123"
    assert kwargs["geoip"] == "184.162.86.23"
    assert "exclude_addons" in kwargs  # uBlock Origin excluded so ads are allowed


def test_ad_tracker_logic():
    tracker = AdTracker(skip_delay_range=(1.0, 2.0))
    assert tracker.ad_is_showing is False
    assert tracker.total_ads_detected == 0

    # Mock page class
    class MockPage:
        def __init__(self, ad_status=False):
            self._ad_status = ad_status

        def evaluate(self, script):
            return self._ad_status

        def query_selector(self, sel):
            return None

    page = MockPage(ad_status=False)
    events = []

    def mock_cb(ev, data):
        events.append((ev, data))

    # Frame 1: Konten normal
    tracker.check(page, event_callback=mock_cb, worker_id=1)
    assert tracker.ad_is_showing is False

    # Frame 2: Iklan muncul!
    page._ad_status = True
    tracker.check(page, event_callback=mock_cb, worker_id=1)
    assert tracker.ad_is_showing is True
    assert tracker.total_ads_detected == 1
    assert any(d.get("event") == "iklan_muncul" for _, d in events)

    # Frame 3: Iklan selesai!
    page._ad_status = False
    tracker.check(page, event_callback=mock_cb, worker_id=1)
    assert tracker.ad_is_showing is False
    assert tracker.total_ads_finished == 1
    assert any(d.get("event") == "iklan_selesai" for _, d in events)


def test_tui_render():
    pm = ProxyManager()
    cfg = load_config()
    tui = TUIManager(concurrency=2, proxy_manager=pm, config=cfg)

    # Fire some mock events
    tui.on_event("status_update", {"worker_id": 1, "status": "Mencari 'horrornologi'..."})
    tui.on_event("strategy_selected", {"worker_id": 1, "flow_type": "Direct Search Video"})
    tui.on_event("video_picked", {"worker_id": 1, "title": "Misteri Hutan Larangan", "flow_type": "Direct Search Video"})
    tui.on_event("playback_progress", {"worker_id": 1, "percent": 45.0, "formatted_current": "02:15", "formatted_target": "05:00"})
    tui.on_event("ad_event", {"worker_id": 1, "event": "iklan_muncul", "status": "🟡 Tayang Iklan"})
    tui.on_event("verifier_report", {
        "worker_id": 1,
        "score": 100,
        "is_safe": True,
        "webdriver_hidden": True,
        "webrtc_safe": True,
        "webgl": "AMD Radeon HD 3200",
        "canvas_audio_ok": True,
        "ads_allowed": True
    })

    group = tui.render()
    assert group is not None


def test_parse_time_str():
    assert parse_time_str("00:45") == 45.0
    assert parse_time_str("01:30") == 90.0
    assert parse_time_str("20:08") == 1208.0
    assert parse_time_str("01:15:30") == 4530.0
    assert parse_time_str("invalid") is None


def test_check_page_offline_or_error():
    class MockPage:
        def __init__(self, is_offline):
            self._is_offline = is_offline

        def evaluate(self, script):
            return self._is_offline

    assert check_page_offline_or_error(MockPage(True)) is True
    assert check_page_offline_or_error(MockPage(False)) is False
