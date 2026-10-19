#!/usr/bin/env python3
"""
test_proxies.py - Diagnostic & Connection Tester for Residential Proxies
Mengecek konektivitas, latensi (ping), dan validitas autentikasi setiap proksi.
"""

import sys
import os
import json
import time
import socket
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("[-] Module 'requests' belum terinstall. Menginstall via pip...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROXIES_JSON = BASE_DIR / "proxies.json"
DEFAULT_TARGET = "https://blog.riztama.my.id"


def test_socket_ping(host: str, port: int, timeout: float = 4.0) -> tuple[bool, float, str]:
    """Cek koneksi dasar TCP Socket ke server proksi."""
    start = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        elapsed = (time.time() - start) * 1000
        if result == 0:
            return True, elapsed, "OK"
        return False, elapsed, f"Port tertutup / reset (code {result})"
    except socket.gaierror:
        return False, 0.0, "DNS lookup gagal (Host tidak ditemukan)"
    except socket.timeout:
        return False, (time.time() - start) * 1000, "Connection Timed Out"
    except Exception as e:
        return False, (time.time() - start) * 1000, str(e)


def test_proxy_http(proxy_info: dict, target_url: str = DEFAULT_TARGET, timeout: float = 8.0) -> dict:
    """Melakukan pengujian HTTP/HTTPS tunneling lengkap melalui proksi."""
    host = proxy_info.get("host", "").strip()
    port = proxy_info.get("port", 10080)
    user = proxy_info.get("username", "").strip()
    pwd = proxy_info.get("password", "").strip()
    country = proxy_info.get("country", "Unknown")

    proxy_url = proxy_info.get("proxy_url")
    if not proxy_url:
        if user and pwd:
            proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = f"http://{host}:{port}"

    result = {
        "host": host,
        "port": port,
        "country": country,
        "proxy_url": proxy_url,
        "socket_ok": False,
        "http_ok": False,
        "latency_ms": 0.0,
        "status_code": None,
        "exit_ip": None,
        "error": None
    }

    # 1. Cek Socket TCP Ping terlebih dahulu
    sock_ok, sock_latency, sock_err = test_socket_ping(host, port, timeout=min(4.0, timeout))
    result["socket_ok"] = sock_ok
    if not sock_ok:
        result["error"] = f"TCP Connect Failed: {sock_err}"
        result["latency_ms"] = sock_latency
        return result

    # 2. Cek Request HTTP Nyata melalui Proksi
    proxies_dict = {
        "http": proxy_url,
        "https": proxy_url
    }

    start = time.time()
    try:
        # Gunakan API deteksi IP eksternal atau target blog
        test_url = target_url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ChronicleTrafficBot/1.0"
        }

        resp = requests.get(
            test_url,
            proxies=proxies_dict,
            timeout=timeout,
            headers=headers,
            allow_redirects=True
        )

        elapsed = (time.time() - start) * 1000
        result["latency_ms"] = round(elapsed, 1)
        result["status_code"] = resp.status_code

        if resp.status_code in [200, 301, 302, 304]:
            result["http_ok"] = True
        else:
            result["error"] = f"HTTP Error Status {resp.status_code}"

    except requests.exceptions.ProxyError as e:
        result["error"] = "Proxy Auth / Tunnel Failed (Username/Password salah atau server menolak koneksi)"
        result["latency_ms"] = round((time.time() - start) * 1000, 1)
    except requests.exceptions.ConnectTimeout:
        result["error"] = f"Connection Timed Out (> {timeout}s)"
        result["latency_ms"] = round(timeout * 1000, 1)
    except requests.exceptions.ReadTimeout:
        result["error"] = "Read Timed Out (Server proksi merespons terlalu lambat)"
        result["latency_ms"] = round(timeout * 1000, 1)
    except requests.exceptions.SSLError as e:
        result["error"] = f"SSL Handshake Error via Proxy: {e}"
    except Exception as e:
        err_s = str(e).splitlines()[0] if str(e) else "Unknown"
        result["error"] = err_s[:80]
        result["latency_ms"] = round((time.time() - start) * 1000, 1)

    return result


