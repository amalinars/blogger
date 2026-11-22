import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from automation import gologin_grabber as gg


class TestGoLoginDirectHops(unittest.TestCase):
    def test_load_direct_hops_prefers_supabase(self):
        fake_hops = [
            {
                "id": "hop#1",
                "idx": 1,
                "host": "1.2.3.4",
                "port": 3129,
                "username": "u",
                "password": "p",
                "proxy_scheme": "http",
                "country": "ID",
                "source": "supabase",
            }
        ]
        with patch.object(gg, "list_hops", return_value=fake_hops) as mock_list:
            items, source = gg.load_direct_hops(proxy_file="/nonexistent", prefer_supabase=True)

        mock_list.assert_called_once()
        self.assertEqual(source, "supabase")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "hop_supabase")
        self.assertEqual(items[0]["ip_detected"], "1.2.3.4")
        self.assertTrue(items[0]["allow_ip_rotation"])

    def test_load_direct_hops_falls_back_to_file_on_supabase_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hops.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("u:p@5.6.7.8:8080\n")

            with patch.object(gg, "list_hops", side_effect=RuntimeError("db down")):
                items, source = gg.load_direct_hops(proxy_file=path, prefer_supabase=True)

        self.assertEqual(source, f"file:{path}")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["host"], "5.6.7.8")
        self.assertEqual(items[0]["source"], "file")

    def test_load_direct_hops_skips_supabase_for_explicit_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "custom.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("socks5://u:p@9.9.9.9:1080\n")

            with patch.object(gg, "list_hops") as mock_list:
                items, source = gg.load_direct_hops(proxy_file=path, prefer_supabase=False)

        mock_list.assert_not_called()
        self.assertEqual(source, f"file:{path}")
        self.assertEqual(items[0]["proxy_scheme"], "socks5")

    def test_harvest_job_no_chain_uses_supabase_hops_not_residential_pool(self):
        fake_hops = [
            {
                "id": "hop#2",
                "host": "10.20.30.40",
                "port": 3129,
                "username": "u",
                "password": "p",
                "proxy_scheme": "http",
                "country": "",
                "source": "supabase",
            }
        ]
        seen_proxies = []
        stop_event = threading.Event()

        def fake_grab(headless=False, proxy_item=None, rounds=2, skip_verifier=False):
            seen_proxies.append(proxy_item)
            stop_event.set()
            return [{"proxy_url": "http://x:y@1.1.1.1:80"}]

        with patch.object(gg, "list_hops", return_value=fake_hops), \
             patch.object(gg, "grab_gologin_proxies", side_effect=fake_grab), \
             patch.object(gg, "acquire_proxy") as mock_acquire, \
             patch.object(gg.time, "sleep"):
            total = gg.run_gologin_harvest_job(
                target_proxies=1,
                concurrency=1,
                rounds=1,
                headless=True,
                proxy_file="/nonexistent",
                stop_event=stop_event,
                use_supabase_hops=True,
            )

        self.assertEqual(total, 1)
        mock_acquire.assert_not_called()
        self.assertEqual(seen_proxies[0]["host"], "10.20.30.40")
        self.assertEqual(seen_proxies[0]["source"], "hop_supabase")

    def test_harvest_job_no_chain_stops_when_no_hops_available(self):
        with patch.object(gg, "list_hops", return_value=[]), \
             patch.object(gg, "acquire_proxy") as mock_acquire:
            total = gg.run_gologin_harvest_job(
                target_proxies=1,
                concurrency=1,
                proxy_file="/nonexistent",
                use_supabase_hops=True,
            )

        self.assertEqual(total, 0)
        mock_acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
