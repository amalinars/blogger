#!/usr/bin/env python3
"""Adsterra ad-render QA scoring and report persistence."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

DEFAULT_AD_HOSTS = ("abscloud.org", "bauval.org")
SENSITIVE_KEYS = {
    "proxy_url",
    "username",
    "password",
    "leased_by",
    "lease_token",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def same_host(url: str, expected_url: str) -> bool:
    try:
        current = (urlparse(url).hostname or "").lower()
        expected = (urlparse(expected_url).hostname or "").lower()
    except Exception:
        return False
    return bool(current and expected and current == expected)


def host_matches(url: str, hosts: List[str]) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    for candidate in hosts:
        candidate = candidate.strip().lower()
        if candidate and (host == candidate or host.endswith(f".{candidate}")):
            return True
    return False


def is_ad_url(url: str, config: Dict[str, Any]) -> bool:
    return host_matches(url, list(config.get("adsterra_hosts") or DEFAULT_AD_HOSTS))


def classify_ad_url(url: str, config: Dict[str, Any]) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    popunder_hosts = ["abscloud.org"]
    if host_matches(url, popunder_hosts):
        return "popunder"

    if host_matches(url, ["bauval.org"]):
        if "/14/" in path:
            return "social_bar"
        if "/21/" in path:
            return "native_banner"
        return "bauval"

    if is_ad_url(url, config):
        return "adsterra"

    return "other"


def _script_has_src(scripts: List[Dict[str, Any]], host: str, path_fragment: Optional[str] = None) -> bool:
    for script in scripts:
        src = script.get("src") or ""
        if not host_matches(src, [host]):
            continue
        if path_fragment is None or path_fragment in src:
            return True
    return False


def _script_has_id(scripts: List[Dict[str, Any]], script_id: str) -> bool:
    return any(script.get("id") == script_id for script in scripts)


def _mark(value: Optional[bool]) -> str:
    if value is None:
        return "SKIP"
    return "PASS" if value else "FAIL"


def summarize_ad_checks(
    dom: Dict[str, Any],
    network: List[Dict[str, Any]],
    page_errors: List[str],
    console_errors: List[str],
    popups: List[str],
    verifier: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    navigations: Optional[List[str]] = None,
    blocked_navigations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Turn raw browser evidence into a deterministic QA verdict."""
    scripts = dom.get("scripts") or []
    target_url = config.get("target_url") or ""
    page_on_target: Optional[bool] = None
    if target_url and dom.get("url"):
        page_on_target = same_host(dom.get("url", ""), target_url)
    off_target_navigations = [
        url
        for url in (navigations or [])
        if target_url and url and not same_host(url, target_url)
    ]
    native_id = config.get("native_container_id", "")
    native_container = dom.get("native_container") or {"present": False, "id": native_id}

    popunder_id = config.get("popunder_script_id", "adsterra-popunder")
    social_id = config.get("social_bar_script_id", "adsterra-social-bar")
    native_script_id = config.get("native_script_id", "adsterra-native-banner")

    popunder_script_seen = _script_has_id(scripts, popunder_id) or _script_has_src(
        scripts, "abscloud.org"
    )
    social_script_seen = _script_has_id(scripts, social_id) or _script_has_src(
        scripts, "bauval.org", "/14/"
    )
    native_script_seen = _script_has_id(scripts, native_script_id) or _script_has_src(
        scripts, "bauval.org", "/21/"
    )

    ad_network = [
        entry for entry in network if is_ad_url(entry.get("url", ""), config)
    ]
    ad_network_ok = any(
        not entry.get("failed")
        and isinstance(entry.get("status"), int)
        and 200 <= entry["status"] < 400
        for entry in ad_network
    )
    ad_network_pending = any(entry.get("pending") for entry in ad_network)

    native_present = bool(native_container.get("present"))
    native_rendered = bool(
        native_present
        and native_container.get("height", 0) >= 20
        and (
            native_container.get("childCount", 0) > 0
            or native_container.get("iframeCount", 0) > 0
            or native_container.get("innerHtmlLength", 0) > 100
        )
    )
    min_visible_ratio = float(config.get("min_visible_ratio", 0.5))
    native_in_viewport = bool(
        native_present
        and native_container.get("visibleRatio", 0) >= min_visible_ratio
    )

    verifier_actual = (verifier or {}).get("actual_state") or {}
    verifier_is_safe = (verifier or {}).get("is_safe")
    adblock_detected = verifier_actual.get("adblock_detected")

    checks: Dict[str, Optional[bool]] = {
        "page_loaded": bool(
            dom.get("title")
            and dom.get("body_text_length", 0) > 0
            and dom.get("ready_state") in ("interactive", "complete")
        ),
        "page_on_target": page_on_target,
        "verifier_passed": None if verifier_is_safe is None else bool(verifier_is_safe),
        "adblock_free": None if adblock_detected is None else not bool(adblock_detected),
        "popunder_script_seen": popunder_script_seen,
        "social_bar_script_seen": social_script_seen,
        "native_script_seen": native_script_seen,
        "native_container_present": native_present,
        "native_container_rendered": native_rendered,
        "native_in_viewport": native_in_viewport,
        "ad_network_seen": bool(ad_network),
        "ad_network_ok": ad_network_ok,
        "no_page_errors": not page_errors,
        "no_console_errors": not console_errors,
    }

    weights = [
        ("page_loaded", 20),
        ("page_on_target", 10),
        ("verifier_passed", 20),
        ("adblock_free", 10),
        ("popunder_script_seen", 5),
        ("social_bar_script_seen", 10),
        ("native_script_seen", 10),
        ("native_container_present", 10),
        ("native_container_rendered", 10),
        ("native_in_viewport", 10),
        ("ad_network_seen", 10),
        ("ad_network_ok", 5),
    ]
    applicable = [(name, weight) for name, weight in weights if checks.get(name) is not None]
    total_weight = sum(weight for _, weight in applicable)
    passed_weight = sum(
        weight for name, weight in applicable if checks.get(name) is True
    )
    score = round((passed_weight / total_weight) * 100) if total_weight else 0

    critical = [
        "page_loaded",
        "page_on_target",
        "native_container_present",
        "native_container_rendered",
        "native_in_viewport",
        "ad_network_seen",
        "ad_network_ok",
    ]
    if checks.get("verifier_passed") is not None:
        critical.append("verifier_passed")
    if checks.get("adblock_free") is not None:
        critical.append("adblock_free")

    issues: List[str] = []
    if not checks["page_loaded"]:
        issues.append("Landing page did not reach a usable loaded state.")
    if checks.get("page_on_target") is False:
        issues.append(
            "Main tab left the QA target and ended on "
            f"{(urlparse(dom.get('url', '')).hostname or dom.get('url', 'unknown'))}."
        )
    if off_target_navigations:
        hosts = []
        for url in off_target_navigations:
            host = urlparse(url).hostname or url
            if host not in hosts:
                hosts.append(host)
        issues.append(
            "Main tab navigated away from the QA target to: "
            + ", ".join(hosts[:5])
            + "."
        )
    if blocked_navigations:
        hosts = []
        for url in blocked_navigations:
            host = urlparse(url).hostname or url
            if host not in hosts:
                hosts.append(host)
        issues.append(
            "Blocked main-tab redirect(s) to ad landing page(s): "
            + ", ".join(hosts[:5])
            + "."
        )
    if not checks["native_container_present"]:
        issues.append(f"Native banner container '{native_id}' was not found.")
    elif not checks["native_container_rendered"]:
        issues.append("Native banner container exists but has no rendered ad content.")
    if checks["native_container_rendered"] and not checks["native_in_viewport"]:
        issues.append(
            "Native banner is rendered but not sufficiently visible in the viewport."
        )
    if not checks["ad_network_seen"]:
        issues.append("No request to an Adsterra network was observed.")
    elif not checks["ad_network_ok"]:
        if ad_network_pending:
            issues.append(
                "Ad network requests were started but did not complete within "
                "the inspection window (proxy or network may block ad domains)."
            )
        else:
            issues.append(
                "Ad network requests were observed but none returned a successful response."
            )
    if checks.get("verifier_passed") is False:
        verifier_issues = (verifier or {}).get("issues") or []
        detail = "; ".join(str(item) for item in verifier_issues[:3])
        issues.append(f"Browser verifier failed{': ' + detail if detail else '.'}")
    if checks.get("adblock_free") is False:
        issues.append("AdBlock or tracking protection appears to hide ad units.")
    if not checks["popunder_script_seen"]:
        issues.append("Popunder script tag was not observed.")
    if not checks["social_bar_script_seen"]:
        issues.append("Social bar script tag was not observed.")
    if page_errors:
        issues.append(f"{len(page_errors)} page error(s) captured.")
    if console_errors:
        issues.append(f"{len(console_errors)} console error(s) captured.")

    if any(checks.get(name) is False for name in critical):
        status = "FAIL"
    elif score >= 90 and checks["no_page_errors"] and checks["no_console_errors"]:
        status = "PASS"
    else:
        status = "WARN"

    evidence_network = []
    for entry in ad_network[:50]:
        evidence_network.append(
            {
                "url": entry.get("url", "")[:500],
                "kind": classify_ad_url(entry.get("url", ""), config),
                "status": entry.get("status"),
                "failed": bool(entry.get("failed")),
                "pending": bool(entry.get("pending")),
                "error": (entry.get("error") or "")[:300],
                "resource_type": entry.get("resource_type"),
            }
        )

    evidence = {
        "page": {
            "url": dom.get("url", ""),
            "title": dom.get("title", ""),
            "ready_state": dom.get("ready_state", ""),
            "body_text_length": dom.get("body_text_length", 0),
        },
        "scripts": scripts[:50],
        "iframes": (dom.get("iframes") or [])[:20],
        "native_container": native_container,
        "ad_network": evidence_network,
        "ad_network_pending": ad_network_pending,
        "navigations": (navigations or [])[:20],
        "off_target_navigations": off_target_navigations[:20],
        "blocked_navigations": (blocked_navigations or [])[:20],
        "resources": (dom.get("resources") or [])[:20],
        "popups": popups[:10],
        "page_errors": page_errors[:20],
        "console_errors": console_errors[:20],
        "verifier": {
            "is_safe": verifier_is_safe,
            "score": (verifier or {}).get("score"),
            "issues": ((verifier or {}).get("issues") or [])[:10],
            "actual_state": verifier_actual,
        },
    }

    return {
        "status": status,
        "score": score,
        "checks": checks,
        "issues": issues,
        "evidence": evidence,
        "labels": {name: _mark(value) for name, value in checks.items()},
    }


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_payload(item)
            for key, item in value.items()
            if key.lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def write_session_report(report_dir: str, result: Dict[str, Any]) -> Path:
    report_root = Path(report_dir)
    worker_id = result.get("worker_id", 1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = report_root / f"session_{stamp}_w{worker_id}.json"
    _atomic_write_json(path, sanitize_payload(result))
    return path


def write_run_summary(report_dir: str, summary: Dict[str, Any]) -> Path:
    report_root = Path(report_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = report_root / f"summary_{stamp}.json"
    _atomic_write_json(path, sanitize_payload(summary))
    return path
