#!/usr/bin/env python3
"""
automation.smartlink.runner
Runner multi-threaded untuk Smartlink Automation.
Proxy: ChainProxyProvider (hop 3xK -> residential) bila `use_chain` aktif,
atau ProxyManager langsung. Rotasi IP tiap sesi, logging terminal berwarna.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from core.proxy_manager import ProxyManager
from automation.smartlink.flow import (
    BOLD,
    CYAN,
    GREEN,
    RED,
    RESET,
    YELLOW,
    classify_session_error,
    run_smartlink_session,
)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class SmartlinkRunner:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pm = ProxyManager(reset_stale_usage=True)
        self.chain: Optional[Any] = None
        self.running = threading.Event()
        self.running.set()
        self.stats_lock = threading.Lock()
        self.total_completed = 0
        self.total_failed = 0

    def stop(self) -> None:
        self.running.clear()
        print(f"\n{YELLOW}[Smartlink Runner] Memberhentikan worker secara aman...{RESET}", flush=True)

    def _setup_chain(self) -> None:
        if not bool(self.config.get("use_chain", True)):
            print(f"{YELLOW}⚠️ Chain dimatikan (use_chain=false); memakai residential langsung.{RESET}", flush=True)
            return
        try:
            from automation.chain_provider import ChainProxyProvider

            self.chain = ChainProxyProvider(
                hop_tries=int(self.config.get("chain_hop_tries", 3)),
                timeout=float(self.config.get("chain_timeout", 15.0)),
                dead_confirm_hops=int(self.config.get("chain_dead_confirm_hops", 2)),
                verbose=bool(self.config.get("chain_verbose", False)),
                hop_blacklist_seconds=float(self.config.get("chain_hop_blacklist_seconds", 300.0)),
                target=str(self.config.get("target_name", "smartlink")),
                channel="automation",
                strict_channel=False,
                target_max_uses_per_day=int(self.config.get("max_uses_per_day", 2)),
                target_cooldown_seconds=float(self.config.get("proxy_cooldown_hours", 6.0)) * 3600,
                residential_host_contains="floppydata",
                log_func=print,
            )
            print(
                f"{GREEN}🔗 Chain mode aktif: hop 3xK -> residential "
                f"(target={self.config.get('target_name', 'smartlink')}, {len(self.chain.hops)} hop).{RESET}",
                flush=True,
            )
        except Exception as exc:
            print(f"{RED}❌ Chain tidak bisa dimulai: {exc}{RESET}", flush=True)
            print(f"{YELLOW}   Fallback ke residential langsung.{RESET}", flush=True)
            self.chain = None

    def _acquire_proxy(self, worker_id: int) -> Tuple[str, Optional[Dict[str, Any]]]:
        caller_id = f"smartlink_w{worker_id}_{int(time.time() * 1000)}"
        try:
            if self.chain is not None:
                proxy = self.chain.next_proxy(caller_id=caller_id, log_prefix=f"[W{worker_id}] ")
            else:
                proxy = self.pm.acquire_proxy(
                    caller_id=caller_id,
                    exclusive=True,
                    verify_alive=False,
                    target=str(self.config.get("target_name", "smartlink")),
                    max_uses_per_day=int(self.config.get("max_uses_per_day", 2)),
                    cooldown_seconds=float(self.config.get("proxy_cooldown_hours", 6.0)) * 3600,
                )
        except Exception as e:
            print(f"{RED}[W{worker_id}] Gagal mengambil proxy: {e}{RESET}", flush=True)
            proxy = None
        return caller_id, proxy

    def _worker_loop(self, worker_id: int, max_sessions: int) -> None:
        sessions_done = 0

        while self.running.is_set() and (max_sessions <= 0 or sessions_done < max_sessions):
            caller_id, proxy = self._acquire_proxy(worker_id)

            if not proxy:
                time.sleep(3.0)
                continue

            proxy_id = proxy.get("id") or proxy.get("proxy_url") or ""
            try:
                run_smartlink_session(
                    worker_id=worker_id,
                    proxy_data=proxy,
                    config=self.config,
                )
                if self.chain is not None:
                    self.chain.finish_session(proxy, True, log_prefix=f"[W{worker_id}] ")
                else:
                    self.pm.record_target_hit(proxy, target=str(self.config.get("target_name", "smartlink")))
                with self.stats_lock:
                    self.total_completed += 1
                sessions_done += 1
            except Exception as err:
                print(f"{RED}[W{worker_id}] ❌ Error saat menjalankan sesi: {err}{RESET}", flush=True)
                with self.stats_lock:
                    self.total_failed += 1
                if self.chain is not None:
                    error_kind = classify_session_error(err, stopping=not self.running.is_set())
                    self.chain.finish_session(proxy, False, err, error_kind, log_prefix=f"[W{worker_id}] ")
                else:
                    self.pm.report_failure(proxy_id, error_message=str(err))
            finally:
                if self.chain is None and proxy_id:
                    self.pm.release_proxy(proxy_id, caller_id=caller_id)

            if self.running.is_set():
                time.sleep(4.0)

    def run(self) -> None:
        concurrency = int(self.config.get("concurrency", 3))
        max_sessions = int(self.config.get("max_sessions_per_run", 20))

        print("=" * 65, flush=True)
        print(f"{BOLD}  🚀 SMARTLINK VISIT AUTOMATION RUNNER{RESET}", flush=True)
        print("=" * 65, flush=True)
        print(f" Target Smartlink   : {self.config.get('target_url')}", flush=True)
        print(f" Mode Proxy         : {'Chain (hop 3xK)' if self.config.get('use_chain', True) else 'Residential langsung'}", flush=True)
        print(f" Concurrency        : {concurrency} Workers", flush=True)
        print(f" Target Sesi        : {'Unlimited (Ctrl+C untuk stop)' if max_sessions <= 0 else f'{max_sessions} Sesi'}", flush=True)
        print(f" Humanize Mouse     : {'Aktif (Bézier + Micro-jitter)' if self.config.get('humanize') else 'Nonaktif'}", flush=True)
        print("=" * 65, flush=True)

        self._setup_chain()

        threads: list[threading.Thread] = []
        sessions_per_worker = 0 if max_sessions <= 0 else max(1, max_sessions // concurrency)

        for i in range(1, concurrency + 1):
            t = threading.Thread(
                target=self._worker_loop,
                args=(i, sessions_per_worker),
                daemon=True,
            )
            threads.append(t)
            t.start()
            time.sleep(2.0)

        try:
            while any(t.is_alive() for t in threads) and self.running.is_set():
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.stop()

        for t in threads:
            t.join(timeout=3.0)

        print("\n" + "=" * 65, flush=True)
        print(f"{BOLD}  📊 HASIL AKHIR AUTOMATION SMARTLINK{RESET}", flush=True)
        print("=" * 65, flush=True)
        print(f" Total Sesi Selesai : {self.total_completed}", flush=True)
        print(f" Sesi Gagal         : {self.total_failed}", flush=True)
        print("=" * 65, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smartlink Visit Runner")
    parser.add_argument("--workers", type=int, default=None, help="Jumlah concurrent workers")
    parser.add_argument("--sessions", type=int, default=None, help="Maksimal total sesi")
    parser.add_argument("--headful", action="store_true", help="Buka browser dengan tampilan GUI")
    parser.add_argument("--no-chain", action="store_true", help="Nonaktifkan chain proxy (residential langsung)")
    args = parser.parse_args()

    cfg = load_config()
    if args.workers:
        cfg["concurrency"] = args.workers
    if args.sessions is not None:
        cfg["max_sessions_per_run"] = args.sessions
    if args.headful:
        cfg["headless"] = False
    if args.no_chain:
        cfg["use_chain"] = False

    runner = SmartlinkRunner(cfg)

    def sigint_handler(signum, frame):
        runner.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)
    runner.run()


if __name__ == "__main__":
    main()
