import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.monetag import flow
from automation.monetag.flow import (
    MonetagNoAdError,
    MonetagProxyError,
    MonetagVerificationError,
    _classify_session_error,
    monetag_worker_thread_loop,
)


class FakeBudget:
    def __init__(self, max_sessions=None):
        self.max_sessions = max_sessions
        self.unlimited = max_sessions is None
        self.reserved = 0
        self.results = []

    def is_exhausted(self):
        return False if self.unlimited else self.reserved >= self.max_sessions

    def has_capacity(self):
        return self.unlimited or self.reserved < self.max_sessions

    def reserve(self):
        if not self.has_capacity():
            return False
        self.reserved += 1
        return True

    def record(self, status):
        self.results.append(status)

    def mark_proxy(self, proxy_id):
        pass


class FakeChainProvider:
    def __init__(self, proxies):
        if isinstance(proxies, dict):
            proxies = [proxies]
        self.proxies = list(proxies)
        self.pm = self
        self.batch_index = 0
        self.next_calls = 0
        self.targets = []
        self.finished = []
        self.hits = []

    def next_proxy(self, caller_id=None, log_prefix="", target=None, lease_seconds=600):
        self.next_calls += 1
        self.targets.append(target)
        return self.proxies[min(self.batch_index, len(self.proxies) - 1)]

    def get_target_usage_summary(self, *args, **kwargs):
        return {}

    def acquire_proxy(self, **kwargs):
        return None

    def release_proxy(self, proxy, **kwargs):
        return True

    def record_target_hit(self, proxy, target=None, **kwargs):
        self.hits.append(target)
        return True

    def finish_session(self, proxy, success, error=None, error_kind="other", log_prefix=""):
        self.finished.append((success, error_kind))
        if not success or error_kind == "batch":
            self.batch_index += 1


class NoDirectProxyCalls:
    supabase_enabled = True

    def __getattr__(self, name):
        raise AssertionError(f"direct proxy_manager.{name} tidak boleh dipanggil di mode chain")


def _chain_proxy(index=1, target_usage=None):
    residential = {"id": index, "supabase_id": index, "host": "r", "port": 1}
    if target_usage is not None:
        residential["target_usage"] = target_usage
    return {
        "id": f"chain#{index}",
        "supabase_id": index,
        "host": "127.0.0.1",
        "port": 41000 + index,
        "expected_ip": f"203.0.113.{index}",
        "country": "United States",
        "source": "chain",
        "_residential": residential,
    }


def _run_one_session(monkeypatch, session_func, expected_status):
    stop_event = threading.Event()
    provider = FakeChainProvider(_chain_proxy())
    budget = FakeBudget()

    def fake_session(**_kwargs):
        stop_event.set()
        return session_func()

    monkeypatch.setattr(flow, "run_monetag_session", fake_session)

    monetag_worker_thread_loop(
        worker_id=1,
        config={
            "max_uses_per_day": 2,
            "proxy_cooldown_hours": 6.0,
            "target_url": "https://article.riztama.my.id/post-1",
        },
        proxy_manager=NoDirectProxyCalls(),
        budget=budget,
        stop_event=stop_event,
        chain_provider=provider,
    )

    assert provider.next_calls == 1
    assert provider.targets == ["monetag:article.riztama.my.id"]
    assert budget.results == [expected_status]
    return provider


def test_worker_url_offset_per_worker(monkeypatch):
    stop_event = threading.Event()
    provider = FakeChainProvider(_chain_proxy())
    budget = FakeBudget()

    def fake_session(**_kwargs):
        stop_event.set()
        return {"success": True}

    monkeypatch.setattr(flow, "run_monetag_session", fake_session)
    monetag_worker_thread_loop(
        worker_id=2,
        config={
            "max_uses_per_day": 2,
            "proxy_cooldown_hours": 6.0,
            "target_urls": ["https://a.example.com", "https://b.example.com"],
        },
        proxy_manager=NoDirectProxyCalls(),
        budget=budget,
        stop_event=stop_event,
        chain_provider=provider,
    )
    assert provider.targets == ["monetag:b.example.com"]


def test_worker_chain_success_releases_batch_once(monkeypatch):
    provider = _run_one_session(monkeypatch, lambda: {"success": True}, "PASS")
    assert provider.finished == [(False, "batch")]
    assert provider.hits == ["monetag:article.riztama.my.id"]


