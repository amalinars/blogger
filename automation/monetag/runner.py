#!/usr/bin/env python3
"""Runner mandiri untuk `automation/monetag` (mendukung Direct IP testing & Proxy Chain)."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from automation.monetag.flow import close_worker_browser, monetag_worker_thread_loop, run_monetag_session
from automation.session import SessionBudget

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


class MonetagRunner:
    """Wrapper runner kompatibel untuk import lama (`automation.monetag.MonetagRunner`)."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def run(self) -> None:
        run_monetag_session(worker_id=1, proxy_data=None, config=self.config)


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner Monetag v2 (Dinamis + CTR-aware).")
    parser.add_argument("--url", default=None, help="URL target Monetag")
    parser.add_argument("-w", "--workers", type=int, default=1, help="Jumlah worker paralel")
    parser.add_argument("--sessions", type=int, default=1, help="Jumlah sesi (0 = tanpa batas)")
    parser.add_argument("--headless", action="store_true", default=True, help="Tanpa layar GUI")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Tampilkan browser Camoufox")
    parser.add_argument("--direct", action="store_true", help="Testing lokal 1 sesi Direct IP tanpa proxy")
    parser.add_argument("--chain", action="store_true", help="Gunakan Proxy Chain (Hop 3xK -> FloppyData)")
    parser.add_argument("--name", default=None, help="Nama node server")
    args = parser.parse_args()

    cfg = load_config()
    if args.url:
        cfg["target_url"] = args.url
    cfg["headless"] = args.headless
    cfg["allow_direct_ip"] = bool(args.direct or not args.chain)

    def _printer(etype: str, data: Dict[str, Any]) -> None:
        if etype == "log_message" and data.get("message"):
            print(data["message"], flush=True)

    if cfg["allow_direct_ip"] and not args.chain:
        try:
            run_monetag_session(worker_id=1, proxy_data=None, config=cfg, event_callback=_printer)
        finally:
            close_worker_browser(1)
        return 0

    from core.proxy_manager import ProxyManager
    from automation.chain_provider import ChainProxyProvider

    pm = ProxyManager(reset_stale_usage=True, node_id=args.name)
    chain = ChainProxyProvider(
        target="monetag",
        channel="automation",
        strict_channel=False,
        residential_host_contains="floppydata",
        proxy_manager=pm,
    )
    stop_event = threading.Event()
    budget = SessionBudget(args.sessions, 1)

    def _on_sig(*_):
        stop_event.set()
        pm.reset_usage_to_idle(shutting_down=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sig)
    signal.signal(signal.SIGTERM, _on_sig)

    threads = []
    for wid in range(1, args.workers + 1):
        t = threading.Thread(
            target=monetag_worker_thread_loop,
            args=(wid, cfg, pm, budget, _printer, stop_event),
            kwargs={"chain_provider": chain},
            daemon=True,
        )
        t.start()
        threads.append(t)
        if wid < args.workers:
            time.sleep(0.2)

    try:
        for t in threads:
            while t.is_alive():
                t.join(timeout=0.5)
    finally:
        pm.reset_usage_to_idle(shutting_down=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
