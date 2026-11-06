#!/usr/bin/env python3
"""
manage_supabase_proxies.py
Alat manajemen & sinkronisasi proxy ke database Supabase (Schema: proxxies).

Fitur:
  - Cek koneksi ke REST API Supabase & schema proxxies
  - Upload daftar proxy (dari text atau file) ke tabel proxxies.proxy_list
  - Tarik (pull) proxy dari Supabase ke file lokal data/proxies.json
  - Tampilkan daftar proxy yang ada di Supabase
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
import requests

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.proxy_manager import ProxyManager

CONFIG_FILE = PROJECT_ROOT / "data" / "supabase_config.json"


def load_supabase_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        alt = PROJECT_ROOT / "data" / "telemetry_config.json"
        if alt.exists():
            with open(alt, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "supabase_url": "https://supabase.riztama.my.id",
            "supabase_key": "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
            "schema": "proxxies",
            "table": "proxy_list",
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_connection() -> bool:
    cfg = load_supabase_config()
    url = cfg.get("supabase_url", "").rstrip("/")
    key = cfg.get("supabase_key", "")
    schema = cfg.get("schema", "proxxies")
    table = cfg.get("table", "proxy_list")

    print(f"📡 Menghubungi Supabase: {url}")
    print(f"📦 Schema target : {schema}")
    print(f"📋 Tabel target  : {table}")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }

    try:
        resp = requests.get(f"{url}/rest/v1/{table}?select=count", headers=headers, timeout=10)
        if resp.status_code == 200:
            print("✅ Koneksi BERHASIL! Schema dan tabel siap digunakan.")
            return True
        elif resp.status_code == 406:
            print(f"❌ Error 406 (Schema Not Exposed): {resp.text}")
            print(f"👉 Pastikan schema '{schema}' sudah di-expose di PostgREST Supabase Anda.")
            return False
        elif resp.status_code == 404:
            print(f"❌ Error 404 (Table Not Found): Tabel '{table}' belum dibuat di schema '{schema}'.")
            return False
        else:
            print(f"❌ Error HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Gagal koneksi: {e}")
        return False


def pull_proxies() -> None:
    pm = ProxyManager()
    count = pm.sync_from_supabase()
    stats = pm.get_stats()
    print(f"✅ Selesai menarik proxy dari Supabase.")
    print(f"📊 Total proxy di data/proxies.json: {stats.get('total', 0)} (Baru masuk: {count})")


def upload_lines(lines: List[str]) -> None:
    pm = ProxyManager()
    uploaded = pm.upload_to_supabase(lines)
    print(f"🚀 Berhasil mengupload {uploaded} proxy ke Supabase!")
    if uploaded > 0:
        # Sinkronkan juga ke lokal
        pm.sync_from_supabase()
        print("💾 data/proxies.json lokal ikut disinkronkan.")


def list_proxies() -> None:
    cfg = load_supabase_config()
    url = cfg.get("supabase_url", "").rstrip("/")
    key = cfg.get("supabase_key", "")
    schema = cfg.get("schema", "proxxies")
    table = cfg.get("table", "proxy_list")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": schema,
    }

    resp = requests.get(f"{url}/rest/v1/{table}?select=*", headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Gagal membaca: {resp.status_code} - {resp.text}")
        return

    items = resp.json()
    print(f"\n📋 Daftar Proxy di Supabase [{schema}.{table}] — Total: {len(items)}")
    print("-" * 75)
    for idx, p in enumerate(items, 1):
        u = p.get("username")
        pwd = p.get("password")
        auth = f" (User: {u})" if u else ""
        print(f" {idx:2d}. {p.get('host')}:{p.get('port')}{auth} | {p.get('country', 'US')} | Status: {p.get('health', 'ALIVE')}")
    print("-" * 75)

def reset_all_idle() -> None:
    pm = ProxyManager()
    cleaned = pm.reset_usage_to_idle()
    print(f"✅ Seluruh status proxy di Supabase & file lokal berhasil dikembalikan ke IDLE (Total: {cleaned} lokal).")


def main():
    parser = argparse.ArgumentParser(description="Manajemen Proxy Supabase (Schema: proxxies)")
    parser.add_argument("--test", action="store_true", help="Uji koneksi ke Supabase & schema proxxies")
    parser.add_argument("--pull", action="store_true", help="Tarik proxy dari Supabase ke data/proxies.json lokal")
    parser.add_argument("--list", action="store_true", help="Tampilkan seluruh proxy di Supabase")
    parser.add_argument("--reset-idle", action="store_true", help="Kembalikan seluruh status proxy (IN_USE) menjadi IDLE di Supabase")
    parser.add_argument("--upload-file", type=str, help="Upload file berisi daftar proxy (1 baris per proxy: host:port:user:pass)")
    parser.add_argument("--upload", type=str, help="Upload string proxy langsung (contoh: host:port:user:pass)")

    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.pull:
        pull_proxies()
    elif args.list:
        list_proxies()
    elif args.reset_idle:
        reset_all_idle()
    elif args.upload_file:
        if not os.path.exists(args.upload_file):
            print(f"❌ File tidak ditemukan: {args.upload_file}")
            sys.exit(1)
        with open(args.upload_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        upload_lines(lines)
    elif args.upload:
        upload_lines([args.upload])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
