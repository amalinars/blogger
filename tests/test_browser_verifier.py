import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import automation.browser_verifier as bv
from automation.browser_verifier import (
    BrowserVerifier,
    _isp_matches,
    _is_private_or_local_ip,
    _normalize_asn,
)

GOOD_FP = {
    "platform": "Win32",
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "webdriver": False,
    "webgl_vendor": "NVIDIA Corporation",
    "webgl_renderer": "ANGLE (NVIDIA GeForce GTX 1080 Direct3D11)",
    "canvas_ok": True,
    "audio_ok": True,
    "plugins_ok": True,
}


def _make_verifier(monkeypatch, ip_data, local_ips=None):
    verifier = BrowserVerifier(strict_mode=True)
    monkeypatch.setattr(verifier, "_inspect_network", lambda page: dict(ip_data))
    monkeypatch.setattr(verifier, "_inspect_fingerprint", lambda page: dict(GOOD_FP))
    monkeypatch.setattr(
        bv, "_get_local_egress_ips", lambda: set(local_ips or [])
    )
    return verifier


SKY_IP = {
    "query": "90.214.34.176",
    "country": "United Kingdom",
    "countryCode": "GB",
    "isp": "Sky UK Limited",
    "org": "Sky Broadband",
    "as": "AS5607 Sky UK Limited",
}


def test_rotation_within_same_asn_is_accepted(monkeypatch):
    verifier = _make_verifier(monkeypatch, SKY_IP)

    report = verifier.verify(
        page=None,
        expected_ip="90.199.100.72",
        expected_asn="AS5607",
        expected_isp="Sky UK Limited",
        allow_ip_rotation=True,
        check_ads=False,
    )

    assert report.match_results["ip_matched"] is True
    assert report.is_safe is True
    assert not any("di luar pool" in issue for issue in report.issues)


def test_rotation_with_matching_isp_but_other_asn_is_accepted(monkeypatch):
    verifier = _make_verifier(monkeypatch, SKY_IP)

    report = verifier.verify(
        page=None,
        expected_asn="AS99999",
        expected_isp="Sky Broadband",
        allow_ip_rotation=True,
        check_ads=False,
    )

    assert report.match_results["ip_matched"] is True
    assert report.is_safe is True


def test_rotation_outside_pool_fails(monkeypatch):
    other_ip = {
        "query": "90.214.34.176",
        "country": "United Kingdom",
        "countryCode": "GB",
        "isp": "Other Telecom Ltd",
        "org": "Other Telecom Ltd",
        "as": "AS12345 Other Telecom",
    }
    verifier = _make_verifier(monkeypatch, other_ip)

    report = verifier.verify(
        page=None,
        expected_asn="AS5607",
        expected_isp="Sky UK Limited",
        allow_ip_rotation=True,
        check_ads=False,
    )

    assert report.match_results["ip_matched"] is False
    assert report.is_safe is False
    assert any("di luar pool" in issue for issue in report.issues)


def test_rotation_detects_real_local_ip_leak(monkeypatch):
    verifier = _make_verifier(
        monkeypatch, SKY_IP, local_ips={"90.214.34.176"}
    )

    report = verifier.verify(
        page=None,
        expected_asn="AS5607",
        expected_isp="Sky UK Limited",
        allow_ip_rotation=True,
        check_ads=False,
    )

    assert report.match_results["ip_matched"] is False
    assert report.is_safe is False
    assert any("IP asli mesin bocor" in issue for issue in report.issues)


def test_rotation_without_metadata_uses_warning(monkeypatch):
    unknown_ip = {
        "query": "8.8.8.8",
        "country": "Unknown",
        "countryCode": "",
        "isp": "Unknown",
        "org": "",
    }
    verifier = _make_verifier(monkeypatch, unknown_ip)

    report = verifier.verify(
        page=None,
        expected_asn="AS5607",
        allow_ip_rotation=True,
        check_ads=False,
    )

    assert report.match_results["ip_matched"] is None
    assert any("tidak bisa dipastikan" in warning for warning in report.warnings)


def test_static_proxy_still_requires_exact_ip(monkeypatch):
    verifier = _make_verifier(monkeypatch, SKY_IP)

    report = verifier.verify(
        page=None,
        expected_ip="90.199.100.72",
        allow_ip_rotation=False,
        check_ads=False,
    )

    assert report.match_results["ip_matched"] is False
    assert report.is_safe is False
    assert any("IP Mismatch" in issue for issue in report.issues)


def test_helpers_normalize_and_detect():
    assert _normalize_asn("AS5607 Sky UK Limited") == "AS5607"
    assert _normalize_asn("as 4134 China Telecom") == "AS4134"
    assert _normalize_asn("Sky UK") == ""

    assert _isp_matches("Sky UK Limited", "Sky Broadband") is True
    assert _isp_matches("Sky Broadband", "Other Telecom") is False

    assert _is_private_or_local_ip("192.168.1.10") is True
    assert _is_private_or_local_ip("127.0.0.1") is True
    assert _is_private_or_local_ip("90.214.34.176") is False