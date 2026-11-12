#!/usr/bin/env python3
"""
proxy_chain_tester.py
Tester proxy dengan chaining bertahap.

Alur:
  1. Cek dulu IP publik lokal (tanpa proxy) sebagai pembanding.
  2. Proxy pertama dites langsung. Kalau hidup, jadi hop pertama rantai.
  3. Proxy berikutnya dites LEWAT rantai yang sudah terkonek (CONNECT berlapis).
     Kalau hidup, ditambahkan ke rantai; kalau gagal, dilewati (rantai tetap).
  4. Tiap proxy dicatat HIDUP/GAGAL beserta exit IP dan latensinya.

Health check = ambil IP keluar lewat proxy ke endpoint target.
Tidak menyentuh Supabase / database apa pun (statis).

Penggunaan:
  python3 proxy_chain_tester.py
  python3 proxy_chain_tester.py --verbose
  python3 proxy_chain_tester.py --file proxies.txt --max-hops 5
  python3 proxy_chain_tester.py --timeout 15 --target "http://checkip.amazonaws.com"
"""

import argparse
import base64
import json
import socket
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

DEFAULT_TARGET = "http://api.ipify.org?format=json"
DEFAULT_TIMEOUT = 15.0

# Daftar proxy default sengaja dikosongkan agar kredensial tidak ikut ter-commit.
# Isi lewat file dengan format `user:pass@host:port` (satu per baris):
#   python3 proxy_chain_tester.py --file proxies.txt
PROXIES: List[Dict[str, Any]] = []


class ChainError(Exception):
    def __init__(
        self,
        message: str,
        status: Optional[int] = None,
        raw: bytes = b"",
        stage: str = "unknown",
        proxy_index: Optional[int] = None,
    ):
        super().__init__(message)
        self.status = status
        self.raw = raw
        self.stage = stage
        self.proxy_index = proxy_index


def _parse_target(url: str) -> Tuple[str, int, str]:
    parts = urlsplit(url)
    if parts.scheme != "http":
        raise ValueError("Target harus http:// (bukan https) agar health check tidak butuh CONNECT tambahan.")
    host = parts.hostname or ""
    port = parts.port or 80
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return host, port, path


def _recv_until(sock: socket.socket, marker: bytes = b"\r\n\r\n", limit: int = 65536) -> bytes:
    buf = b""
    while marker not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) >= limit:
            break
    return buf


def _status_code(status_line: str) -> int:
    parts = status_line.split()
    for p in parts[1:]:
        if p.isdigit():
            return int(p)
    return 0


