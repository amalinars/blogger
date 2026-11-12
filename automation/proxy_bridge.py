#!/usr/bin/env python3
"""Local HTTP CONNECT bridge untuk chain proxy berlapis.

Browser/GoLogin hanya melihat proxy lokal `127.0.0.1:<port>`. Bridge ini yang
membuka rantai sebenarnya:

    browser -> hop 3xK -> residential FloppyData -> target

Dengan begini Camoufox/Playwright tidak perlu tahu soal multi-hop, sementara
exit IP yang dilihat target tetap IP residential FloppyData.
"""

from __future__ import annotations

import socket
import socketserver
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from proxy_chain_tester import open_chain_tunnel

_HOP_BY_HOP_HEADERS = {
    "proxy-authorization",
    "proxy-connection",
    "connection",
    "keep-alive",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _split_host_port(authority: str, default_port: int = 80) -> Tuple[str, int]:
    authority = authority.strip()
    if authority.startswith("["):
        end = authority.find("]")
        if end == -1:
            raise ValueError(f"Authority IPv6 tidak valid: {authority}")
        host = authority[1:end]
        rest = authority[end + 1:]
        port = int(rest[1:]) if rest.startswith(":") and rest[1:] else default_port
        return host, port
    host, sep, port_s = authority.rpartition(":")
    if not sep or not port_s.isdigit():
        return authority, default_port
    return host, int(port_s)


def _read_headers(sock: socket.socket, limit: int = 128 * 1024) -> Tuple[bytes, bytes]:
    """Baca header sampai CRLFCRLF, kembalikan (header_blob, sisa_body)."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(8192)
        if not chunk:
            break
        buf += chunk
        if len(buf) >= limit:
            raise ValueError("Header request terlalu besar")
    if b"\r\n\r\n" not in buf:
        return buf, b""
    head, leftover = buf.split(b"\r\n\r\n", 1)
    return head + b"\r\n\r\n", leftover


def _relay(source: socket.socket, destination: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            destination.sendall(chunk)
    except (OSError, socket.timeout):
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _bridge_bidirectional(client: socket.socket, upstream: socket.socket) -> None:
    client.settimeout(None)
    upstream.settimeout(None)
    t = threading.Thread(target=_relay, args=(client, upstream), daemon=True)
    t.start()
    _relay(upstream, client)
    t.join(timeout=5.0)


class _ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        chain: "ChainProxyServer" = self.server.chain  # type: ignore[attr-defined]
        client: socket.socket = self.request
        client.settimeout(30.0)
        response_started = False

        try:
            header_blob, leftover = _read_headers(client)
            if not header_blob:
                return

            first_line, _, rest = header_blob.partition(b"\r\n")
            parts = first_line.decode("latin-1", errors="replace").split()
            if len(parts) < 2:
                self._send_error(client, 400, "Bad Request")
                return

            method, target = parts[0], parts[1]
            method_upper = method.upper()

            if method_upper == "CONNECT":
                host, port = _split_host_port(target, default_port=443)
                upstream = open_chain_tunnel(
                    chain.chain,
                    host,
                    port,
                    timeout=chain.timeout,
                    verbose=chain.verbose,
                )
                try:
                    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    response_started = True
                    if leftover:
                        upstream.sendall(leftover)
                    _bridge_bidirectional(client, upstream)
                finally:
                    try:
                        upstream.close()
                    except OSError:
                        pass
                return

            parsed = urlsplit(target)
            if parsed.scheme.lower() != "http" or not parsed.hostname:
                self._send_error(client, 400, "Only absolute http:// requests are supported")
                return

            host = parsed.hostname
            port = parsed.port or 80
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"

            header_lines = rest.split(b"\r\n")
            rebuilt = [f"{method} {path} HTTP/1.1".encode("latin-1")]
            has_host = False
            for raw_line in header_lines:
                if not raw_line:
                    continue
                name, sep, _ = raw_line.partition(b":")
                if not sep:
                    continue
                if name.strip().lower().decode("latin-1", errors="replace") in _HOP_BY_HOP_HEADERS:
                    continue
                if name.strip().lower() == b"host":
                    has_host = True
                rebuilt.append(raw_line)
            if not has_host:
                rebuilt.append(f"Host: {host}:{port}".encode("latin-1"))
            rebuilt.append(b"Connection: close")
            request_blob = b"\r\n".join(rebuilt) + b"\r\n\r\n"

            upstream = open_chain_tunnel(
                chain.chain,
                host,
                port,
                timeout=chain.timeout,
                verbose=chain.verbose,
            )
            try:
                upstream.sendall(request_blob)
                if leftover:
                    upstream.sendall(leftover)
                _bridge_bidirectional(client, upstream)
            finally:
                try:
                    upstream.close()
                except OSError:
                    pass

        except Exception as exc:  # bridge harus tetap hidup untuk request berikutnya
            if chain.verbose:
                print(f"[proxy-bridge] request gagal: {type(exc).__name__}: {exc}")
            if not response_started:
                self._send_error(client, 502, "Bad Gateway")

    @staticmethod
    def _send_error(client: socket.socket, status: int, message: str) -> None:
        body = f"{status} {message}\n".encode("utf-8", errors="replace")
        response = (
            f"HTTP/1.1 {status} {message}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("latin-1") + body
        try:
            client.sendall(response)
        except OSError:
            pass


class _ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ChainProxyServer:
    """Proxy lokal yang meneruskan koneksi lewat rantai hop + residential."""

    def __init__(
        self,
        chain: List[Dict[str, Any]],
        timeout: float = 15.0,
        verbose: bool = False,
    ):
        if not chain:
            raise ValueError("Chain proxy tidak boleh kosong")
        self.chain = chain
        self.timeout = timeout
        self.verbose = verbose
        self._server: Optional[_ThreadingServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: Optional[int] = None

    @property
    def proxy_url(self) -> str:
        if self.port is None:
            raise RuntimeError("Bridge belum dijalankan")
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> int:
        if self._server is not None:
            return int(self.port)  # type: ignore[arg-type]
        server = _ThreadingServer(("127.0.0.1", 0), _ProxyHandler)
        server.chain = self  # type: ignore[attr-defined]
        self._server = server
        self.port = int(server.server_address[1])
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)

    def __enter__(self) -> "ChainProxyServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
