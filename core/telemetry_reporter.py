#!/usr/bin/env python3
"""
Supabase Persistent Realtime Telemetry Reporter (`proxxies.bot_nodes`).

Mengirim snapshot status terstruktur server & tiap worker langsung ke tabel
Supabase `proxxies.bot_nodes` (1 baris per `node_name`, persisten lintas restart)
sehingga `monitor-ui` dapat memantau armada secara realtime (Postgres Changes)
dan mendeteksi server/Colab yang mati lewat `last_heartbeat`.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("TelemetryReporter")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUPABASE_CONFIG_PATH = PROJECT_ROOT / "data" / "supabase_config.json"
SUPABASE_SERVICE_PATH = PROJECT_ROOT / "data" / "supabase_service.json"
TELEMETRY_CONFIG_PATH = PROJECT_ROOT / "data" / "telemetry_config.json"

_IMPRESSION_KEYS = (
    "vignette",
    "popunder",
    "direct_link",
    "banner",
    "in_page_push",
    "video_slider",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_breakdown() -> Dict[str, int]:
    return {k: 0 for k in _IMPRESSION_KEYS}


def _default_stats() -> Dict[str, Any]:
    return {
        "total_sessions": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate_pct": 0.0,
        "impressions_expected": 0,
        "impressions_breakdown": _empty_breakdown(),
        "sessions_per_hour": 0.0,
        "impressions_per_hour": 0.0,
    }


class TelemetryReporter:
    _instance: Optional["TelemetryReporter"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TelemetryReporter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self.config = self._load_config()
        self.supabase_url = str(self.config.get("supabase_url") or "https://supabase.riztama.my.id").rstrip("/")
        self.supabase_key = str(self.config.get("supabase_key") or "")
        self.schema = str(self.config.get("schema") or "proxxies")
        self.table = "bot_nodes"
        self.endpoint = f"{self.supabase_url}/rest/v1/{self.table}"

        default_host = socket.gethostname().strip() or "unknown-node"
        self.node_name = os.environ.get("BOT_NODE_NAME") or os.environ.get("BOT_NODE_ID") or default_host
        self.node_id = self.node_name
        self.started_at_ts = time.time()
        self.started_at_iso = _iso_now()

        self.meta: Dict[str, Any] = {
            "hostname": default_host,
            "os": platform.system(),
            "cpu_count": os.cpu_count() or 1,
        }

        self.stats: Dict[str, Any] = _default_stats()
        self._run_sessions = 0
        self._run_impressions = 0
        self._hydrated_name: Optional[str] = None
        self._last_error_logged: Optional[str] = None

        self._min_interval = max(2.0, float(self.config.get("heartbeat_interval_seconds", 4.0)))
        self._queue_lock = threading.Lock()
        self._pending_row: Optional[Dict[str, Any]] = None
        self._last_row: Optional[Dict[str, Any]] = None

        self._worker_thread = threading.Thread(target=self._upsert_loop, daemon=True, name="TelemetryUpsert")
        self._worker_thread.start()

    def _load_config(self) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {
            "supabase_url": "https://supabase.riztama.my.id",
            "supabase_key": "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
            "schema": "proxxies",
            "heartbeat_interval_seconds": 4.0,
        }
        for path in (TELEMETRY_CONFIG_PATH, SUPABASE_CONFIG_PATH):
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        cfg.update({k: v for k, v in data.items() if v is not None})
                except Exception:
                    pass
        if SUPABASE_SERVICE_PATH.exists():
            try:
                svc = json.loads(SUPABASE_SERVICE_PATH.read_text(encoding="utf-8"))
                if isinstance(svc, dict):
                    if svc.get("supabase_url"):
                        cfg["supabase_url"] = svc["supabase_url"]
                    if svc.get("supabase_key"):
                        cfg["supabase_key"] = svc["supabase_key"]
            except Exception:
                pass
        return cfg

    def _headers(self, prefer: str = "") -> Dict[str, str]:
        h = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def set_node_name(self, name: str) -> None:
        clean = str(name or "").strip()
        if not clean:
            return
        self.node_name = clean
        self.node_id = clean
        self._hydrate_remote_stats(clean)

    def _hydrate_remote_stats(self, node_name: str) -> None:
        """Tarik akumulasi stats sebelumnya dari Supabase agar restart tidak menimpa counter."""
        if not self.supabase_key or self._hydrated_name == node_name:
            return
        self._hydrated_name = node_name
        try:
            resp = requests.get(
                f"{self.endpoint}?node_name=eq.{quote(node_name, safe='')}&select=stats&limit=1",
                headers=self._headers(),
                timeout=3.5,
            )
            if resp.status_code != 200:
                return
            rows = resp.json()
            if not isinstance(rows, list) or not rows:
                return
            remote = rows[0].get("stats")
            if not isinstance(remote, dict):
                return
            with self._queue_lock:
                self.stats["total_sessions"] = int(remote.get("total_sessions") or 0)
                self.stats["passed"] = int(remote.get("passed") or 0)
                self.stats["failed"] = int(remote.get("failed") or 0)
                self.stats["impressions_expected"] = int(remote.get("impressions_expected") or 0)
                rb = remote.get("impressions_breakdown") or {}
                if isinstance(rb, dict):
                    for k in _IMPRESSION_KEYS:
                        self.stats["impressions_breakdown"][k] = int(rb.get(k) or 0)
                tot = self.stats["total_sessions"]
                self.stats["pass_rate_pct"] = round((self.stats["passed"] / tot) * 100, 1) if tot > 0 else 0.0
        except Exception:
            pass

    def record_session_result(
        self,
        target: str,
        passed: bool,
        score: int = 80,
        bot_detected: bool = False,
        proxy_ip: str = "—",
        country: str = "—",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Akumulasi hasil 1 sesi + rincian expected impressions."""
        metrics = details if isinstance(details, dict) else {}
        with self._queue_lock:
            self.stats["total_sessions"] += 1
            self._run_sessions += 1
            if passed:
                self.stats["passed"] += 1
            else:
                self.stats["failed"] += 1

            added_imp = 0
            breakdown = self.stats.setdefault("impressions_breakdown", _empty_breakdown())
            for k in _IMPRESSION_KEYS:
                val = int(metrics.get(k) or 0)
                if val > 0:
                    breakdown[k] = int(breakdown.get(k) or 0) + val
                    added_imp += val

            explicit_imp = int(metrics.get("expected_impressions") or 0)
            delta_imp = explicit_imp if explicit_imp > 0 else added_imp
            if delta_imp > 0:
                self.stats["impressions_expected"] = int(self.stats.get("impressions_expected") or 0) + delta_imp
                self._run_impressions += delta_imp

            tot = self.stats["total_sessions"]
            self.stats["pass_rate_pct"] = round((self.stats["passed"] / tot) * 100, 1) if tot > 0 else 0.0

            elapsed_h = max((time.time() - self.started_at_ts) / 3600.0, 1.0 / 3600.0)
            self.stats["sessions_per_hour"] = round(self._run_sessions / elapsed_h, 1)
            self.stats["impressions_per_hour"] = round(self._run_impressions / elapsed_h, 1)

    def broadcast_state(
        self,
        target_network: str,
        running: bool,
        uptime_seconds: int,
        workers: List[Dict[str, Any]],
        proxy_summary: Optional[Dict[str, Any]] = None,
        proxies: Optional[List[Dict[str, Any]]] = None,
        target_url: str = "",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Antrekan snapshot state terstruktur ke tabel Supabase `proxxies.bot_nodes`."""
        now_iso = _iso_now()
        with self._queue_lock:
            elapsed_h = max((time.time() - self.started_at_ts) / 3600.0, 1.0 / 3600.0)
            stats_snap = {
                "total_sessions": int(self.stats.get("total_sessions") or 0),
                "passed": int(self.stats.get("passed") or 0),
                "failed": int(self.stats.get("failed") or 0),
                "pass_rate_pct": float(self.stats.get("pass_rate_pct") or 0.0),
                "impressions_expected": int(self.stats.get("impressions_expected") or 0),
                "impressions_breakdown": dict(self.stats.get("impressions_breakdown") or _empty_breakdown()),
                "sessions_per_hour": round(self._run_sessions / elapsed_h, 1),
                "impressions_per_hour": round(self._run_impressions / elapsed_h, 1),
                "uptime_seconds": int(uptime_seconds),
            }
            meta_snap = dict(self.meta)
            if extra_meta:
                meta_snap.update(extra_meta)
            if proxy_summary:
                meta_snap["proxy_summary"] = proxy_summary

            row = {
                "node_name": self.node_name,
                "target_network": str(target_network or "MONETAG").upper(),
                "target_url": str(target_url or ""),
                "status": "RUNNING" if running else "STOPPED",
                "workers_count": len(workers),
                "workers_state": workers,
                "stats": stats_snap,
                "meta": meta_snap,
                "started_at": self.started_at_iso,
                "last_heartbeat": now_iso,
                "updated_at": now_iso,
            }
            self._pending_row = row
            self._last_row = row

    def mark_stopped(self) -> bool:
        """Flush sinkron status STOPPED saat Ctrl+C agar UI langsung membedakan stop normal vs crash."""
        with self._queue_lock:
            row = dict(self._last_row) if self._last_row else {
                "node_name": self.node_name,
                "target_network": "MONETAG",
                "target_url": "",
                "workers_count": 0,
                "workers_state": [],
                "stats": dict(self.stats),
                "meta": dict(self.meta),
                "started_at": self.started_at_iso,
            }
            now_iso = _iso_now()
            row["status"] = "STOPPED"
            row["last_heartbeat"] = now_iso
            row["updated_at"] = now_iso
            self._pending_row = None
        return self._send_upsert(row, timeout=3.0)

    def _send_upsert(self, row: Dict[str, Any], timeout: float = 4.5) -> bool:
        if not self.supabase_key:
            return False
        try:
            resp = requests.post(
                f"{self.endpoint}?on_conflict=node_name",
                headers=self._headers(prefer="resolution=merge-duplicates,return=minimal"),
                json=row,
                timeout=timeout,
            )
            if resp.status_code in (200, 201, 204):
                self._last_error_logged = None
                return True
            err_key = f"HTTP {resp.status_code}: {resp.text[:140]}"
            if err_key != self._last_error_logged:
                self._last_error_logged = err_key
                logger.warning("Telemetry upsert gagal (%s)", err_key)
            return False
        except Exception as exc:
            err_key = str(type(exc).__name__)
            if err_key != self._last_error_logged:
                self._last_error_logged = err_key
                logger.debug("Telemetry upsert exception: %s", exc)
            return False

    def _upsert_loop(self) -> None:
        while True:
            row = None
            with self._queue_lock:
                if self._pending_row is not None:
                    row = self._pending_row
                    self._pending_row = None
            if row is not None:
                self._send_upsert(row)
            time.sleep(self._min_interval)


def get_telemetry_reporter() -> TelemetryReporter:
    return TelemetryReporter.get_instance()
