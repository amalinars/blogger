import pytest
from automation.traffic_bot import ProxyManager, ProxyUnavailableError, run_single_session_safe

def test_proxy_manager_exhausted_returns_none():
    pm = ProxyManager(proxies=[])
    proxy, idx = pm.get_valid_proxy()
    assert proxy is None
    assert idx is None

def test_anti_leak_aborts_session_when_proxy_required():
    # When use_proxy is True, passing proxy=None must be safely rejected
    res = run_single_session_safe(use_proxy=True, proxy=None)
    assert res is False
