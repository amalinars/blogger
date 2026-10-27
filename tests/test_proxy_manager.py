import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.proxy_manager as proxy_manager
from core.proxy_manager import (
    ProxyManager,
    HEALTH_ALIVE,
    HEALTH_DEAD,
    HEALTH_UNKNOWN,
    HEALTH_COOLDOWN,
    USAGE_IDLE,
    USAGE_IN_USE,
)


@pytest.fixture
def temp_proxy_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "proxies.json")
        sample_data = {
            "cursor": 0,
            "proxies": [
                {
                    "id": "p1",
                    "proxy_url": "http://user1:pass1@1.1.1.1:8080",
                    "health": HEALTH_ALIVE,
                    "usage": USAGE_IDLE,
                    "last_checked": 9999999999.0,  # fresh
                },
                {
                    "id": "p2",
                    "proxy_url": "http://user2:pass2@2.2.2.2:8080",
                    "health": HEALTH_DEAD,
                    "usage": USAGE_IDLE,
                    "last_checked": 1000.0,
                },
                {
                    "id": "p3",
                    "proxy_url": "http://user3:pass3@3.3.3.3:8080",
                    "health": HEALTH_ALIVE,
                    "usage": USAGE_IDLE,
                    "last_checked": 9999999999.0,
                },
                {
                    "id": "p4",
                    "proxy_url": "http://user4:pass4@4.4.4.4:8080",
                    "health": HEALTH_UNKNOWN,
                    "usage": USAGE_IDLE,
                },
            ],
        }
        with open(filepath, "w") as f:
            json.dump(sample_data, f)
        yield filepath


def test_migration_from_legacy_flat_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "legacy.json")
        legacy_data = [
            {"country": "US", "proxy_url": "http://test:test@10.0.0.1:8080", "status": "idle"},
            {"country": "CA", "proxy_url": "http://test:test@10.0.0.2:8080", "status": "idle"},
        ]
        with open(filepath, "w") as f:
            json.dump(legacy_data, f)

        pm = ProxyManager(filepath=filepath)
        stats = pm.get_stats()
        assert stats["total"] == 2
        assert stats["cursor"] == 0
        proxies = pm.get_proxies()
        assert len(proxies) == 2
        assert proxies[0]["proxy_url"] == "http://test:test@10.0.0.1:8080"
        assert proxies[0]["health"] == HEALTH_UNKNOWN
        assert proxies[0]["usage"] == USAGE_IDLE


