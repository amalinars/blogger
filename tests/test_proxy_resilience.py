import json
import threading
import time

from automation.core.proxy_manager import ProxyManager, probe_proxy_target


def _px(host="1.1.1.1", port=10080, user="u1"):
    return {"host": host, "port": port, "username": user, "password": "p", "country": "US"}


def test_transient_failure_does_not_kill_proxy():
    pm = ProxyManager(
        proxies=[_px()],
        failure_threshold=3,
        check_attempts=1,
    )
    calls = {"n": 0}

    def fake_check(*args, **kwargs):
        calls["n"] += 1
        return (calls["n"] >= 2, "fake")

    pm.check_proxy_alive = fake_check
    pm._target_healthy_direct = lambda *args, **kwargs: True
    proxy, idx = pm.get_valid_proxy()
    assert proxy is not None
    assert idx == 0
    assert pm.dead_indices == set()
    assert calls["n"] == 2


def test_proxy_marked_dead_only_after_threshold():
    pm = ProxyManager(proxies=[_px()], failure_threshold=3)
    with pm.lock:
        assert pm._record_failure_locked(0, "timeout") is False
        assert 0 not in pm.dead_indices
        assert pm._record_failure_locked(0, "timeout") is False
        assert 0 not in pm.dead_indices
        assert pm._record_failure_locked(0, "timeout") is True
        assert 0 in pm.dead_indices


def test_navigation_failures_need_threshold_and_reset_on_success():
    pm = ProxyManager(proxies=[_px()], failure_threshold=3)
    pm._target_healthy_direct = lambda *args, **kwargs: True
    pm.mark_dead(0, "timeout")
    pm.mark_dead(0, "timeout")
    assert 0 not in pm.dead_indices

    pm.report_session_success(0)
    assert pm.nav_failures.get(0, 0) == 0

    pm.mark_dead(0, "timeout")
    pm.mark_dead(0, "timeout")
    pm.mark_dead(0, "timeout")
    assert 0 in pm.dead_indices


def test_dead_state_never_written_to_proxies_file(tmp_path):
    proxy_file = tmp_path / "proxies.json"
    proxy_file.write_text(json.dumps([_px()]), encoding="utf-8")
    pm = ProxyManager(proxy_file_path=str(proxy_file), proxies=[_px()], failure_threshold=1)
    with pm.lock:
        pm._record_failure_locked(0, "timeout")

    on_disk = json.loads(proxy_file.read_text(encoding="utf-8"))
    assert on_disk == [_px()]


def test_new_proxy_added_while_running_is_picked_up(tmp_path):
    proxy_file = tmp_path / "proxies.json"
    proxy_file.write_text(json.dumps([_px(user="u1")]), encoding="utf-8")
    pm = ProxyManager(proxy_file_path=str(proxy_file), proxies=[_px(user="u1")])

    proxy_file.write_text(
        json.dumps([_px(user="u1"), _px(host="2.2.2.2", user="u2")]),
        encoding="utf-8",
    )
    pm.sync_new_proxies_from_disk(force=True)

    assert len(pm.proxies) == 2
    assert pm.proxies[1]["username"] == "u2"


def test_health_checks_are_strictly_serialized():
    proxies = [_px(host=f"10.0.0.{i}", user=f"u{i}") for i in range(1, 6)]
    pm = ProxyManager(proxies=proxies, check_attempts=1)
    state = {"active": 0, "max_active": 0}
    guard = threading.Lock()

    def fake_check(*args, **kwargs):
        with guard:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.03)
        with guard:
            state["active"] -= 1
        return True, "fake"

    pm.check_proxy_alive = fake_check
    results = []
    lock = threading.Lock()

    def worker(wid):
        proxy, idx = pm.get_valid_proxy(worker_id=wid)
        with lock:
            results.append(idx)
        time.sleep(0.02)
        pm.release_proxy(idx, worker_id=wid)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(results) == 5
    assert len(set(results)) == 5
    assert state["max_active"] == 1


def test_proxy_rotation_is_sequential_without_skipping():
    proxies = [_px(host=f"10.0.1.{i}", user=f"u{i}") for i in range(1, 6)]
    pm = ProxyManager(proxies=proxies, check_attempts=1)
    pm.check_proxy_alive = lambda *args, **kwargs: (True, "ok")

    picked = []
    for _ in range(5):
        _, idx = pm.get_valid_proxy()
        picked.append(idx)
        pm.release_proxy(idx)

    assert picked == [0, 1, 2, 3, 4]


def test_probe_requires_http_200(monkeypatch):
    called = []

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    def fake_get(url, **kwargs):
        called.append(url)
        return FakeResponse(204)

    monkeypatch.setattr("automation.core.proxy_manager.requests.get", fake_get)
    ok, reason = probe_proxy_target(_px(), timeout=1.0)
    assert ok is False
    assert "bukan 200" in reason
    assert called
    assert "read.riztama.my.id" in called[0]


def test_hard_failure_marks_dead_and_scan_continues_to_good_proxy():
    pm = ProxyManager(
        proxies=[_px(host="1.1.1.1", user="u1"), _px(host="2.2.2.2", user="u2")],
        failure_threshold=3,
        check_attempts=1,
    )
    calls = []

    def fake_check(px, *args, **kwargs):
        calls.append(px["username"])
        if px["username"] == "u1":
            return False, "402 Payment Required (saldo/akun proxy habis)"
        return True, "HTTP 200 OK"

    pm.check_proxy_alive = fake_check
    pm._target_healthy_direct = lambda *args, **kwargs: True

    proxy, idx = pm.get_valid_proxy()

    assert idx == 1
    assert proxy["username"] == "u2"
    assert calls == ["u1", "u2"]
    assert 0 in pm.dead_indices


def test_target_unhealthy_does_not_mark_proxy_dead():
    pm = ProxyManager(proxies=[_px()], failure_threshold=1, check_attempts=1)
    pm._target_guard_ttl = 0.0
    pm.check_proxy_alive = lambda *args, **kwargs: (False, "timeout")
    pm._target_healthy_direct = lambda *args, **kwargs: False

    proxy, idx = pm.get_valid_proxy()

    assert proxy is None
    assert idx is None
    assert pm.dead_indices == set()
    assert pm.failure_counts.get(0, 0) == 0
