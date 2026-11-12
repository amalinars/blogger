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
    unlimited = True

    def __init__(self):
        self.results = []

    def is_exhausted(self):
        return False

    def has_capacity(self):
        return True

    def reserve(self):
        return True

    def record(self, status):
        self.results.append(status)

    def mark_proxy(self, proxy_id):
        pass


class FakeChainProvider:
    def __init__(self, proxy):
        self.proxy = proxy
        self.pm = self
        self.next_calls = 0
        self.finished = []

    def next_proxy(self, caller_id=None, log_prefix=""):
        self.next_calls += 1
        return self.proxy if self.next_calls == 1 else None

    def get_target_usage_summary(self, *args, **kwargs):
        return {}

    def finish_session(self, proxy, success, error=None, error_kind="other", log_prefix=""):
        self.finished.append((success, error_kind))


class NoDirectProxyCalls:
    supabase_enabled = True

    def __getattr__(self, name):
        raise AssertionError(f"direct proxy_manager.{name} tidak boleh dipanggil di mode chain")


def _chain_proxy():
    return {
        "id": "chain#1",
        "supabase_id": 1,
        "host": "127.0.0.1",
        "port": 41000,
        "expected_ip": "203.0.113.7",
        "country": "United States",
        "source": "chain",
        "_residential": {"id": 1, "supabase_id": 1, "host": "r", "port": 1},
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
        config={"max_uses_per_day": 2, "proxy_cooldown_hours": 6.0},
        proxy_manager=NoDirectProxyCalls(),
        budget=budget,
        stop_event=stop_event,
        chain_provider=provider,
    )

    assert provider.next_calls == 1
    assert budget.results == [expected_status]
    return provider


def test_worker_chain_success_finishes_once(monkeypatch):
    provider = _run_one_session(monkeypatch, lambda: {"success": True}, "PASS")
    assert provider.finished == [(True, "other")]


def test_worker_chain_failure_classifies_and_finishes_once(monkeypatch):
    def boom():
        raise MonetagProxyError("ERR_PROXY_CONNECTION_FAILED")

    provider = _run_one_session(monkeypatch, boom, "FAIL")
    assert provider.finished == [(False, "proxy")]


def test_classify_session_error():
    assert _classify_session_error(MonetagVerificationError("ip mismatch")) == "verification"
    assert _classify_session_error(MonetagProxyError("tunnel")) == "proxy"
    assert _classify_session_error(MonetagNoAdError("tidak ada impresi")) == "no_ad"
    assert _classify_session_error(RuntimeError("Target closed")) == "shutdown"
    assert _classify_session_error(RuntimeError("Cloudflare Turnstile")) == "cloudflare"
    assert _classify_session_error(RuntimeError("random")) == "other"