#!/usr/bin/env python3
"""
automation.exoclick.runner
Runner multi-threaded untuk ExoClick Automation dengan rotasi proxy otomatis.
Fokus: Pemicu impresi Popunder, In-Page Push, Native Widget, & Display Banner.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from typing import Any, Dict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from core.proxy_manager import ProxyManager
from automation.exoclick.flow import run_exoclick_session

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class ExoClickRunner:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pm = ProxyManager(reset_stale_usage=True)
        self.running = threading.Event()
        self.running.set()
        self.stats_lock = threading.Lock()
        self.total_completed = 0
        self.total_popunders = 0
        self.total_failed = 0

    def stop(self) -> None:
        self.running.clear()
        print("\n[ExoClick Runner] Memberhentikan worker secara aman...")

    def _worker_loop(self, worker_id: int, max_sessions: int) -> None:
        sessions_done = 0

        while self.running.is_set() and (max_sessions <= 0 or sessions_done < max_sessions):
            proxy_data = None
            caller_id = f"exoclick_runner_w{worker_id}_{int(time.time() * 1000)}"
            try:
                max_u = int(self.config.get("max_uses_per_day", 2))
                cd_h = float(self.config.get("proxy_cooldown_hours", 6.0))
                proxy_data = self.pm.acquire_proxy(
                    caller_id=caller_id,
                    exclusive=True,
                    verify_alive=False,
                    target="exoclick",
                    max_uses_per_day=max_u,
                    cooldown_seconds=cd_h * 3600,
                )
            except Exception as e:
                print(f"[W{worker_id}] Gagal mengambil proxy: {e}")

            if not proxy_data:
                time.sleep(3.0)
                continue

            proxy_id = (proxy_data or {}).get("id") or ""
            try:
                result = run_exoclick_session(
                    worker_id=worker_id,
                    proxy_data=proxy_data,
                    config=self.config,
                )

                with self.stats_lock:
                    self.total_completed += 1
                    self.total_popunders += result.get("popunders_processed", 0)

                sessions_done += 1
                if proxy_id:
                    self.pm.record_target_hit(proxy_data, target="exoclick")

            except Exception as err:
                print(f"[W{worker_id}] ❌ Error saat sesi ExoClick: {err}")
                with self.stats_lock:
                    self.total_failed += 1
                if proxy_id:
                    self.pm.report_failure(proxy_id, error_message=str(err))

            finally:
                if proxy_id:
                    self.pm.release_proxy(proxy_id, caller_id=caller_id)

            if self.running.is_set():
                time.sleep(3.5)

    def run(self) -> None:
        concurrency = int(self.config.get("concurrency", 3))
        max_sessions = int(self.config.get("max_sessions_per_run", 20))

        print("=" * 65)
        print("  🚀 EXOCLICK AD AUTOMATION RUNNER (4 FORMATS)")
        print("=" * 65)
        print(f" Target Web        : {self.config.get('target_url')}")
        print(f" Concurrency       : {concurrency} Workers")
        print(f" Target Sesi       : {max_sessions} Sesi")
        print(f" Humanize Mouse    : {'Aktif (Bézier + Micro-jitter)' if self.config.get('humanize') else 'Nonaktif'}")
        print(f" Dwell Popunder    : {self.config.get('dwell_popup_seconds')}")
        print("=" * 65)

        threads: list[threading.Thread] = []
        sessions_per_worker = max(1, max_sessions // concurrency)

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

        print("\n" + "=" * 65)
        print("  📊 HASIL AKHIR AUTOMATION EXOCLICK")
        print("=" * 65)
        print(f" Total Sesi Selesai : {self.total_completed}")
        print(f" Popunder Dwelled   : {self.total_popunders}")
        print(f" Sesi Gagal         : {self.total_failed}")
        print("=" * 65)


def main() -> None:
    parser = argparse.ArgumentParser(description="ExoClick Ad Runner")
    parser.add_argument("--workers", type=int, default=None, help="Jumlah concurrent workers")
    parser.add_argument("--sessions", type=int, default=None, help="Maksimal total sesi")
    parser.add_argument("--headful", action="store_true", help="Buka browser dengan GUI")
    args = parser.parse_args()

    cfg = load_config()
    if args.workers:
        cfg["concurrency"] = args.workers
    if args.sessions:
        cfg["max_sessions_per_run"] = args.sessions
    if args.headful:
        cfg["headless"] = False

    runner = ExoClickRunner(cfg)

    def sigint_handler(signum, frame):
        runner.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)
    runner.run()


if __name__ == "__main__":
    main()
