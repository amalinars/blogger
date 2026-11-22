#!/usr/bin/env python3
"""
check_proxies.py
Multi-threaded Proxy Health Checker & Auto-Cleaner CLI (Full Supabase).

Fitur:
  - Cek kesehatan seluruh proxy di tabel Supabase `proxxies.proxy_list` secara paralel
  - Mendukung pengecekan langsung maupun lewat jalur Chain (--chain: hop 3xK -> residential)
  - Memisahkan kegagalan hop (SKIPPED) dari proxy residential mati (DEAD) agar tidak salah hapus
  - Menghapus proxy DEAD langsung dari Supabase (--delete-dead) dengan verifikasi jumlah terhapus

Contoh Penggunaan:
  # Cek semua proxy di Supabase lewat Chain (tanpa hapus):
  python3 check_proxies.py --chain -t 10 --timeout 15

  # Cek lewat Chain dan LANGSUNG HAPUS yang benar-benar DEAD di Supabase:
  python3 check_proxies.py --chain --delete-dead -t 10 --timeout 15

  # Cek langsung (tanpa chain) dan hapus yang DEAD di Supabase:
  python3 check_proxies.py --delete-dead -t 15 --timeout 12
"""

import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.chain_provider import ChainProxyProvider, hop_is_blamed  # noqa: E402
from proxy_chain_tester import ChainError, fetch_through_chain  # noqa: E402

CONFIG_FILE = PROJECT_ROOT / "data" / "supabase_config.json"
SERVICE_CONFIG_FILE = PROJECT_ROOT / "data" / "supabase_service.json"
CHECK_ENDPOINTS = [
    ("http://api.ipify.org?format=json", "json", "ip"),
    ("https://icanhazip.com", "text", None),
    ("http://ip-api.com/json", "json", "query"),
]
CHAIN_CHECK_URLS = (
    "http://api.ipify.org?format=json",
    "http://ip-api.com/json",
)
FATAL_RESIDENTIAL_STATUS = {402, 407}

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


def test_proxy_via_chain(proxy_item: Dict[str, Any], index: int, provider: ChainProxyProvider, timeout: int = 12) -> Dict[str, Any]:
    """Uji 1 residential lewat jalur yang sama dengan bot: VPS -> hop acak -> residential.

    Kegagalan di lapisan hop (hop_tcp / hop ditolak) tidak menghukum proxy residential
    dan dikembalikan sebagai SKIPPED agar tidak pernah salah terhapus.
    """
    country = proxy_item.get("country", "Unknown")
    res_chain = provider._chain_item(proxy_item, proxy_item.get("id"))
    hops = provider._pick_hops(provider.hop_tries)
    if not hops:
        return {
            "index": index,
            "status": "SKIPPED",
            "country": country,
            "ip": None,
            "latency_ms": None,
            "last_error": "Tidak ada hop aktif tersedia",
            "proxy_item": proxy_item,
        }

    last_err = None
    res_failures = 0
    for hop_idx, hop in enumerate(hops):
        check_url = CHAIN_CHECK_URLS[hop_idx % len(CHAIN_CHECK_URLS)]
        try:
            result = fetch_through_chain([hop, res_chain], check_url, timeout=timeout)
            try:
                data = json.loads(result.get("body") or "{}")
            except (TypeError, ValueError):
                data = {}
            exit_ip = result.get("exit_ip") or data.get("query") or data.get("ip")
            if not exit_ip:
                res_failures += 1
                last_err = "Chain tersambung tapi IP exit tidak terbaca"
                continue
            return {
                "index": index,
                "status": "ALIVE",
                "country": country,
                "ip": str(exit_ip),
                "latency_ms": result.get("latency_ms"),
                "proxy_item": proxy_item,
            }
        except ChainError as exc:
            if exc.stage == "hop_tcp":
                # Timeout TCP hop bersifat sementara: blacklist di memori saja, jangan matikan permanen di DB
                provider._blacklist_hop(hop)
                last_err = f"hop {hop.get('host')} timeout TCP"
                continue
            if hop_is_blamed(exc):
                # Penolakan permanen terhadap jaringan/akun hop (403 free trial / auth hop gagal)
                provider._blacklist_hop(hop)
                provider.disable_hop(hop, str(exc)[:80])
                last_err = f"hop {hop.get('host')} ditolak: {str(exc)[:60]}"
                continue
            if exc.stage == "proxy_connect":
                provider._blacklist_hop(hop)
                last_err = f"hop {hop.get('host')} gagal CONNECT: {str(exc)[:60]}"
                continue
            # Kegagalan di tahap target (setelah tunnel hop -> residential tersambung)
            res_failures += 1
            last_err = f"residential via {hop.get('host')}: {str(exc)[:70]}"
            if exc.status in FATAL_RESIDENTIAL_STATUS:
                break
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:60]}"

    return {
        "index": index,
        "status": "DEAD" if res_failures > 0 else "SKIPPED",
        "country": country,
        "ip": None,
        "latency_ms": None,
        "last_error": last_err or "Semua hop gagal",
        "proxy_item": proxy_item,
    }