def test_worker_chain_failure_classifies_and_finishes_once(monkeypatch):
    def boom():
        raise MonetagProxyError("ERR_PROXY_CONNECTION_FAILED")

    provider = _run_one_session(monkeypatch, boom, "FAIL")
    assert provider.finished == [(False, "proxy")]


def test_worker_runs_post_session_with_same_proxy(monkeypatch):
    stop_event = threading.Event()
    provider = FakeChainProvider(_chain_proxy())
    budget = FakeBudget()
    seen = {}

    def fake_session(**kwargs):
        seen["session_proxy"] = kwargs["proxy_data"]
        stop_event.set()
        return {"success": True}

    def fake_post(worker_id, proxy, _config):
        seen["post_worker"] = worker_id
        seen["post_proxy"] = proxy

    monkeypatch.setattr(flow, "run_monetag_session", fake_session)

    monetag_worker_thread_loop(
        worker_id=7,
        config={"max_uses_per_day": 2, "proxy_cooldown_hours": 6.0},
        proxy_manager=NoDirectProxyCalls(),
        budget=budget,
        stop_event=stop_event,
        chain_provider=provider,
        post_session=fake_post,
    )

    assert seen["post_worker"] == 7
    assert seen["post_proxy"] is seen["session_proxy"]
    assert provider.finished == [(False, "batch")]


def _run_batch(monkeypatch, provider, budget, session_func=None):
    stop_event = threading.Event()
    seen = []

    def fake_session(**kwargs):
        seen.append((kwargs["proxy_data"]["id"], kwargs["config"]["target_url"]))
        if session_func is not None:
            session_func()
        if budget.max_sessions and len(seen) >= budget.max_sessions:
            stop_event.set()

    monkeypatch.setattr(flow, "run_monetag_session", fake_session)
    monkeypatch.setattr(flow.time, "sleep", lambda *_: None)

    monetag_worker_thread_loop(
        worker_id=1,
        config={
            "max_uses_per_day": 2,
            "proxy_cooldown_hours": 6.0,
            "target_urls": ["https://a.example.com", "https://b.example.com"],
            "site_urls": ["https://a.example.com", "https://b.example.com"],
        },
        proxy_manager=NoDirectProxyCalls(),
        budget=budget,
        stop_event=stop_event,
        chain_provider=provider,
    )
    return seen


def test_worker_batch_uses_same_proxy_for_all_urls_then_rotates(monkeypatch):
    provider = FakeChainProvider([_chain_proxy(1), _chain_proxy(2)])
    budget = FakeBudget(max_sessions=4)

    seen = _run_batch(monkeypatch, provider, budget)

    assert seen == [
        ("chain#1", "https://a.example.com"),
        ("chain#1", "https://b.example.com"),
        ("chain#2", "https://a.example.com"),
        ("chain#2", "https://b.example.com"),
    ]
    assert provider.hits == [
        "monetag:a.example.com",
        "monetag:b.example.com",
        "monetag:a.example.com",
        "monetag:b.example.com",
    ]
    assert provider.finished == [(False, "batch"), (False, "batch")]


def test_worker_batch_skips_url_in_cooldown(monkeypatch):
    now = flow.time.time()
    proxy = _chain_proxy(
        1,
        target_usage={"monetag:a.example.com": {"count": 1, "last_used": now}},
    )
    provider = FakeChainProvider(proxy)
    budget = FakeBudget(max_sessions=1)

    seen = _run_batch(monkeypatch, provider, budget)

    assert seen == [("chain#1", "https://b.example.com")]
    assert provider.hits == ["monetag:b.example.com"]


def test_worker_batch_aborts_on_failure_and_rotates_ip(monkeypatch):
    provider = FakeChainProvider(_chain_proxy(1))
    budget = FakeBudget(max_sessions=1)

    def boom():
        raise MonetagProxyError("ERR_PROXY_CONNECTION_FAILED")

    seen = _run_batch(monkeypatch, provider, budget, session_func=boom)

    assert seen == [("chain#1", "https://a.example.com")]
    assert provider.hits == []
    assert provider.finished == [(False, "proxy")]


def test_classify_session_error():
    assert _classify_session_error(MonetagVerificationError("ip mismatch")) == "verification"
    assert _classify_session_error(MonetagProxyError("tunnel")) == "proxy"
    assert _classify_session_error(MonetagNoAdError("tidak ada impresi")) == "no_ad"
    assert _classify_session_error(RuntimeError("Target closed")) == "shutdown"
    assert _classify_session_error(RuntimeError("Cloudflare Turnstile")) == "cloudflare"
    assert _classify_session_error(RuntimeError("random")) == "other"