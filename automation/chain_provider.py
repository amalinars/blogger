#!/usr/bin/env python3
"""Provider chain GoLogin: hop 3xK acak -> residential FloppyData Supabase.

Alur per sesi:
  1. Acak hop dari `data/proxies_scrape.txt` (bukan urut baris).
  2. Acquire 1 residential ALIVE dari channel gologin Supabase.
  3. Probe hop, lalu probe chain penuh untuk memastikan exit IP = FloppyData.
  4. Start local bridge `127.0.0.1:<port>` yang dipakai browser.
  5. Setelah sesi: update state, release lease, stop bridge.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proxy_chain_tester import ChainError, fetch_through_chain

from automation.proxy_bridge import ChainProxyServer
from core.proxy_manager import (
    acquire_proxy,
    record_probe,
    record_target_hit,
    release_proxy,
    report_cooldown,
    report_dead,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCRAPE_FILE = os.path.join(PROJECT_ROOT, "data", "proxies_scrape.txt")

DEFAULT_PROBE_TARGETS = [
    "http://ip-api.com/json/?fields=status,message,country,countryCode,isp,org,as,query,proxy,hosting",
    "http://api.ipify.org?format=json",
]

FATAL_PROXY_STATUS = {403, 407}


def _short(text: Any, limit: int = 220) -> str:
    value = str(text or "").replace("\n", " ").strip()
    return value[:limit]


def parse_hop_file(path: str) -> List[Dict[str, Any]]:
    """Parse `[scheme://]user:pass@host:port` menjadi item hop."""
    items: List[Dict[str, Any]] = []
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError as exc:
        print(f"! File hop tidak bisa dibaca: {path} ({exc})")
        return items

    with fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            scheme = "http"
            if "://" in line:
                scheme, _, line = line.partition("://")
                scheme = scheme.strip().lower()
                if scheme not in ("http", "https", "socks5"):
                    print(f"! Hop baris {lineno} scheme tidak didukung: {scheme}")
                    continue
                if scheme == "https":
                    scheme = "http"
            cred, sep, hostport = line.rpartition("@")
            if sep:
                username, _, password = cred.partition(":")
            else:
                username, password = "", ""
                hostport = line
            host, _, port_s = hostport.rpartition(":")
            if not host or not port_s.isdigit():
                print(f"! Hop baris {lineno} format salah: {line[:60]}")
                continue
            items.append(
                {
                    "id": f"hop#{lineno}",
                    "idx": lineno,
                    "host": host.strip(),
                    "port": int(port_s),
                    "username": username.strip(),
                    "password": password.strip(),
                    "proxy_scheme": scheme,
                    "source": "scrape",
                }
            )
    return items


class ChainProxyProvider:
    """Sumber proxy chain untuk `run_gologin_harvest_job`."""

    def __init__(
        self,
        scrape_file: str = DEFAULT_SCRAPE_FILE,
        hop_tries: int = 3,
        timeout: float = 15.0,
        cooldown_seconds: int = 900,
        dead_confirm_hops: int = 2,
        hop_blacklist_seconds: float = 300.0,
        probe_targets: Optional[List[str]] = None,
        verbose: bool = False,
    ):
        self.scrape_file = scrape_file
        self.hop_tries = max(1, int(hop_tries))
        self.timeout = float(timeout)
        self.cooldown_seconds = max(60, int(cooldown_seconds))
        self.dead_confirm_hops = max(1, int(dead_confirm_hops))
        self.hop_blacklist_seconds = max(0.0, float(hop_blacklist_seconds))
        self.probe_targets = list(probe_targets or DEFAULT_PROBE_TARGETS)
        self.verbose = verbose

        self.hops = parse_hop_file(scrape_file)
        self._rng = random.SystemRandom()
        self._hop_blacklist: Dict[str, float] = {}
        if not self.hops:
            raise ValueError(f"Tidak ada hop valid di {scrape_file}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def next_proxy(self) -> Optional[Dict[str, Any]]:
        caller_id = f"chain_{uuid.uuid4().hex[:10]}"
        residential = acquire_proxy(
            caller_id=caller_id,
            target="gologin",
            verify_alive=False,
            channel="gologin",
            strict_channel=True,
        )
        if not residential:
            return None

        release_caller = (
            residential.get("leased_by")
            or residential.get("lease_token")
            or caller_id
        )
        res_chain = self._chain_item(residential, residential.get("supabase_id") or 0)

        selected_hops = self._pick_hops(self.hop_tries)
        dead_votes = 0
        fatal_dead = False
        reasons: List[str] = []
        target_errors: List[str] = []

        for hop in selected_hops:
            hop_probe = None
            try:
                hop_probe = self._probe([hop])
            except ChainError as exc:
                self._blacklist_hop(hop)
                reasons.append(f"hop {hop['host']} mati: {_short(exc)}")
                continue

            try:
                chain_probe = self._probe([hop, res_chain])
            except ChainError as exc:
                if exc.stage == "hop_tcp":
                    self._blacklist_hop(hop)
                    reasons.append(f"hop {hop['host']} mati: {_short(exc)}")
                elif exc.stage == "proxy_connect":
                    if exc.status in FATAL_PROXY_STATUS:
                        fatal_dead = True
                        reasons.append(
                            f"residential menolak auth (HTTP {exc.status}): {_short(exc)}"
                        )
                        break
                    dead_votes += 1
                    reasons.append(f"residential tidak bisa dihubungi: {_short(exc)}")
                elif exc.stage == "target":
                    target_errors.append(_short(exc))
                else:
                    reasons.append(f"probe chain gagal: {_short(exc)}")
                continue

            exit_ip = chain_probe.get("exit_ip")
            hop_exit_ip = (hop_probe or {}).get("exit_ip")
            if not exit_ip:
                target_errors.append("probe chain tidak mengembalikan exit IP")
                continue
            if hop_exit_ip and exit_ip == hop_exit_ip:
                self._blacklist_hop(hop)
                reasons.append(
                    f"hop {hop['host']} transparent (exit IP sama dengan hop)"
                )
                continue

            country = (
                chain_probe.get("country")
                or residential.get("country")
                or ""
            )
            country_code = chain_probe.get("country_code") or ""

            bridge = ChainProxyServer(
                [hop, res_chain], timeout=self.timeout, verbose=self.verbose
            )
            try:
                port = bridge.start()
            except Exception as exc:
                reasons.append(f"gagal start bridge: {_short(exc)}")
                continue

            try:
                record_probe(
                    residential,
                    ip_detected=exit_ip,
                    latency_ms=chain_probe.get("latency_ms"),
                    channel="gologin",
                    strict_channel=True,
                )
            except Exception as exc:
                print(f"! Gagal update probe Supabase: {_short(exc)}")

            print(
                f"   chain: hop={hop['host']}:{hop['port']} "
                f"-> residential={residential.get('host')}:{residential.get('port')} "
                f"(id={residential.get('supabase_id')}, {country or country_code or '?'}) "
                f"-> exit={exit_ip} | {chain_probe.get('latency_ms')}ms"
            )

            return {
                "id": f"chain#{residential.get('supabase_id')}",
                "supabase_id": residential.get("supabase_id"),
                "host": "127.0.0.1",
                "port": port,
                "username": "",
                "password": "",
                "proxy_scheme": "http",
                "country": country,
                "country_code": country_code,
                "connection_type": "residential",
                "expected_ip": exit_ip,
                "ip_detected": exit_ip,
                "expected_asn": chain_probe.get("asn") or "",
                "expected_isp": chain_probe.get("isp") or "",
                "allow_ip_rotation": True,
                "latency_ms": chain_probe.get("latency_ms"),
                "source": "chain",
                "channel": "gologin",
                "verify_country": bool(country or country_code),
                "hop_ip": hop["host"],
                "hop_port": hop["port"],
                "residential_id": residential.get("supabase_id"),
                "residential_host": residential.get("host"),
                "caller_id": release_caller,
                "bridge": bridge,
                "_residential": residential,
                "_hop": hop,
                "_res_chain": res_chain,
            }

        # Semua hop gagal: putuskan apakah residential memang mati atau cuma hop.
        if fatal_dead or dead_votes >= self.dead_confirm_hops:
            reason = "Residential tidak bisa connect: " + "; ".join(reasons[-3:])
            try:
                report_dead(
                    residential,
                    reason=reason,
                    is_fatal=fatal_dead,
                    force_dead=(not fatal_dead and dead_votes >= self.dead_confirm_hops),
                    cooldown_seconds=self.cooldown_seconds,
                    channel="gologin",
                    strict_channel=True,
                )
            except Exception as exc:
                print(f"! Gagal menandai DEAD: {_short(exc)}")
        elif target_errors:
            reason = f"Probe target gagal lewat chain: {target_errors[-1]}"
            try:
                report_cooldown(
                    residential,
                    reason=reason,
                    cooldown_seconds=self.cooldown_seconds,
                    channel="gologin",
                    strict_channel=True,
                )
            except Exception as exc:
                print(f"! Gagal menandai COOLDOWN: {_short(exc)}")
        else:
            print(
                "   Semua hop 3xK gagal; residential tidak dihukum (bukan bukti IP mati)."
            )

        self._release(residential, release_caller)
        return None

    def finish_session(
        self,
        proxy: Optional[Dict[str, Any]],
        success: bool,
        error: Optional[BaseException] = None,
        error_kind: str = "other",
    ) -> None:
        """Selalu stop bridge, update state sesuai jenis error, lalu release lease."""
        if not proxy:
            return

        bridge = proxy.get("bridge")
        if bridge is not None:
            try:
                bridge.stop()
            except Exception:
                pass

        residential = proxy.get("_residential") or {}
        if not residential:
            return

        caller_id = proxy.get("caller_id") or residential.get("leased_by")
        try:
            if success:
                try:
                    record_target_hit(
                        residential,
                        target="gologin",
                        channel="gologin",
                        strict_channel=True,
                    )
                except Exception as exc:
                    print(f"! Gagal record target hit: {_short(exc)}")
            elif error_kind == "shutdown":
                print("   Sesi dihentikan; health proxy tidak diubah.")
            elif error_kind == "test":
                print("   Chain test selesai; health proxy tidak diubah.")
            elif error_kind == "cloudflare":
                self._cooldown(
                    residential,
                    f"Cloudflare/Turnstile blocked exit {proxy.get('expected_ip') or '?'}: {_short(error)}",
                )
            elif error_kind == "verification":
                self._cooldown(
                    residential,
                    f"Verification failed (exit IP/leak): {_short(error)}",
                )
            else:
                self._handle_runtime_failure(proxy, residential, error, error_kind)
        finally:
            self._release(residential, caller_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _cooldown(self, residential: Dict[str, Any], reason: str) -> None:
        try:
            report_cooldown(
                residential,
                reason=reason,
                cooldown_seconds=self.cooldown_seconds,
                channel="gologin",
                strict_channel=True,
            )
        except Exception as exc:
            print(f"! Gagal menandai COOLDOWN: {_short(exc)}")

    def _release(self, residential: Dict[str, Any], caller_id: Optional[str]) -> None:
        try:
            release_proxy(
                residential,
                caller_id=caller_id,
                channel="gologin",
                strict_channel=True,
            )
        except Exception as exc:
            print(f"! Gagal release lease: {_short(exc)}")

    def _handle_runtime_failure(
        self,
        proxy: Dict[str, Any],
        residential: Dict[str, Any],
        error: Optional[BaseException],
        error_kind: str,
    ) -> None:
        hop = proxy.get("_hop")
        res_chain = proxy.get("_res_chain")
        if not hop or not res_chain:
            self._cooldown(residential, f"{error_kind}: {_short(error)}")
            return

        try:
            probe = self._probe([hop, res_chain])
        except ChainError as exc:
            if exc.stage == "hop_tcp":
                self._blacklist_hop(hop)
                print(
                    f"   Hop {hop.get('host')} mati saat sesi; residential tidak dihukum."
                )
                return
            if exc.stage == "proxy_connect":
                fatal = exc.status in FATAL_PROXY_STATUS
                try:
                    report_dead(
                        residential,
                        reason=(
                            f"Sesi gagal ({error_kind}): {_short(error)}; "
                            f"chain probe gagal: {_short(exc)}"
                        ),
                        is_fatal=fatal,
                        cooldown_seconds=self.cooldown_seconds,
                        channel="gologin",
                        strict_channel=True,
                    )
                except Exception as report_exc:
                    print(f"! Gagal menandai DEAD: {_short(report_exc)}")
                return
            if exc.stage == "target":
                self._cooldown(
                    residential,
                    f"Sesi gagal ({error_kind}): {_short(error)}; target probe gagal: {_short(exc)}",
                )
                return
            self._cooldown(residential, f"{error_kind}: {_short(error)}")
            return
        except Exception as exc:
            self._cooldown(residential, f"{error_kind}: {_short(error)} ({_short(exc)})")
            return

        self._cooldown(
            residential,
            f"Sesi gagal ({error_kind}): {_short(error)}; chain masih hidup "
            f"({probe.get('latency_ms')}ms, exit {probe.get('exit_ip')})",
        )

    def _chain_item(self, proxy: Dict[str, Any], idx: Any) -> Dict[str, Any]:
        return {
            "idx": idx,
            "host": proxy.get("host"),
            "port": int(proxy.get("port") or 0),
            "username": proxy.get("username") or "",
            "password": proxy.get("password") or "",
        }

    def _pick_hops(self, count: int) -> List[Dict[str, Any]]:
        now = time.time()
        available = [
            hop
            for hop in self.hops
            if self._hop_blacklist.get(hop["host"], 0.0) <= now
        ]
        if not available:
            self._hop_blacklist.clear()
            available = list(self.hops)
        self._rng.shuffle(available)
        return available[: max(1, count)]

    def _blacklist_hop(self, hop: Dict[str, Any]) -> None:
        if self.hop_blacklist_seconds > 0:
            self._hop_blacklist[hop["host"]] = time.time() + self.hop_blacklist_seconds

    def _probe(
        self,
        chain: List[Dict[str, Any]],
        targets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        last_error: Optional[ChainError] = None
        for target in targets or self.probe_targets:
            try:
                result = fetch_through_chain(
                    chain, target, timeout=self.timeout, verbose=self.verbose
                )
            except ChainError as exc:
                last_error = exc
                if exc.stage in ("hop_tcp", "proxy_connect"):
                    raise
                continue

            body = result.get("body") or ""
            data: Dict[str, Any] = {}
            try:
                loaded = json.loads(body)
                if isinstance(loaded, dict):
                    data = loaded
            except (TypeError, ValueError):
                pass

            exit_ip = result.get("exit_ip") or data.get("query") or data.get("ip")
            if not exit_ip:
                last_error = ChainError(
                    "Probe tidak mengembalikan IP",
                    stage="target",
                    proxy_index=chain[-1].get("idx") if chain else None,
                )
                continue

            return {
                "ok": True,
                "exit_ip": str(exit_ip),
                "latency_ms": result.get("latency_ms"),
                "country": data.get("country") or "",
                "country_code": data.get("countryCode") or "",
                "isp": data.get("isp") or "",
                "org": data.get("org") or "",
                "asn": data.get("as") or "",
                "proxy": data.get("proxy"),
                "hosting": data.get("hosting"),
                "target": target,
                "body": body,
            }

        if last_error is not None:
            raise last_error
        raise ChainError(
            "Semua endpoint probe gagal",
            stage="target",
            proxy_index=chain[-1].get("idx") if chain else None,
        )
