#!/usr/bin/env python3
"""CLI Runner mandiri untuk flow dinamis `automation/artikle_ad`.

Contoh pemakaian testing lokal (Direct IP, layar terlihat):
  python3 automation/artikle_ad/runner.py --no-headless
  python3 automation/artikle_ad/runner.py --url https://ghasima.ai.studio --articles 2 --click-push --no-headless

Contoh pemakaian produksi dengan Proxy Chain:
  python3 automation/artikle_ad/runner.py --chain --workers 2 --sessions 0
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from automation.artikle_ad.flow import article_ad_worker_thread_loop

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner dinamis HilltopAds + Monetag Direct Link (artikle_ad).")
    parser.add_argument("--url", default=None, help="URL website artikel target")
    parser.add_argument("-w", "--workers", type=int, default=1, help="Jumlah worker paralel")
    parser.add_argument("--sessions", type=int, default=1, help="Jumlah sesi per worker (0 = tanpa batas)")
    parser.add_argument("--articles", type=int, default=None, help="Jumlah kartu artikel Direct Link yang diklik per sesi")
    parser.add_argument("--click-push", action="store_true", help="Selalu klik kartu In-Page Push (100%%) untuk testing")
    parser.add_argument("--headless", action="store_true", default=True, help="Jalankan tanpa GUI layar")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Tampilkan jendela Camoufox")
    parser.add_argument("--chain", action="store_true", help="Gunakan Proxy Chain (Hop 3xK -> FloppyData)")
    parser.add_argument("--proxy", action="store_true", help="Gunakan Proxy Supabase langsung (tanpa chain)")
    parser.add_argument("--name", default=None, help="Nama node server ini (opsional, default persisten per mesin)")
    parser.add_argument("--max-uses", type=int, default=2, help="Maksimal pemakaian per IP per hari (default: 2)")
    parser.add_argument("--cooldown", type=float, default=6.0, help="Cooldown antar pemakaian IP dalam jam (default: 6.0)")
    parser.add_argument("--hop-tries", type=int, default=3, help="Jumlah hop acak yang dicoba per sesi chain")
    parser.add_argument("--chain-timeout", type=float, default=15.0, help="Timeout probe chain dalam detik")
    parser.add_argument("--chain-verbose", action="store_true", help="Tampilkan log detail probe chain")
    args = parser.parse_args()

    cfg = load_config()
    if args.url:
        cfg["target_url"] = args.url
    if args.articles is not None:
        cfg["article_clicks_per_session"] = args.articles
    if args.click_push:
        cfg["push_click_chance"] = 1.0
    cfg["headless"] = args.headless
    cfg["max_sessions_per_run"] = args.sessions
    cfg["max_uses_per_day"] = args.max_uses
    cfg["proxy_cooldown_hours"] = args.cooldown
    cfg["direct_ip"] = not (args.chain or args.proxy)

    stop_event = threading.Event()
    proxy_manager = None
    chain_provider = None

    if args.chain or args.proxy:
        from core.proxy_manager import ProxyManager

        proxy_manager = ProxyManager(reset_stale_usage=True, node_id=args.name)
        if args.chain:
            from automation.chain_provider import ChainProxyProvider

            chain_provider = ChainProxyProvider(
                hop_tries=args.hop_tries,
                timeout=args.chain_timeout,
                verbose=args.chain_verbose,
                target="artikle_ad",
                channel="automation",
                strict_channel=False,
                target_max_uses_per_day=args.max_uses,
                target_cooldown_seconds=args.cooldown * 3600,
                target_window_seconds=24 * 3600,
                residential_host_contains="floppydata",
                proxy_manager=proxy_manager,
            )

    cleaned_up = False

    def _cleanup(*_):
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        except Exception:
            pass
        stop_event.set()
        if proxy_manager is not None:
            proxy_manager._shutting_down = True
            c1 = proxy_manager.reset_usage_to_idle(shutting_down=True)
            time.sleep(0.35)
            c2 = proxy_manager.reset_usage_to_idle(shutting_down=True)
            print(f"\n✅ Status proxy node ({proxy_manager.node_id}) dikembalikan ke IDLE (Total: {max(c1, c2)}).", flush=True)

    def _on_sig(*_):
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sig)
    signal.signal(signal.SIGTERM, _on_sig)

    mode_str = "PROXY CHAIN" if args.chain else ("PROXY DIRECT" if args.proxy else "DIRECT IP (TESTING)")
    print("=" * 65, flush=True)
    print(f"  🚀 ARTIKLE_AD DYNAMIC RUNNER ({mode_str})", flush=True)
    print(f"  Target URL     : {cfg.get('target_url')}", flush=True)
    print(f"  Workers        : {args.workers} | Sesi/Worker: {args.sessions or 'Unlimited'}", flush=True)
    print(f"  Artikel/Sesi   : {cfg.get('article_clicks_per_session')} | Push Click: {int(float(cfg.get('push_click_chance', 0.4)) * 100)}%", flush=True)
    print(f"  Headless       : {'Aktif' if args.headless else 'Non-Headless (Layar Terlihat)'}", flush=True)
    print("=" * 65, flush=True)

    threads = []
    for wid in range(1, args.workers + 1):
        t = threading.Thread(
            target=article_ad_worker_thread_loop,
            args=(wid, cfg, proxy_manager, None, None, stop_event, chain_provider),
            daemon=True,
        )
        t.start()
        threads.append(t)
        if wid < args.workers:
            time.sleep(0.3)

    try:
        for t in threads:
            while t.is_alive():
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        _on_sig()
    finally:
        _cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