def test_add_remove_and_stats(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    stats = pm.get_stats()
    assert stats["total"] == 4
    assert stats["alive"] == 2
    assert stats["dead"] == 1
    assert stats["unknown"] == 1

    # Add new proxy
    new_p = pm.add_proxy({"proxy_url": "http://user5:pass5@5.5.5.5:8080", "country": "DE"})
    assert new_p["id"] is not None
    assert pm.get_stats()["total"] == 5

    # Remove proxy
    removed = pm.remove_proxy(new_p["id"])
    assert removed is True
    assert pm.get_stats()["total"] == 4


def test_continuous_rotation_cursor(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # File initially has cursor at 0.
    # p1 is ALIVE -> should acquire p1. Cursor becomes (0 + 1) % 4 = 1.
    alloc1 = pm.acquire_proxy(caller_id="worker_1")
    assert alloc1 is not None
    assert alloc1["id"] == "p1"
    assert alloc1["usage"] == USAGE_IN_USE

    # Verify cursor saved to file
    with open(temp_proxy_file, "r") as f:
        saved = json.load(f)
    assert saved["cursor"] == 1

    # Next acquire starts at index 1 (p2, which is DEAD -> skip).
    # Then index 2 is p3 (ALIVE) -> should acquire p3.
    # Cursor advances to (2 + 1) % 4 = 3.
    alloc2 = pm.acquire_proxy(caller_id="worker_2")
    assert alloc2 is not None
    assert alloc2["id"] == "p3"

    with open(temp_proxy_file, "r") as f:
        saved = json.load(f)
    assert saved["cursor"] == 3


def test_persistence_across_restart(temp_proxy_file):
    pm1 = ProxyManager(filepath=temp_proxy_file)
    a1 = pm1.acquire_proxy(caller_id="caller_A")
    assert a1["id"] == "p1"

    # Simulate restart by creating a new ProxyManager instance on the same file
    pm2 = ProxyManager(filepath=temp_proxy_file)
    assert pm2.get_stats()["cursor"] == 1

    # Next acquisition continues from saved cursor (skips DEAD p2, acquires p3)
    a2 = pm2.acquire_proxy(caller_id="caller_B")
    assert a2["id"] == "p3"
    assert pm2.get_stats()["cursor"] == 3


def test_acquire_and_release(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    alloc = pm.acquire_proxy(caller_id="job_99")
    assert alloc["id"] == "p1"

    # Check status is IN_USE
    p1_data = next(p for p in pm.get_proxies() if p["id"] == "p1")
    assert p1_data["usage"] == USAGE_IN_USE
    assert p1_data["leased_by"] == "job_99"

    # Release by wrong caller should fail
    fail_release = pm.release_proxy("p1", caller_id="imposter")
    assert fail_release is False
    assert next(p for p in pm.get_proxies() if p["id"] == "p1")["usage"] == USAGE_IN_USE

    # Release by correct caller
    success_release = pm.release_proxy("p1", caller_id="job_99")
    assert success_release is True
    p1_after = next(p for p in pm.get_proxies() if p["id"] == "p1")
    assert p1_after["usage"] == USAGE_IDLE
    assert p1_after["health"] == HEALTH_ALIVE


def test_release_does_not_revive_dead_proxy(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # p2 is DEAD
    p2 = next(p for p in pm.get_proxies() if p["id"] == "p2")
    assert p2["health"] == HEALTH_DEAD

    # Releasing p2 must keep health as DEAD
    pm.release_proxy("p2")
    p2_after = next(p for p in pm.get_proxies() if p["id"] == "p2")
    assert p2_after["health"] == HEALTH_DEAD


def test_validate_unknown_on_acquire(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # Set cursor to p4 (index 3), which is UNKNOWN
    with open(temp_proxy_file, "r") as f:
        data = json.load(f)
    data["cursor"] = 3
    with open(temp_proxy_file, "w") as f:
        json.dump(data, f)

    # Mock network test to succeed for p4
    with patch.object(pm, "_test_proxy_network", return_value={"success": True, "ip": "4.4.4.4", "latency_ms": 110, "error": None}):
        alloc = pm.acquire_proxy(caller_id="worker_unknown")
        assert alloc is not None
        assert alloc["id"] == "p4"
        assert alloc["health"] == HEALTH_ALIVE
        assert alloc["usage"] == USAGE_IN_USE


def test_report_failure_transient_vs_fatal(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    alloc = pm.acquire_proxy(caller_id="job_fail")
    assert alloc["id"] == "p1"

    # 1. Transient website error (e.g., 502 Bad Gateway from target website)
    res = pm.report_failure("p1", error_message="HTTP 502 Bad Gateway from target", is_proxy_error=False)
    assert res["health"] == HEALTH_COOLDOWN
    assert res["fail_count"] == 1

    # Release should still work smoothly
    assert pm.release_proxy("p1", caller_id="job_fail") is True

    # 2. Fatal proxy error (e.g. ProxyError / connection refused)
    with patch.object(pm, "_test_proxy_network", return_value={"success": False, "ip": None, "latency_ms": None, "error": "ConnectionRefused"}):
        res2 = pm.report_failure("p1", error_message="ProxyError: Cannot connect to proxy", is_proxy_error=True)
        assert res2["health"] == HEALTH_DEAD
        assert "Dead confirmed" in res2["last_error"]


def test_three_strike_rule_and_timeout_cooldown(temp_proxy_file):
    """Memverifikasi bahwa timeout selalu diberi COOLDOWN dan koneksi tidak terjangkau mati total pada percobaan ke-3."""
    pm = ProxyManager(filepath=temp_proxy_file)

    # 1. Timeout -> COOLDOWN
    res_to = pm.report_failure("p1", error_message="Page.goto: Timeout 30000ms exceeded.")
    assert res_to["health"] == HEALTH_COOLDOWN
    assert res_to["fail_count"] == 1

    # 2. Unreachable percobaan ke-2 (mock test network success agar tidak instant dead)
    with patch.object(pm, "_test_proxy_network", return_value={"success": True, "ip": "1.1.1.1", "latency_ms": 200, "error": None}):
        res_un1 = pm.report_failure("p1", error_message="ConnectionRefused: Target web unreachable")
        assert res_un1["health"] == HEALTH_COOLDOWN
        assert res_un1["fail_count"] == 2

    # 3. Unreachable percobaan ke-3 -> MATI TOTAL (DEAD)
    res_un2 = pm.report_failure("p1", error_message="ConnectionRefused: Target web unreachable")
    assert res_un2["health"] == HEALTH_DEAD
    assert res_un2["fail_count"] == 3
    assert "DEAD" in res_un2["last_error"]


def test_revalidate_dead(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # p2 is DEAD. Test revalidate_dead with mocked success.
    with patch.object(pm, "_test_proxy_network", return_value={"success": True, "ip": "2.2.2.2", "latency_ms": 150, "error": None}):
        result = pm.revalidate_dead()
        assert result["restored"] >= 1

    p2 = next(p for p in pm.get_proxies() if p["id"] == "p2")
    assert p2["health"] == HEALTH_ALIVE


def test_no_available_proxies_avoids_infinite_loop(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # Mark all proxies as DEAD
    data = pm._load_raw()
    for p in data["proxies"]:
        p["health"] = HEALTH_DEAD
    pm._save_raw(data)

    # Must return None safely without infinite loop
    result = pm.acquire_proxy()
    assert result is None


def test_concurrent_exclusive_acquire(temp_proxy_file):
    import concurrent.futures

    pm = ProxyManager(filepath=temp_proxy_file)
    # File has 2 ALIVE proxies (p1, p3) and p4 is UNKNOWN (mock as DEAD)
    results = []

    def worker_acquire(worker_num):
        with patch.object(pm, "_test_proxy_network", return_value={"success": False, "ip": None, "latency_ms": None, "error": "Timeout"}):
            res = pm.acquire_proxy(caller_id=f"thread_{worker_num}")
            return res

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_acquire, i) for i in range(5)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                results.append(res)

    # There are only 2 ALIVE proxies, so exactly 2 should be acquired, no double allocation
    acquired_ids = [r["id"] for r in results]
    assert len(acquired_ids) == 2
    assert len(set(acquired_ids)) == 2  # No duplicate
    assert "p1" in acquired_ids
    assert "p3" in acquired_ids


def test_append_proxies_dict_and_string(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    initial_total = pm.get_stats()["total"]

    # Append list containing dict and raw string formats
    new_items = [
        {"proxy_url": "http://u1:p1@10.0.0.1:8080", "country": "Singapore"},
        "http://u2:p2@10.0.0.2:8080",
        "10.0.0.3:8080:u3:p3",
        {"proxy_url": "http://user1:pass1@1.1.1.1:8080"},  # duplicate of p1, should be ignored
    ]
    added = pm.append_proxies(new_items)
    assert added == 3
    assert pm.get_stats()["total"] == initial_total + 3

    # Test get_proxy_by_index
    item_at_0 = pm.get_proxy_by_index(0)
    assert item_at_0["id"] == "p1"
    assert pm.get_proxy_by_index(999) is None


def test_delete_dead_proxies(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    stats_before = pm.get_stats()
    assert stats_before["dead"] >= 1

    # Delete all DEAD proxies
    removed = pm.delete_dead_proxies()
    assert removed == stats_before["dead"]

    # Verify no DEAD proxies left
    stats_after = pm.get_stats()
    assert stats_after["dead"] == 0
    assert stats_after["total"] == stats_before["total"] - removed

    # Test calling delete_dead again when none exist
    removed_second = pm.delete_dead()
    assert removed_second == 0


def test_reset_usage_to_idle(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # Lease a proxy first
    alloc = pm.acquire_proxy(caller_id="worker_leak")
    assert alloc is not None
    assert alloc["usage"] == USAGE_IN_USE

    # Verify state in manager
    stats = pm.get_stats()
    assert stats["in_use"] >= 1

    # Reset usage
    cleaned = pm.reset_usage_to_idle()
    assert cleaned >= 1

    # Verify all are now IDLE
    stats_after = pm.get_stats()
    assert stats_after["in_use"] == 0
    assert stats_after["idle"] == stats_after["total"]


def test_reset_cursor(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)
    # Advance cursor
    pm.acquire_proxy(caller_id="w1")
    assert pm.get_stats()["cursor"] > 0

    # Reset cursor back to 0
    new_cur = pm.reset_cursor(0)
    assert new_cur == 0
    assert pm.get_stats()["cursor"] == 0


def test_acquire_proxy_with_verify_alive(temp_proxy_file):
    pm = ProxyManager(filepath=temp_proxy_file)

    # Mock _test_proxy_network to simulate first proxy failing, second proxy succeeding
    call_count = 0
    def mock_test_net(url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First proxy candidate fails network check
            return {"success": False, "ip": None, "latency_ms": None, "error": "Connection timed out"}
        else:
            # Second proxy candidate passes network check
            return {"success": True, "ip": "203.0.113.5", "latency_ms": 120.5, "error": None}

    with patch.object(pm, "_test_proxy_network", side_effect=mock_test_net):
        # Even if p1 was ALIVE in JSON, verify_alive=True causes live check!
        alloc = pm.acquire_proxy(caller_id="verifier_worker", verify_alive=True)
        assert alloc is not None
        # First proxy failed and was marked DEAD, so candidate 2 or next working was returned
        assert alloc["ip_detected"] == "203.0.113.5"
        assert alloc["health"] == HEALTH_ALIVE





