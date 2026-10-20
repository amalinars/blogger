import pytest
from automation.core.browser import build_browser_args, format_proxy_dict
from automation.core.proxy_manager import ProxyManager, ProxyUnavailableError, resolve_proxy_path
from automation.core.human import smooth_scroll, natural_mouse_move, physical_click
from automation.core.stealth import get_geo_profile, get_fingerprint_profile
from automation.youtube.bot import load_config as load_yt_config


def test_build_browser_args():
    args = build_browser_args(window_position=(100, 200), window_size=(1280, 720))
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--enforce-webrtc-ip-permission-check" in args
    assert "--window-position=100,200" in args
    assert "--window-size=1280,720" in args


def test_format_proxy_dict():
    raw_px = {"host": "1.2.3.4", "port": 8080, "username": "user", "password": "pwd"}
    formatted = format_proxy_dict(raw_px)
    assert formatted["server"] == "http://1.2.3.4:8080"
    assert formatted["username"] == "user"
    assert formatted["password"] == "pwd"

    assert format_proxy_dict(None) is None
    assert format_proxy_dict({}) is None


def test_core_proxy_manager():
    dummy_proxies = [
        {"host": "1.1.1.1", "port": 80, "country": "US"},
        {"host": "2.2.2.2", "port": 80, "country": "GB", "dead": True},
    ]
    pm = ProxyManager(proxies=dummy_proxies)
    assert len(pm.proxies) == 2
    assert 1 in pm.dead_indices


def test_youtube_config_loads():
    cfg = load_yt_config()
    assert "target_video_url" in cfg
    assert "watch_duration" in cfg
