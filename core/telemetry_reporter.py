#!/usr/bin/env python3
"""
Supabase Realtime Telemetry Reporter.

Membroadcast status bot dan statistik lokal mesin ke Supabase Realtime Channel
secara efisien melalui HTTP endpoint /realtime/v1/api/broadcast (REST to WebSocket).
100% numpang Realtime WebSocket:
- 0 Byte di database PostgreSQL Supabase (tidak ada tabel / DB queries).
- Semua statistik lokal disimpan di file data/local_node_stats.json di masing-masing mesin.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("TelemetryReporter")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "data" / "telemetry_config.json"
STATS_PATH = PROJECT_ROOT / "data" / "local_node_stats.json"


class TelemetryReporter:
    _instance: Optional[TelemetryReporter] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> TelemetryReporter:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self.config = self._load_config()
        self.supabase_url = self.config.get("supabase_url", "https://supabase.riztama.my.id").rstrip("/")
        self.supabase_key = self.config.get("supabase_key", "")
        self.topic = self.config.get("topic", "bot-nodes")
        self.broadcast_url = f"{self.supabase_url}/realtime/v1/api/broadcast"

        # Identitas Node (Bisa di-override lewat env var saat menjalankan bot di server)
        self.node_id = os.environ.get("BOT_NODE_ID") or self._generate_node_id()
        self.node_name = os.environ.get("BOT_NODE_NAME") or self._generate_node_name()

        self.stats = self._load_stats()
        self._last_broadcast_ts = 0.0
        self._min_interval = float(self.config.get("broadcast_interval_seconds", 2.0))
        self._queue_lock = threading.Lock()
        self._pending_payload: Optional[Dict[str, Any]] = None
        self._worker_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._worker_thread.start()

    def _generate_node_id(self) -> str:
        h = socket.gethostname().lower().replace(" ", "-")
        return f"{h}-{os.getpid()}"

    def _generate_node_name(self) -> str:
        h = socket.gethostname()
        system_os = platform.system()
        return f"🖥️ {h} ({system_os})"

    def set_node_name(self, name: str) -> None:
        self.node_name = name

    def _load_config(self) -> Dict[str, Any]:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "supabase_url": "https://supabase.riztama.my.id",
            "supabase_key": "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX",
            "topic": "bot-nodes",
            "broadcast_interval_seconds": 2.0,
        }

    def _load_stats(self) -> Dict[str, Any]:
        if STATS_PATH.exists():
            try:
                with open(STATS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        default_stats = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "created_at": time.time(),
            "total_sessions": 0,
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "anti_detect_100_count": 0,
            "bot_detected_count": 0,
            "recent_sessions": [],
        }
        self._save_stats(default_stats)
        return default_stats

    def _save_stats(self, stats: Dict[str, Any]) -> None:
        try:
            STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Gagal menyimpan local_node_stats.json: %s", e)

    def record_session_result(
        self,
        target: str,
        passed: bool,
        score: int,
        bot_detected: bool,
        proxy_ip: str = "—",
        country: str = "—",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mencatat hasil 1 sesi kunjungan ke file json lokal dan trigger broadcast."""
        with self._queue_lock:
            self.stats["total_sessions"] += 1
            if passed:
                self.stats["passed"] += 1
            else:
                self.stats["failed"] += 1

            if score >= 100 and not bot_detected:
                self.stats["anti_detect_100_count"] += 1

            if bot_detected:
                self.stats["bot_detected_count"] += 1

            history_entry = {
                "ts": int(time.time()),
                "target": target,
                "passed": passed,
                "score": score,
                "bot_detected": bot_detected,
                "proxy_ip": proxy_ip,
                "country": country,
            }
            if details:
                history_entry.update(details)

            recents = self.stats.get("recent_sessions", [])
            recents.insert(0, history_entry)
            self.stats["recent_sessions"] = recents[:30]  # Simpan 30 histori terakhir
            self._save_stats(self.stats)

    def broadcast_state(
        self,
        target_network: str,
        running: bool,
        uptime_seconds: int,
        workers: List[Dict[str, Any]],
        proxy_summary: Optional[Dict[str, Any]] = None,
        proxies: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Kirim state realtime bot + snapshot data statistik lokal via Supabase Realtime."""
        now = time.time()
        # Ringkasan statistik performa
        total_s = max(self.stats.get("total_sessions", 0), 1)
        pass_s = self.stats.get("passed", 0)
        perfect_ad = self.stats.get("anti_detect_100_count", 0)
        bot_det = self.stats.get("bot_detected_count", 0)

        payload = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "target_network": target_network,
            "running": running,
            "uptime_seconds": uptime_seconds,
            "workers": workers,
            "proxy_summary": proxy_summary or {},
            "proxies": proxies or [],
            "stats": {
                "total_sessions": self.stats.get("total_sessions", 0),
                "passed": pass_s,
                "failed": self.stats.get("failed", 0),
                "warned": self.stats.get("warned", 0),
                "pass_rate_pct": round((pass_s / total_s) * 100, 1) if self.stats.get("total_sessions", 0) > 0 else 0,
                "anti_detect_100_count": perfect_ad,
                "anti_detect_pct": round((perfect_ad / total_s) * 100, 1) if self.stats.get("total_sessions", 0) > 0 else 100,
                "bot_detected_count": bot_det,
                "recent_sessions": self.stats.get("recent_sessions", [])[:15],
            },
            "timestamp": int(now),
        }

        with self._queue_lock:
            self._pending_payload = payload

    def _broadcast_loop(self) -> None:
        """Background thread pengirim broadcast agar tidak memblokir antarmuka GUI."""
        while True:
            payload = None
            with self._queue_lock:
                if self._pending_payload is not None:
                    payload = self._pending_payload
                    self._pending_payload = None

            if payload and self.supabase_key:
                try:
                    headers = {
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json",
                    }
                    body = {
                        "messages": [
                            {
                                "topic": self.topic,
                                "event": "node_update",
                                "payload": payload,
                            }
                        ]
                    }
                    requests.post(self.broadcast_url, headers=headers, json=body, timeout=4.0)
                except Exception:
                    pass

            time.sleep(self._min_interval)


# Helper singleton getter
def get_telemetry_reporter() -> TelemetryReporter:
    return TelemetryReporter.get_instance()
