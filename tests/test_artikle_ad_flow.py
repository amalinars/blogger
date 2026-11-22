import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.artikle_ad import flow
from automation.chain_provider import ChainProxyProvider
from automation.session import SessionBudget
from proxy_chain_tester import ChainError


class _FakeChainProvider:
    def __init__(self, responses):
        self._responses = list(responses)
        self.last_miss_reason = ""
        self.finished = []
        self.calls = 0

    def next_proxy(self, caller_id=None, log_prefix="", target=None, lease_seconds=600):
        self.calls += 1
        proxy, reason = self._responses.pop(0) if self._responses else (None, "pool_empty")
        self.last_miss_reason = reason
        return proxy

    def finish_session(self, proxy, success, error=None, error_kind="other", log_prefix=""):
        self.finished.append((success, error_kind, log_prefix))


class _FakeProxyManager:
    supabase_enabled = True


class ArtikleAdFlowTest(unittest.TestCase):
    def test_pool_empty_logs_and_updates_stepper_without_resetting_supabase(self):
        stop_event = threading.Event()
        events = []
        reset_called = []

        def on_event(etype, data):
            events.append((etype, data))
            if etype == "log_message":
                stop_event.set()

        provider = _FakeChainProvider([(None, "pool_empty")])
        flow.article_ad_worker_thread_loop(
            worker_id=1,
            config={
                "target_url": "https://ghasima.ai.studio/",
                "max_sessions_per_run": 0,
                "max_uses_per_day": 2,
                "proxy_cooldown_hours": 6.0,
                "direct_ip": False,
            },
            proxy_manager=_FakeProxyManager(),
            budget=SessionBudget(0, 1),
            event_callback=on_event,
            stop_event=stop_event,
            chain_provider=provider,
            reset_pool_callback=lambda: reset_called.append(True),
        )

        self.assertEqual(reset_called, [])
        self.assertTrue(any(t == "stepper_update" and d.get("stage") == "⏳ Menunggu IP" for t, d in events))
        self.assertTrue(any(t == "log_message" and "cooldown" in d.get("message", "").lower() for t, d in events))

    def test_chain_success_finishes_with_success_true(self):
        stop_event = threading.Event()
        proxy = {"id": "chain#1", "host": "127.0.0.1", "port": 41001, "expected_ip": "1.2.3.4", "country": "US"}
        provider = _FakeChainProvider([(proxy, "")])

        def fake_session(**_kwargs):
            stop_event.set()
            return {"success": True}

        with mock.patch.object(flow, "run_article_ad_session", side_effect=fake_session):
            flow.article_ad_worker_thread_loop(
                worker_id=2,
                config={"target_url": "https://ghasima.ai.studio/", "max_sessions_per_run": 1, "direct_ip": False},
                proxy_manager=_FakeProxyManager(),
                budget=SessionBudget(1, 1),
                stop_event=stop_event,
                chain_provider=provider,
            )

        self.assertEqual(provider.finished, [(True, "other", "[W2] ")])

    def test_shutdown_exception_marks_error_kind_shutdown(self):
        stop_event = threading.Event()
        proxy = {"id": "chain#2", "host": "127.0.0.1", "port": 41002, "expected_ip": "1.2.3.5", "country": "US"}
        provider = _FakeChainProvider([(proxy, "")])

        def boom(**_kwargs):
            stop_event.set()
            raise RuntimeError("Target page, context or browser has been closed")

        with mock.patch.object(flow, "run_article_ad_session", side_effect=boom):
            flow.article_ad_worker_thread_loop(
                worker_id=3,
                config={"target_url": "https://ghasima.ai.studio/", "max_sessions_per_run": 0, "direct_ip": False},
                proxy_manager=_FakeProxyManager(),
                budget=SessionBudget(0, 1),
                stop_event=stop_event,
                chain_provider=provider,
            )

        self.assertEqual(provider.finished, [(False, "shutdown", "[W3] ")])

    def test_chain_provider_sets_last_miss_reason_pool_empty(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as fh:
            fh.write("u:p@10.0.0.1:3129\n")
            hop_path = fh.name
        try:
            class EmptyPM:
                def acquire_proxy(self, **kwargs):
                    return None

            with mock.patch("automation.chain_provider.list_hops_from_supabase", return_value=[]):
                provider = ChainProxyProvider(scrape_file=hop_path, proxy_manager=EmptyPM(), log_func=lambda *_: None)
            self.assertIsNone(provider.next_proxy(target="artikle_ad:ghasima.ai.studio"))
            self.assertEqual(provider.last_miss_reason, "pool_empty")
        finally:
            os.unlink(hop_path)

    def test_chain_provider_sets_last_miss_reason_and_logs_probe_cooldown(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as fh:
            fh.write("u:p@10.0.0.1:3129\n")
            hop_path = fh.name
        try:
            logs = []

            class OnePM:
                def acquire_proxy(self, **kwargs):
                    return {"id": 99, "supabase_id": 99, "host": "geo.floppydata.com", "port": 10080, "leased_by": "l1"}

                def report_failure(self, *args, **kwargs):
                    pass

                def release_proxy(self, *args, **kwargs):
                    return True

            with mock.patch("automation.chain_provider.list_hops_from_supabase", return_value=[]):
                provider = ChainProxyProvider(
                    scrape_file=hop_path,
                    hop_tries=1,
                    channel="automation",
                    strict_channel=False,
                    proxy_manager=OnePM(),
                    log_func=logs.append,
                )
            with mock.patch.object(provider, "_probe", side_effect=ChainError("HTTP 503", stage="target", status=503)):
                self.assertIsNone(provider.next_proxy(log_prefix="[W1] "))
            self.assertEqual(provider.last_miss_reason, "cooldown")
            self.assertTrue(any("cooldown probe" in line for line in logs))
        finally:
            os.unlink(hop_path)


if __name__ == "__main__":
    unittest.main()