def _proxy_connect(sock: socket.socket, host: str, port: int, username: str, password: str) -> Tuple[int, bytes]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = (
        f"CONNECT {host}:{port} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Proxy-Authorization: Basic {token}\r\n"
        f"Proxy-Connection: Keep-Alive\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())
    raw = _recv_until(sock)
    status_line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
    code = _status_code(status_line)
    return code, raw


def _auth_header(proxy: Dict[str, Any]) -> str:
    token = base64.b64encode(
        f"{proxy['username']}:{proxy['password']}".encode()
    ).decode()
    return f"Basic {token}"


def _connect_next_proxy(
    sock: socket.socket,
    prev: Dict[str, Any],
    nxt: Dict[str, Any],
    verbose: bool = False,
) -> None:
    """CONNECT ke proxy berikutnya lewat tunnel yang sudah terbuka."""
    code, raw = _proxy_connect(
        sock,
        nxt["host"],
        int(nxt["port"]),
        prev["username"],
        prev["password"],
    )
    if verbose:
        status_line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        print(
            f"    [chain] CONNECT {nxt['host']}:{nxt['port']} "
            f"via #{prev.get('idx')} -> {status_line}"
        )
    if code != 200:
        body = raw.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in raw else b""
        raise ChainError(
            f"CONNECT ke proxy #{nxt.get('idx')} ditolak (HTTP {code})",
            status=code,
            raw=body,
            stage="proxy_connect",
            proxy_index=nxt.get("idx"),
        )


def open_chain_tunnel(
    chain: List[Dict[str, Any]],
    target_host: str,
    target_port: int,
    timeout: float = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> socket.socket:
    """
    Buka tunnel TCP penuh: hop pertama -> proxy berikutnya -> target.
    Dipakai oleh local proxy bridge untuk meneruskan koneksi browser.

    Caller bertanggung jawab menutup socket yang dikembalikan.
    """
    if not chain:
        raise ChainError("Rantai proxy kosong", stage="hop_tcp")

    sock: Optional[socket.socket] = None
    try:
        first = chain[0]
        try:
            sock = socket.create_connection(
                (first["host"], int(first["port"])), timeout=timeout
            )
        except socket.timeout:
            raise ChainError(
                f"Timeout konek ke hop {first['host']}:{first['port']}",
                stage="hop_tcp",
                proxy_index=first.get("idx"),
            )
        except OSError as exc:
            raise ChainError(
                f"Gagal konek ke hop {first['host']}:{first['port']}: {exc}",
                stage="hop_tcp",
                proxy_index=first.get("idx"),
            )

        sock.settimeout(timeout)
        if verbose:
            print(f"    [chain] TCP langsung -> {first['host']}:{first['port']}")

        for j in range(1, len(chain)):
            _connect_next_proxy(sock, chain[j - 1], chain[j], verbose)

        last = chain[-1]
        code, raw = _proxy_connect(
            sock,
            target_host,
            target_port,
            last["username"],
            last["password"],
        )
        if verbose:
            status_line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
            print(
                f"    [chain] CONNECT target {target_host}:{target_port} "
                f"via #{last.get('idx')} -> {status_line}"
            )
        if code != 200:
            body = raw.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in raw else b""
            raise ChainError(
                f"CONNECT ke target {target_host}:{target_port} ditolak (HTTP {code})",
                status=code,
                raw=body,
                stage="target",
                proxy_index=last.get("idx"),
            )

        return sock

    except Exception:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        raise


def fetch_through_chain(
    chain: List[Dict[str, Any]],
    target_url: str,
    timeout: float = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Buka rantai proxy lalu ambil target_url lewat proxy terakhir.
    chain[0] dihubungi langsung; chain[1..] dihubungi via CONNECT berlapis.
    """
    target_host, target_port, target_path = _parse_target(target_url)
    start = time.time()

    sock: Optional[socket.socket] = None
    try:
        first = chain[0]
        try:
            sock = socket.create_connection(
                (first["host"], int(first["port"])), timeout=timeout
            )
        except socket.timeout:
            raise ChainError(
                f"Timeout konek ke hop {first['host']}:{first['port']}",
                stage="hop_tcp",
                proxy_index=first.get("idx"),
            )
        except OSError as exc:
            raise ChainError(
                f"Gagal konek ke hop {first['host']}:{first['port']}: {exc}",
                stage="hop_tcp",
                proxy_index=first.get("idx"),
            )

        sock.settimeout(timeout)
        if verbose:
            print(f"    [chain] TCP langsung -> {first['host']}:{first['port']}")

        for j in range(1, len(chain)):
            _connect_next_proxy(sock, chain[j - 1], chain[j], verbose)

        last = chain[-1]
        authority = target_host if target_port == 80 else f"{target_host}:{target_port}"
        absolute_target = f"http://{authority}{target_path}"
        request = (
            f"GET {absolute_target} HTTP/1.1\r\n"
            f"Host: {authority}\r\n"
            f"Proxy-Authorization: {_auth_header(last)}\r\n"
            f"User-Agent: proxy-chain-tester/1.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode())

        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk

        if verbose:
            first_line = buf.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
            print(f"    [chain] GET via #{last.get('idx')} -> {first_line}")

        if b"\r\n\r\n" not in buf:
            raise ChainError(
                "Respons target tidak valid / kosong",
                stage="target",
                proxy_index=last.get("idx"),
            )

        head, body = buf.split(b"\r\n\r\n", 1)
        status_line = head.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        code = _status_code(status_line)

        if b"transfer-encoding: chunked" in head.lower():
            body = _dechunk(body)

        text = body.decode("utf-8", errors="replace").strip()
        latency = round((time.time() - start) * 1000, 2)

        if code != 200:
            raise ChainError(
                f"HTTP {code} dari target: {text[:200]}",
                status=code,
                raw=body,
                stage="target",
                proxy_index=last.get("idx"),
            )

        return {
            "ok": True,
            "status": code,
            "body": text,
            "latency_ms": latency,
            "exit_ip": _extract_ip(text),
        }

    except ChainError:
        raise
    except socket.timeout:
        raise ChainError(
            f"Timeout ({timeout}s)",
            stage="target",
            proxy_index=chain[-1].get("idx") if chain else None,
        )
    except Exception as exc:
        raise ChainError(f"{type(exc).__name__}: {exc}")
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def _dechunk(data: bytes) -> bytes:
    out = b""
    while data:
        line_end = data.find(b"\r\n")
        if line_end == -1:
            break
        size_line = data[:line_end].split(b";", 1)[0].strip()
        try:
            size = int(size_line, 16)
        except ValueError:
            break
        data = data[line_end + 2:]
        if size == 0:
            break
        out += data[:size]
        data = data[size + 2:]
    return out


def _extract_ip(body: str) -> Optional[str]:
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in ("ip", "query", "origin", "YourFuckingIPAddress"):
                if key in data and data[key]:
                    return str(data[key]).split(",")[0].strip()
    except (ValueError, TypeError):
        pass
    first = body.split()[0] if body.split() else ""
    candidate = first.strip().strip("{}").strip('"')
    if candidate and all(c.isdigit() or c == "." or c == ":" for c in candidate):
        return candidate
    return None


def get_local_public_ip(target_url: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """Ambil IP publik jaringan kita tanpa proxy, sebagai pembanding."""
    host, port, path = _parse_target(target_url)
    authority = host if port == 80 else f"{host}:{port}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        f"User-Agent: proxy-chain-tester/1.0\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(request.encode())
        buf = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
    if b"\r\n\r\n" not in buf:
        return None
    head, body = buf.split(b"\r\n\r\n", 1)
    if b"transfer-encoding: chunked" in head.lower():
        body = _dechunk(body)
    return _extract_ip(body.decode("utf-8", errors="replace").strip())


def describe(proxy: Dict[str, Any]) -> str:
    country = proxy.get("country") or ""
    tag = f" [{country}]" if country else ""
    return f"#{proxy['idx']}{tag} {proxy['username']}@{proxy['host']}:{proxy['port']}"


def load_proxies_file(path: str) -> List[Dict[str, Any]]:
    """Parse file berisi proxy format user:pass@host:port (satu per baris)."""
    proxies: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                cred, sep, hostport = line.rpartition("@")
                if sep:
                    username, _, password = cred.partition(":")
                else:
                    username, password = "", ""
                    hostport = line
                host, _, port_s = hostport.rpartition(":")
                if not host or not port_s.isdigit():
                    raise ValueError("format host:port tidak valid")
                proxies.append({
                    "idx": lineno,
                    "host": host.strip(),
                    "port": int(port_s),
                    "username": username.strip(),
                    "password": password.strip(),
                    "country": "",
                })
            except ValueError as exc:
                print(f"  ! Baris {lineno} gagal parse: {line[:60]} ({exc})")
    return proxies


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tester rantai proxy: cek proxy berikutnya lewat koneksi proxy sebelumnya.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default=DEFAULT_TARGET, help=f"URL target health check (default: {DEFAULT_TARGET})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"Timeout per operasi detik (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Tampilkan detail CONNECT antar proxy")
    parser.add_argument("--file", default=None, help="File daftar proxy format user:pass@host:port (satu per baris)")
    parser.add_argument("--max-hops", type=int, default=5, help="Panjang maksimal rantai; setelah penuh, proxy berikutnya dites langsung (default: 5)")
    args = parser.parse_args()

    proxies_list = load_proxies_file(args.file) if args.file else PROXIES
    if args.file:
        print(f"Memuat {len(proxies_list)} proxy dari {args.file}")

    print("=" * 70)
    print("PROXY TESTER (CHAINING BERTAHAP)")
    print(f"Target health : {args.target}")
    print(f"Timeout       : {args.timeout}s")
    print(f"Max hops      : {args.max_hops}")
    print(f"Total proxy   : {len(proxies_list)}")
    print("=" * 70)

    if not proxies_list:
        print("Tidak ada proxy untuk diuji.")
        return 1

    print("\nCek IP publik lokal (tanpa proxy)...")
    try:
        local_ip = get_local_public_ip(args.target, timeout=args.timeout)
        print(f"IP lokal sekarang: {local_ip or '(tidak terbaca)'}")
    except Exception as exc:
        local_ip = None
        print(f"IP lokal sekarang: GAGAL dicek ({type(exc).__name__}: {exc})")

    results: List[Dict[str, Any]] = []
    alive_count = 0
    chain: List[Dict[str, Any]] = []  # proxy yang sudah terkonek, berurutan

    for i, proxy in enumerate(proxies_list):
        label = describe(proxy)
        if len(chain) >= args.max_hops:
            candidate = [proxy]
            mode = "langsung (rantai penuh)"
        else:
            candidate = chain + [proxy]
            mode = "via rantai" if chain else "langsung"
        via = " -> ".join(f"#{p['idx']}" for p in candidate)
        print(f"\n[{i + 1}/{len(proxies_list)}] Cek {label} | {mode} | jalur: {via}")

        try:
            res = fetch_through_chain(candidate, args.target, timeout=args.timeout, verbose=args.verbose)
            alive_count += 1
            chain = candidate
            results.append({"proxy": proxy, "alive": True, **res})
            same = " (SAMA dengan IP lokal!)" if res.get("exit_ip") == local_ip else ""
            print(f"    HASIL: HIDUP | exit IP: {res.get('exit_ip')}{same} | {res['latency_ms']} ms")
        except ChainError as exc:
            results.append({"proxy": proxy, "alive": False, "error": str(exc), "status": exc.status})
            print(f"    HASIL: MATI/GAGAL | {exc}")
            if exc.raw:
                preview = exc.raw.decode("utf-8", errors="replace").strip().splitlines()[:3]
                for line in preview:
                    print(f"      > {line[:160]}")

    print("\n" + "=" * 70)
    print("RINGKASAN")
    print("=" * 70)
    print(f"  IP lokal (tanpa proxy): {local_ip or '(tidak terbaca)'}")
    print("-" * 70)
    for r in results:
        p = r["proxy"]
        if r["alive"]:
            print(f"  HIDUP  {describe(p):52s} exit={r.get('exit_ip')} {r['latency_ms']}ms")
        else:
            print(f"  GAGAL  {describe(p):52s} {r['error']}")
    print("-" * 70)
    final_chain = " -> ".join("#" + str(p["idx"]) for p in chain) or "(kosong)"
    print(f"Rantai akhir: {final_chain}")
    print(f"Total hidup: {alive_count}/{len(results)}")
    return 0 if alive_count else 2


if __name__ == "__main__":
    sys.exit(main())