def load_supabase_config(for_write: bool = False) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "supabase_url": "https://supabase.riztama.my.id",
        "supabase_key": "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
        "schema": "proxxies",
        "table": "proxy_list",
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            base.update(json.load(f))
    if for_write and SERVICE_CONFIG_FILE.exists():
        try:
            with open(SERVICE_CONFIG_FILE, "r", encoding="utf-8") as f:
                svc = json.load(f)
            if svc.get("supabase_url"):
                base["supabase_url"] = svc["supabase_url"]
            if svc.get("supabase_key"):
                base["supabase_key"] = svc["supabase_key"]
        except Exception:
            pass
    return base


def fetch_all_supabase_proxies() -> List[Dict[str, Any]]:
    cfg = load_supabase_config(for_write=False)
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
            print(f"⚠️ Gagal membaca Supabase (HTTP {resp.status_code}): {resp.text[:160]}")
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
    cfg = load_supabase_config(for_write=True)
    url = cfg["supabase_url"].rstrip("/")
    key = cfg["supabase_key"]
    schema = cfg.get("schema", "proxxies")
    table = cfg.get("table", "proxy_list")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
        "Prefer": "return=representation",
    }

    deleted_total = 0
    chunk_size = 100
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        id_filter = ",".join(str(x) for x in chunk)
        endpoint = f"{url}/rest/v1/{table}?id=in.({id_filter})"
        try:
            resp = requests.delete(endpoint, headers=headers, timeout=20)
            if resp.status_code == 200:
                rows = resp.json()
                deleted_total += len(rows) if isinstance(rows, list) else len(chunk)
            elif resp.status_code == 204:
                deleted_total += len(chunk)
            else:
                print(f"⚠️ Gagal hapus batch Supabase (HTTP {resp.status_code}): {resp.text[:160]}")
        except Exception as e:
            print(f"⚠️ Gagal menghapus batch Supabase: {e}")

    return deleted_total