def main():
    parser = argparse.ArgumentParser(description="Chronicle Proxy Connection Tester & Diagnostic")
    parser.add_argument("--file", "-f", default=str(DEFAULT_PROXIES_JSON), help="Path ke file proxies.json")
    parser.add_argument("--proxy", "-p", default=None, help="Tes satu URL/string proksi saja (misal: http://user:pass@host:port)")
    parser.add_argument("--target", "-t", default=DEFAULT_TARGET, help="Target URL yang ingin diuji (default: https://blog.riztama.my.id)")
    parser.add_argument("--timeout", type=float, default=6.0, help="Batas timeout per proksi dalam detik (default: 6.0s)")
    parser.add_argument("--threads", type=int, default=15, help="Jumlah thread pengujian paralel (default: 15)")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Batasi jumlah proksi yang diuji (contoh: 10 untuk tes cepat)")
    parser.add_argument("--save-alive", "-s", default=None, help="Simpan hanya proksi yang aktif ke file JSON (contoh: automation/proxies_alive.json)")
    parser.add_argument("--clean-dead", "--auto-clean", action="store_true", help="Otomatis hapus proksi mati langsung dari file aslinya (dengan backup otomatis)")
    args = parser.parse_args()

    print("=" * 70)
    print("      CHRONICLE RESIDENTIAL PROXY CONNECTION TESTER")
    print("=" * 70)
    print(f"[*] Target Uji       : {args.target}")
    print(f"[*] Timeout per Host : {args.timeout} detik")
    print(f"[*] Parallel Threads : {args.threads}")

    proxies_to_test = []

    if args.proxy:
        raw = args.proxy.strip()
        # Parse single proxy
        if "@" in raw:
            creds, rest = raw.split("@", 1)
            clean_creds = creds.replace("http://", "").replace("https://", "")
            u_p = clean_creds.split(":", 1)
            u = u_p[0]
            p = u_p[1] if len(u_p) > 1 else ""
            r_parts = rest.split(":")
            h = r_parts[0]
            port = int(r_parts[1]) if len(r_parts) > 1 and r_parts[1].isdigit() else 10080
            c = r_parts[2] if len(r_parts) > 2 else "Custom"
        else:
            parts = raw.split(":")
            h = parts[0]
            port = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10080
            u = parts[2] if len(parts) > 2 else ""
            p = parts[3] if len(parts) > 3 else ""
            c = parts[4] if len(parts) > 4 else "Custom"

        proxies_to_test.append({
            "host": h,
            "port": port,
            "username": u,
            "password": p,
            "country": c,
            "proxy_url": f"http://{u}:{p}@{h}:{port}" if u else f"http://h:{port}"
        })
    else:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"[-] File {file_path} tidak ditemukan!")
            sys.exit(1)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                proxies_to_test = json.load(f)
        except Exception as e:
            print(f"[-] Gagal membaca file JSON: {e}")
            sys.exit(1)

    if args.limit and args.limit > 0:
        proxies_to_test = proxies_to_test[:args.limit]

    total = len(proxies_to_test)
    print(f"[*] Total Proksi Diuji: {total}")
    print("=" * 70)
    print(f"{'#':<4} {'Negara':<16} {'Host:Port':<28} {'Status':<10} {'Latensi':<10} {'Keterangan'}")
    print("-" * 70)

    alive_proxies = []
    dead_count = 0
    total_latency_alive = 0.0

    start_all = time.time()

    with ThreadPoolExecutor(max_workers=min(args.threads, max(1, total))) as executor:
        futures = {
            executor.submit(test_proxy_http, px, args.target, args.timeout): (idx + 1, px)
            for idx, px in enumerate(proxies_to_test)
        }

        for fut in as_completed(futures):
            idx, orig_px = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {
                    "host": orig_px.get("host", ""),
                    "port": orig_px.get("port", ""),
                    "country": orig_px.get("country", "Unknown"),
                    "http_ok": False,
                    "latency_ms": 0,
                    "error": str(e)
                }

            host_port = f"{res['host']}:{res['port']}"
            country = res["country"][:15]

            if res["http_ok"]:
                alive_proxies.append(orig_px)
                total_latency_alive += res["latency_ms"]
                status_str = "✅ HIDUP"
                latency_str = f"{res['latency_ms']:.0f}ms"
                detail = f"HTTP {res['status_code']} OK"
                color_code = "\033[92m" # Green
            else:
                dead_count += 1
                status_str = "❌ MATI"
                latency_str = f"{res['latency_ms']:.0f}ms" if res['latency_ms'] > 0 else "-"
                detail = res["error"] or "Gagal terhubung"
                color_code = "\033[91m" # Red

            reset_code = "\033[0m"
            print(f"{color_code}{idx:<4} {country:<16} {host_port:<28} {status_str:<10} {latency_str:<10} {detail[:30]}{reset_code}")

    elapsed_total = time.time() - start_all
    alive_count = len(alive_proxies)
    avg_latency = (total_latency_alive / alive_count) if alive_count > 0 else 0

    print("=" * 70)
    print("                      RINGKASAN HASIL PENGUJIAN")
    print("=" * 70)
    print(f"Total Diuji         : {total} Proksi (Selesai dalam {elapsed_total:.1f} detik)")
    print(f"✅ Proksi Hidup     : \033[92m{alive_count}\033[0m ({alive_count/total*100:.1f}%)" if total else "0")
    print(f"❌ Proksi Mati/Down : \033[91m{dead_count}\033[0m ({dead_count/total*100:.1f}%)" if total else "0")
    if alive_count > 0:
        print(f"⚡ Rata-rata Latensi: {avg_latency:.1f} ms")
    print("=" * 70)

    # Otomatis bersihkan proksi mati dari file sumber jika --clean-dead aktif
    if args.clean_dead and not args.proxy:
        src_path = Path(args.file)
        if src_path.exists():
            backup_path = src_path.parent / "proxies_backup.json"
            if not backup_path.exists():
                try:
                    import shutil
                    shutil.copy2(src_path, backup_path)
                    print(f"[*] [BACKUP] Salinan cadangan proksi tersimpan di: {backup_path.name}")
                except Exception:
                    pass
            try:
                with open(src_path, "w", encoding="utf-8") as f:
                    json.dump(alive_proxies, f, indent=2)
                print(f"[✓] 🧹 [AUTO-CLEAN] Berhasil membuang {dead_count} proksi mati dari {src_path.name}! (Sisa aktif: {len(alive_proxies)} proksi).")
            except Exception as e:
                print(f"[-] Gagal memperbarui file proksi: {e}")

    # Simpan proksi aktif jika diminta
    if args.save_alive and alive_proxies:
        out_path = Path(args.save_alive)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(alive_proxies, f, indent=2)
            print(f"[+] Berhasil menyimpan {len(alive_proxies)} proksi aktif ke: {out_path.name}")
        except Exception as e:
            print(f"[-] Gagal menyimpan proksi: {e}")

    elif alive_count == 0:
        print("\n[!] PERINGATAN: Semua proksi yang diuji tidak dapat terhubung.")
        print("    Penyebab umum: Server proksi down/expired atau IP host diblokir firewall.")
        print("    Solusi: Gunakan proksi baru yang aktif atau hilangkan centang 'Gunakan Proksi' di GUI.")


if __name__ == "__main__":
    main()
