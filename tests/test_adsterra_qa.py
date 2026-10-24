#!/usr/bin/env python3
"""Tests for the Adsterra ad-render QA suite."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.adsterra.qa import (
    SessionBudget,
    is_proxy_pool_exhausted,
    load_config,
)
from automation.adsterra.report import (
    classify_ad_url,
    host_matches,
    summarize_ad_checks,
    write_session_report,
)
from automation.adsterra.tui import TUIManager
from core.proxy_manager import ProxyManager


def _config():
    return {
        "target_url": "https://article.riztama.my.id/",
        "adsterra_hosts": ["abscloud.org", "bauval.org"],
        "popunder_script_id": "adsterra-popunder",
        "social_bar_script_id": "adsterra-social-bar",
        "native_script_id": "adsterra-native-banner",
        "native_container_id": "container-eff1cc809a63f65a58e6ad5541eb7757",
    }


def _dom(native_present=True, native_rendered=True):
    return {
        "url": "https://article.riztama.my.id/",
        "title": "Gateway to your order page",
        "ready_state": "complete",
        "body_text_length": 1200,
        "scripts": [
            {"src": "https://abscloud.org/1/eeed", "id": "adsterra-popunder"},
            {"src": "https://bauval.org/14/4003", "id": "adsterra-social-bar"},
            {"src": "https://bauval.org/21/eff1", "id": "adsterra-native-banner"},
        ],
        "iframes": [],
        "containers": [],
        "native_container": {
            "present": native_present,
            "id": "container-eff1cc809a63f65a58e6ad5541eb7757",
            "height": 120 if native_rendered else 0,
            "childCount": 1 if native_rendered else 0,
            "iframeCount": 1 if native_rendered else 0,
            "innerHtmlLength": 220 if native_rendered else 0,
            "visibleRatio": 1.0 if native_rendered else 0.0,
            "inViewport": native_rendered,
        },
    }


def _verifier(adblock=False, safe=True):
    return {
        "is_safe": safe,
        "score": 100 if safe else 40,
        "actual_state": {"adblock_detected": adblock},
        "issues": [] if safe else ["WebRTC leak detected"],
    }


def _network():
    return [
        {
            "url": "https://abscloud.org/1/eeed",
            "status": 200,
            "failed": False,
            "resource_type": "script",
        },
        {
            "url": "https://bauval.org/21/eff1",
            "status": 200,
            "failed": False,
            "resource_type": "script",
        },
    ]


def test_load_config():
    config = load_config()
    assert config["target_url"].startswith("https://")
    assert 1 <= config["max_sessions_per_run"] <= 50
    assert 1 <= config["max_sessions_per_proxy"] <= 3


def test_host_matches_and_classify():
    assert host_matches("https://ads.abscloud.org/1/x", ["abscloud.org"])
    assert not host_matches("https://example.com/abscloud.org", ["abscloud.org"])
    assert classify_ad_url("https://abscloud.org/1/x", _config()) == "popunder"
    assert classify_ad_url("https://bauval.org/14/x", _config()) == "social_bar"
    assert classify_ad_url("https://bauval.org/21/x", _config()) == "native_banner"
    assert classify_ad_url("https://example.com/x", _config()) == "other"


def test_summarize_pass():
    summary = summarize_ad_checks(
        dom=_dom(),
        network=_network(),
        page_errors=[],
        console_errors=[],
        popups=[],
        verifier=_verifier(),
        config=_config(),
    )
    assert summary["status"] == "PASS"
    assert summary["score"] == 100
    assert summary["checks"]["native_container_rendered"] is True
    assert summary["checks"]["native_in_viewport"] is True
    assert summary["checks"]["ad_network_seen"] is True
    assert summary["labels"]["adblock_free"] == "PASS"


def test_summarize_fails_without_native_container():
    summary = summarize_ad_checks(
        dom=_dom(native_present=False, native_rendered=False),
        network=_network(),
        page_errors=[],
        console_errors=[],
        popups=[],
        verifier=_verifier(),
        config=_config(),
    )
    assert summary["status"] == "FAIL"
    assert summary["checks"]["native_container_present"] is False
    assert any("container" in issue.lower() for issue in summary["issues"])


def test_summarize_detects_pending_ad_requests():
    dom = _dom()
    dom["native_container"]["childCount"] = 0
    dom["native_container"]["iframeCount"] = 0
    dom["native_container"]["innerHtmlLength"] = 0
    network = [
        {
            "url": "https://abscloud.org/1/eeed",
            "status": None,
            "failed": False,
            "pending": True,
        }
    ]
    summary = summarize_ad_checks(
        dom=dom,
        network=network,
        page_errors=[],
        console_errors=[],
        popups=[],
        verifier=_verifier(),
        config=_config(),
    )
    assert summary["status"] == "FAIL"
    assert summary["checks"]["ad_network_seen"] is True
    assert summary["checks"]["ad_network_ok"] is False
    assert summary["evidence"]["ad_network_pending"] is True
    assert any("did not complete" in issue.lower() for issue in summary["issues"])


def test_summarize_fails_when_main_tab_is_redirected_to_ad_landing():
    dom = _dom(native_present=False, native_rendered=False)
    dom["url"] = "https://bmdeit7.site/?bemobdata=x"
    dom["title"] = "Age Verification"
    dom["body_text_length"] = 27
    summary = summarize_ad_checks(
        dom=dom,
        network=_network(),
        page_errors=[],
        console_errors=[],
        popups=[],
        verifier=_verifier(),
        config=_config(),
        navigations=[
            "https://article.riztama.my.id/",
            "https://bmdeit7.site/?bemobdata=x",
        ],
    )
    assert summary["status"] == "FAIL"
    assert summary["checks"]["page_on_target"] is False
    assert summary["evidence"]["off_target_navigations"] == [
        "https://bmdeit7.site/?bemobdata=x"
    ]
    assert any("left the QA target" in issue for issue in summary["issues"])


def test_summarize_fails_when_native_ad_is_not_visible():
    dom = _dom()
    dom["native_container"]["visibleRatio"] = 0.1
    dom["native_container"]["inViewport"] = True
    summary = summarize_ad_checks(
        dom=dom,
        network=_network(),
        page_errors=[],
        console_errors=[],
        popups=[],
        verifier=_verifier(),
        config=_config(),
    )
    assert summary["status"] == "FAIL"
    assert summary["checks"]["native_in_viewport"] is False
    assert any("visible" in issue.lower() for issue in summary["issues"])


def test_summarize_fails_when_adblock_is_active():
    summary = summarize_ad_checks(
        dom=_dom(),
        network=_network(),
        page_errors=[],
        console_errors=[],
        popups=[],
        verifier=_verifier(adblock=True),
        config=_config(),
    )
    assert summary["status"] == "FAIL"
    assert summary["checks"]["adblock_free"] is False


def test_proxy_pool_exhaustion_detection():
    assert is_proxy_pool_exhausted(
        {"alive": 0, "unknown": 0, "cooldown": 0, "in_use": 0}
    )
    assert not is_proxy_pool_exhausted(
        {"alive": 1, "unknown": 0, "cooldown": 0, "in_use": 0}
    )
    assert not is_proxy_pool_exhausted(
        {"alive": 0, "unknown": 3, "cooldown": 0, "in_use": 0}
    )
    assert not is_proxy_pool_exhausted(
        {"alive": 0, "unknown": 0, "cooldown": 0, "in_use": 1}
    )


def test_session_budget_caps():
    budget = SessionBudget(max_sessions=2, max_sessions_per_proxy=1)
    assert budget.has_capacity()
    assert budget.reserve()
    assert budget.reserve()
    assert not budget.reserve()
    assert budget.can_use_proxy("proxy_a")
    budget.mark_proxy("proxy_a")
    assert not budget.can_use_proxy("proxy_a")
    budget.record("PASS")
    budget.record("FAIL")
    snapshot = budget.snapshot()
    assert snapshot["completed"] == 2
    assert snapshot["passed"] == 1
    assert snapshot["failed"] == 1
    assert budget.is_exhausted()


def test_write_session_report_sanitizes_secrets(tmp_path):
    result = {
        "worker_id": 1,
        "status": "PASS",
        "proxy": {
            "id": "proxy_1",
            "ip": "203.0.113.10",
            "username": "secret-user",
            "password": "secret-pass",
            "proxy_url": "http://secret-user:secret-pass@proxy:8080",
        },
    }
    path = write_session_report(str(tmp_path), result)
    text = path.read_text(encoding="utf-8")
    assert "secret-user" not in text
    assert "secret-pass" not in text
    assert "proxy_1" in text
    assert json.loads(text)["status"] == "PASS"


def test_tui_render_and_state(tmp_path):
    proxy_manager = ProxyManager(filepath=str(tmp_path / "proxies.json"))
    budget = SessionBudget(max_sessions=2, max_sessions_per_proxy=1)
    tui = TUIManager(
        concurrency=1,
        proxy_manager=proxy_manager,
        config=load_config(),
        budget=budget,
    )
    tui.on_event(
        "proxy_assigned",
        {
            "worker_id": 1,
            "proxy_id": "proxy_1",
            "ip": "203.0.113.10",
            "country": "United States",
        },
    )
    tui.on_event(
        "verifier_report",
        {
            "worker_id": 1,
            "score": 100,
            "is_safe": True,
            "webdriver_hidden": True,
            "webrtc_safe": True,
            "webgl": "Native GPU",
            "adblock_detected": False,
        },
    )
    tui.on_event(
        "ad_check",
        {
            "worker_id": 1,
            "status": "PASS",
            "score": 100,
            "checks": {
                "popunder_script_seen": True,
                "social_bar_script_seen": True,
                "native_container_rendered": True,
                "ad_network_seen": True,
            },
        },
    )
    tui.on_event(
        "session_completed",
        {
            "worker_id": 1,
            "status": "PASS",
            "score": 100,
            "report_path": str(tmp_path / "report.json"),
        },
    )
    group = tui.render()
    assert group is not None
    state = tui.public_state()["1"]
    assert state["verdict"] == "PASS"
    assert state["checks"]["native_container_rendered"] is True