def main():
    parser = argparse.ArgumentParser(
        description="Multi-threaded Proxy Health Checker & Auto-Cleaner CLI (Full Supabase)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--delete-dead",
        "--clean",
        action="store_true",
        dest="delete_dead",
        help="Hapus proxy yang berstatus DEAD langsung dari Supabase",
    )
    parser.add_argument(
        "--supabase",
        action="store_true",
        default=True,
        help="Targetkan Supabase (default aktif penuh; opsi dipertahankan untuk kompatibilitas)",
    )
    parser.add_argument(
        "--chain",
        action="store_true",
        help="Uji proxy lewat chain hop 3xK -> residential (jalur yang sama dengan bot)",
    )
    parser.add_argument(
        "--hop-tries",
        type=int,
        default=3,
        help="Jumlah hop acak dicoba per proxy saat mode --chain (default: 3)",
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=15,
        help="Jumlah thread paralel pengecekan (default: 15 agar gateway residential & hop stabil)",
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
        help="Paksa hapus meskipun rasio DEAD > 35%% (safety guard bypass)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Batasi jumlah proxy yang diuji (0 = uji semua)",
    )
    args = parser.parse_args()

    # 1. Muat daftar proxy langsung dari Supabase (tanpa file data lokal)
    print("☁️ Mengambil seluruh proxy dari database Supabase (schema: proxxies)...")
    proxy_list = fetch_all_supabase_proxies()

    if args.limit and args.limit > 0:
        proxy_list = proxy_list[: args.limit]

    total = len(proxy_list)
    if total == 0:
        print("⚠️ Tidak ada proxy yang ditemukan di Supabase untuk diuji.")
        sys.exit(0)

    print(
        f"📊 Ditemukan {total} proxy di Supabase. "
        f"Mode: {'Chain hop->residential' if args.chain else 'Langsung'}. "
        f"Menjalankan checker paralel ({args.threads} threads, timeout: {args.timeout}s)..."
    )

    chain_provider: Optional[ChainProxyProvider] = None
    if args.chain:
        chain_provider = ChainProxyProvider(
            hop_tries=args.hop_tries,
            timeout=args.timeout,
            target="monetag",
            channel="automation",
            strict_channel=False,
            verbose=False,
        )

    alive_proxies = []
    dead_proxies = []
    skipped_proxies = []

    start_check = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {}
        for idx, p in enumerate(proxy_list, 1):
            if chain_provider is not None:
                futures[executor.submit(test_proxy_via_chain, p, idx, chain_provider, args.timeout)] = p
            else:
                futures[executor.submit(test_proxy, p, idx, args.timeout, args.retries)] = p
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            p_item = res["proxy_item"]
            idx = res["index"]
            c = res["country"]
            host_port = f"{p_item.get('host')}:{p_item.get('port')}"
            if res["status"] == "ALIVE":
                alive_proxies.append(res)
                print(f"  ✅ [ALIVE]   #{idx:4d} ({c:14s}) -> IP: {res['ip']:15s} | Latency: {res['latency_ms']} ms")
            elif res["status"] == "SKIPPED":
                skipped_proxies.append(res)
                print(f"  ⏭️ [SKIPPED] #{idx:4d} ({c:14s}) -> {host_port} [{res.get('last_error') or 'Hop gagal'}]")
            else:
                dead_proxies.append(res)
                err_txt = res.get("last_error") or "Connection failed"
                print(f"  ❌ [DEAD]    #{idx:4d} ({c:14s}) -> {host_port} [{err_txt}]")

    elapsed = round(time.time() - start_check, 2)
    tested_decisive = len(alive_proxies) + len(dead_proxies)
    print("\n" + "=" * 65)
    print("📈 HASIL PENGECEKAN PROXY (Supabase):")
    print(f"   - Total Diuji   : {total}")
    print(f"   - Aktif (ALIVE) : {len(alive_proxies)} ✅")
    print(f"   - Mati (DEAD)   : {len(dead_proxies)} ❌")
    if skipped_proxies:
        print(f"   - Dilewati      : {len(skipped_proxies)} ⏭️ (hop bermasalah, TIDAK dihapus)")
    print(f"   - Total Durasi  : {elapsed} detik")
    print("=" * 65)

    if args.delete_dead:
        if not dead_proxies:
            print("✅ Tidak ada proxy DEAD yang perlu dihapus dari Supabase.")
            return

        if tested_decisive > 0 and len(dead_proxies) > tested_decisive * 0.35 and not args.force:
            print("\n" + "!" * 65)
            print("🛡️ PERINGATAN SAFETY GUARD: PENGHAPUSAN DIBATALKAN OTOMATIS!")
            print(f"   Terdeteksi {len(dead_proxies)} dari {tested_decisive} proxy teruji ({len(dead_proxies)*100//tested_decisive}%) dianggap DEAD.")
            print("   Kegagalan massal (>35%) sering disebabkan oleh throttling gateway/timeout.")
            print("   Tambahkan flag --force jika Anda yakin ingin menghapus semuanya secara permanen.")
            print("!" * 65)
            sys.exit(0)

        dead_ids = [
            item["proxy_item"]["id"]
            for item in dead_proxies
            if item["proxy_item"].get("id") is not None
        ]
        print(f"🗑️ Menghapus {len(dead_ids)} proxy DEAD dari Supabase (proxxies.proxy_list)...")
        deleted_sb = delete_supabase_proxies(dead_ids)
        print(f"✅ Berhasil menghapus {deleted_sb}/{len(dead_ids)} proxy DEAD dari Supabase!")
    else:
        chain_hint = " --chain" if chain_provider is not None else ""
        print("\n💡 Mode cek saja (belum menghapus). Untuk langsung hapus yang DEAD dari Supabase:")
        print(f"   python3 check_proxies.py{chain_hint} --delete-dead")


if __name__ == "__main__":
    main()
