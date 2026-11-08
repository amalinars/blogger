#!/usr/bin/env python3
"""
check_proxies.py
Multi-threaded Proxy Health Checker & Auto-Cleaner CLI.

Fitur:
  - Cek kesehatan proxy secara paralel (HTTP ping ke api.ipify.org)
  - Otomatis menghapus proxy DEAD dari file lokal (data/proxies.json)
  - Mendukung pengecekan dan penghapusan langsung di database Supabase (--supabase)
  - Menampilkan latency dan real IP yang terdeteksi

Contoh Penggunaan:
  # Cek proxies lokal dan tampilkan yang hidup/mati:
  python3 check_proxies.py

  # Cek proxies lokal dan LANGSUNG HAPUS yang mati:
  python3 check_proxies.py --delete-dead

  # Cek dan hapus yang mati langsung di database SUPABASE:
  python3 check_proxies.py --supabase --delete-dead

  # Cek dengan 50 thread dan timeout 5 detik:
  python3 check_proxies.py --threads 50 --timeout 5 --delete-dead
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

PROJECT_ROOT = Path(__file__).resolve().parent
PROXY_FILE = PROJECT_ROOT / "data" / "proxies.json"
CONFIG_FILE = PROJECT_ROOT / "data" / "supabase_config.json"
CHECK_ENDPOINTS = [
    ("http://api.ipify.org?format=json", "json", "ip"),
    ("https://icanhazip.com", "text", None),
    ("http://ip-api.com/json", "json", "query"),
]

def get_proxy_url(p: Dict[str, Any]) -> str:
    url = p.get("proxy_url")
    if url:
        return url
    host = p.get("host")
    port = p.get("port")
    u = p.get("username")
    pwd = p.get("password")
    if u and pwd:
        return f"http://{u}:{pwd}@{host}:{port}"
    return f"http://{host}:{port}"


def test_proxy(proxy_item: Dict[str, Any], index: int, timeout: int = 12, retries: int = 2) -> Dict[str, Any]:
    proxy_url = get_proxy_url(proxy_item)
    country = proxy_item.get("country", "Unknown")
    proxies = {"http": proxy_url, "https": proxy_url}

    last_err = None
    for attempt in range(max(1, retries)):
        ep_url, ep_type, ep_key = CHECK_ENDPOINTS[attempt % len(CHECK_ENDPOINTS)]
        start_time = time.time()
        try:
            resp = requests.get(ep_url, proxies=proxies, timeout=timeout)
            latency = round((time.time() - start_time) * 1000, 2)
            if resp.status_code == 200:
                if ep_type == "json":
                    ip_detected = resp.json().get(ep_key, "N/A")
                else:
                    ip_detected = resp.text.strip()
                return {
                    "index": index,
                    "status": "ALIVE",
                    "country": country,
                    "ip": ip_detected,
                    "latency_ms": latency,
                    "proxy_item": proxy_item,
                }
            elif resp.status_code == 407:
                last_err = "Auth Failed (407)"
                break
            else:
                last_err = f"HTTP {resp.status_code}"
        except requests.exceptions.ProxyError as pe:
            last_err = f"ProxyError: {pe}"
        except requests.exceptions.Timeout:
            last_err = f"Timeout ({timeout}s)"
        except Exception as e:
            last_err = str(type(e).__name__)

        if attempt < retries - 1:
            time.sleep(0.3)

    return {
        "index": index,
        "status": "DEAD",
        "country": country,
        "ip": None,
        "latency_ms": None,
        "last_error": last_err or "Connection failed",
        "proxy_item": proxy_item,
    }

def load_supabase_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "supabase_url": "https://supabase.riztama.my.id",
        "supabase_key": "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
        "schema": "proxxies",
        "table": "proxy_list",
    }


def fetch_all_supabase_proxies() -> List[Dict[str, Any]]:
    cfg = load_supabase_config()
    url = cfg["supabase_url"].rstrip("/")
    key = cfg["supabase_key"]
    schema = cfg.get("schema", "proxxies")
    table = cfg.get("table", "proxy_list")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": schema,
    }

    all_items = []
    page_size = 1000
    offset = 0

    while True:
        p_headers = {**headers, "Range": f"{offset}-{offset + page_size - 1}"}
        resp = requests.get(f"{url}/rest/v1/{table}?select=*&order=id.asc", headers=p_headers, timeout=15)
        if resp.status_code not in (200, 206):
            break
        chunk = resp.json()
        if not chunk:
            break
        all_items.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size

    return all_items


def delete_supabase_proxies(ids: List[int]) -> int:
    if not ids:
        return 0
    cfg = load_supabase_config()
    url = cfg["supabase_url"].rstrip("/")
    key = cfg["supabase_key"]
    schema = cfg.get("schema", "proxxies")
    table = cfg.get("table", "proxy_list")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }

    deleted_total = 0
    chunk_size = 100
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        id_filter = ",".join(str(x) for x in chunk)
        endpoint = f"{url}/rest/v1/{table}?id=in.({id_filter})"
        try:
            resp = requests.delete(endpoint, headers=headers, timeout=20)
            if resp.status_code in (200, 204):
                deleted_total += len(chunk)
        except Exception as e:
            print(f"⚠️ Gagal menghapus batch Supabase: {e}")

    return deleted_total


def main():
    parser = argparse.ArgumentParser(
        description="Multi-threaded Proxy Health Checker & Auto-Cleaner CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--delete-dead",
        "--clean",
        action="store_true",
        dest="delete_dead",
        help="Hapus proxy yang berstatus DEAD langsung dari daftar",
    )
    parser.add_argument(
        "--supabase",
        action="store_true",
        help="Targetkan pengecekan & penghapusan langsung ke database Supabase (schema proxxies)",
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=20,
        help="Jumlah thread paralel pengecekan (default: 20 agar gateway residential stabil)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=12,
        help="Batas waktu timeout HTTP per proxy dalam detik (default: 12)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Jumlah percobaan fallback endpoint sebelum menyatakan proxy DEAD (default: 2)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Paksa hapus meskipun rasio DEAD > 35% (safety guard bypass)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Batasi jumlah proxy yang diuji (0 = uji semua)",
    )
    args = parser.parse_args()

    # 1. Muat daftar proxy
    is_supabase = args.supabase
    if is_supabase:
        print("☁️ Mengambil seluruh proxy dari database Supabase (schema: proxxies)...")
        proxy_list = fetch_all_supabase_proxies()
        cursor = 0
        is_dict_format = False
    else:
        if not PROXY_FILE.exists():
            print(f"❌ File {PROXY_FILE} tidak ditemukan!")
            sys.exit(1)
        print(f"🔍 Membaca proxy dari file lokal {PROXY_FILE}...")
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        if isinstance(raw_data, dict) and "proxies" in raw_data:
            proxy_list = raw_data["proxies"]
            cursor = raw_data.get("cursor", 0)
            is_dict_format = True
        else:
            proxy_list = raw_data
            cursor = 0
            is_dict_format = False

    if args.limit and args.limit > 0:
        proxy_list = proxy_list[: args.limit]

    total = len(proxy_list)
    if total == 0:
        print("⚠️ Tidak ada proxy yang ditemukan untuk diuji.")
        sys.exit(0)

    print(
        f"📊 Ditemukan {total} proxy ({'Supabase Database' if is_supabase else 'File Lokal'}). "
        f"Menjalankan checker paralel ({args.threads} threads, timeout: {args.timeout}s)..."
    )

    alive_proxies = []
    dead_proxies = []

    start_check = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(test_proxy, p, idx, args.timeout, args.retries): p
            for idx, p in enumerate(proxy_list, 1)
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            p_item = res["proxy_item"]
            idx = res["index"]
            c = res["country"]
            if res["status"] == "ALIVE":
                alive_proxies.append(res)
                p_item["health"] = "ALIVE"
                p_item["ip_detected"] = res["ip"]
                p_item["latency_ms"] = res["latency_ms"]
                p_item["last_checked"] = time.time()
                p_item["fail_count"] = 0
                p_item["last_error"] = None
                print(f"  ✅ [ALIVE] #{idx:4d} ({c:14s}) -> IP: {res['ip']:15s} | Latency: {res['latency_ms']} ms")
            else:
                dead_proxies.append(res)
                p_item["health"] = "DEAD"
                p_item["last_checked"] = time.time()
                p_item["last_error"] = res.get("last_error") or "Connection failed"
                host_port = f"{p_item.get('host')}:{p_item.get('port')}"
                print(f"  ❌ [DEAD]  #{idx:4d} ({c:14s}) -> {host_port} [{p_item['last_error']}]")

    elapsed = round(time.time() - start_check, 2)
    print("\n" + "=" * 65)
    print(f"📈 HASIL PENGECEKAN PROXY ({'Supabase' if is_supabase else 'Lokal'}):")
    print(f"   - Total Diuji   : {total}")
    print(f"   - Aktif (ALIVE) : {len(alive_proxies)} ✅")
    print(f"   - Mati (DEAD)   : {len(dead_proxies)} ❌")
    print(f"   - Total Durasi  : {elapsed} detik")
    print("=" * 65)

    alive_data = [item["proxy_item"] for item in alive_proxies]

    if args.delete_dead:
        if len(dead_proxies) > len(proxy_list) * 0.35 and not args.force:
            print("\n" + "!" * 65)
            print("🛡️ PERINGATAN SAFETY GUARD: PENGHAPUSAN DIBATALKAN OTOMATIS!")
            print(f"   Terdeteksi {len(dead_proxies)} dari {len(proxy_list)} proxy ({len(dead_proxies)*100//len(proxy_list)}%) dianggap DEAD.")
            print("   Untuk proxy residential, kegagalan masal (>35%) hampir selalu disebabkan oleh:")
            print("   1. Gateway Floppydata overload/throttling karena thread terlalu banyak.")
            print("   2. Timeout jaringan terlalu cepat untuk residential handshake.")
            print("   Demi melindungi kuota dan proxy Anda dari salah hapus, operasi dibatalkan.")
            print("   Jika Anda benar-benar yakin ingin menghapus semuanya, tambahkan flag: --force")
            print("!" * 65)
            sys.exit(0)

        if is_supabase:
            dead_ids = [
                item["proxy_item"]["id"]
                for item in dead_proxies
                if item["proxy_item"].get("id")
            ]
            print(f"🗑️ Menghapus {len(dead_ids)} proxy DEAD dari database Supabase...")
            deleted_sb = delete_supabase_proxies(dead_ids)
            print(f"✅ Berhasil menghapus {deleted_sb} proxy DEAD dari Supabase!")

            # Sinkronkan file lokal
            if PROXY_FILE.exists():
                try:
                    with open(PROXY_FILE, "r", encoding="utf-8") as f:
                        loc_raw = json.load(f)
                    if isinstance(loc_raw, dict) and "proxies" in loc_raw:
                        loc_list = loc_raw["proxies"]
                        dead_id_set = set(dead_ids)
                        dead_keys = {
                            (d["proxy_item"].get("host"), int(d["proxy_item"].get("port")), d["proxy_item"].get("username", ""))
                            for d in dead_proxies
                            if d.get("proxy_item") and d["proxy_item"].get("host") and d["proxy_item"].get("port")
                        }
                        loc_alive = []
                        for p in loc_list:
                            if p.get("id") in dead_id_set:
                                continue
                            try:
                                p_port = int(p.get("port")) if p.get("port") else None
                            except (ValueError, TypeError):
                                p_port = None
                            if (p.get("host"), p_port, p.get("username", "")) in dead_keys:
                                continue
                            loc_alive.append(p)
                        loc_raw["proxies"] = loc_alive
                        loc_raw["cursor"] = loc_raw.get("cursor", 0) % max(1, len(loc_alive))
                        with open(PROXY_FILE, "w", encoding="utf-8") as f:
                            json.dump(loc_raw, f, indent=2)
                        print(f"💾 File lokal {PROXY_FILE} ikut dibersihkan (Sisa: {len(loc_alive)} proxy).")
                except Exception:
                    pass
        else:
            print(f"🗑️ Menghapus {len(dead_proxies)} proxy DEAD dari {PROXY_FILE}...")
            if is_dict_format:
                new_cursor = cursor % len(alive_data) if alive_data else 0
                final_data = {"cursor": new_cursor, "proxies": alive_data}
            else:
                final_data = alive_data
            with open(PROXY_FILE, "w", encoding="utf-8") as f:
                json.dump(final_data, f, indent=2)
            print(f"✅ File {PROXY_FILE} berhasil dibersihkan! Sisa {len(alive_data)} proxy aktif.")
    else:
        # Simpan backup proxy yang masih hidup ke proxies_alive.json
        out_alive = PROJECT_ROOT / "data" / "proxies_alive.json"
        with open(out_alive, "w", encoding="utf-8") as f:
            json.dump(alive_data, f, indent=2)
        print(f"💾 Proxy ALIVE disimpan ke: {out_alive}")
        print("\n💡 Tip: Gunakan argumen '--delete-dead' untuk langsung menghapus yang mati:")
        if is_supabase:
            print("   python3 check_proxies.py --supabase --delete-dead")
        else:
            print("   python3 check_proxies.py --delete-dead")


if __name__ == "__main__":
    main()
