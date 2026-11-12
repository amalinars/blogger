#!/usr/bin/env python3
"""Seed tabel `proxxies.hop_proxy_list` dari file hop lokal.

Contoh:
    python seed_hops_to_supabase.py
    python seed_hops_to_supabase.py --file data/proxies_scrape.txt --dry-run

File hop boleh berisi kredensial asli (`user:pass@host:port`) atau placeholder
(`<user>:<pass>@host:port`). Placeholder diisi dari `.env`:
    X3K_USER=...
    X3K_PASS=...
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from automation.chain_provider import DEFAULT_SCRAPE_FILE, parse_hop_file
from core.hop_registry import DEFAULT_CONFIG_FILE, HopRegistry

DEFAULT_ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

_USER_PLACEHOLDERS = {"<user>", "<username>", "${x3k_user}", "$x3k_user"}
_PASS_PLACEHOLDERS = {"<pass>", "<password>", "${x3k_pass}", "$x3k_pass"}


def load_dotenv(path: str) -> None:
    """Muat KEY=VALUE sederhana dari .env tanpa menimpa env yang sudah ada."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export ") :].strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except OSError as exc:
        print(f"! Gagal membaca {path}: {exc}")


def resolve_credentials(hops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    default_user = os.environ.get("X3K_USER", "").strip()
    default_pass = os.environ.get("X3K_PASS", "").strip()
    resolved: List[Dict[str, Any]] = []
    for hop in hops:
        username = str(hop.get("username") or "").strip()
        password = str(hop.get("password") or "").strip()
        if username.lower() in _USER_PLACEHOLDERS or not username:
            username = default_user
        if password.lower() in _PASS_PLACEHOLDERS or not password:
            password = default_pass
        if not username or not password:
            print(f"! Lewati {hop.get('host')}:{hop.get('port')} (kredensial kosong)")
            continue
        resolved.append(
            {
                "host": hop["host"],
                "port": int(hop["port"]),
                "proxy_scheme": hop.get("proxy_scheme") or "http",
                "username": username,
                "password": password,
                "country": "",
                "enabled": True,
            }
        )
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=DEFAULT_SCRAPE_FILE, help="File hop lokal")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="Config Supabase")
    parser.add_argument("--env", default=DEFAULT_ENV_FILE, help="File .env")
    parser.add_argument("--dry-run", action="store_true", help="Hanya tampilkan jumlah")
    args = parser.parse_args()

    load_dotenv(args.env)

    hops = parse_hop_file(args.file)
    if not hops:
        print(f"! Tidak ada hop valid di {args.file}")
        return 1

    payload = resolve_credentials(hops)
    if not payload:
        print("! Semua hop terlewat: kredensial kosong (set X3K_USER/X3K_PASS)")
        return 1

    print(f"   {len(payload)} hop siap di-upsert dari {args.file}")
    if args.dry_run:
        return 0

    registry = HopRegistry(config_path=args.config)
    if not registry.enabled:
        print(f"! Config Supabase tidak lengkap: {args.config}")
        return 1

    if not registry.upsert_hops(payload):
        print("! Upsert gagal (cek RPC upsert_hop_proxies / koneksi)")
        return 1

    print("   Upsert selesai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())