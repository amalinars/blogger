"""Hop proxy registry (3xK) dari Supabase.

Tabel: `proxxies.hop_proxy_list`
RPC : `list_active_hops`, `upsert_hop_proxies`

Memakai kredensial Supabase yang sama dengan `core.proxy_manager`
(`data/supabase_config.json`).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILE = os.path.join(PROJECT_ROOT, "data", "supabase_config.json")
DEFAULT_TIMEOUT = 8.0

_VALID_SCHEMES = {"http", "https", "socks5"}


def load_supabase_config(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class HopRegistry:
    """Client tipis untuk tabel hop proxy di Supabase."""

    def __init__(self, config_path: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        cfg = load_supabase_config(config_path)
        self.supabase_url = str(cfg.get("supabase_url") or "").rstrip("/")
        self.supabase_key = str(cfg.get("supabase_key") or "")
        self.supabase_schema = str(cfg.get("schema") or "proxxies")
        self.timeout = float(timeout)
        self.enabled = bool(self.supabase_url and self.supabase_key)

    def _rpc(self, fn_name: str, payload: Dict[str, Any]) -> Any:
        if not self.enabled:
            return None
        endpoint = f"{self.supabase_url}/rest/v1/rpc/{fn_name}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept-Profile": self.supabase_schema,
            "Content-Profile": self.supabase_schema,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                endpoint, headers=headers, json=payload, timeout=self.timeout
            )
        except Exception:
            return None
        if resp.status_code not in (200, 201, 204):
            return None
        if resp.status_code == 204 or not resp.content:
            return []
        try:
            return resp.json()
        except ValueError:
            return None

    @staticmethod
    def _to_hop(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            port = int(row.get("port") or 0)
        except (TypeError, ValueError):
            return None
        host = str(row.get("host") or "").strip()
        if not host or port <= 0:
            return None
        scheme = str(row.get("proxy_scheme") or "http").strip().lower()
        if scheme not in _VALID_SCHEMES:
            scheme = "http"
        if scheme == "https":
            scheme = "http"
        row_id = row.get("id")
        return {
            "id": f"hop#{row_id}",
            "idx": row_id,
            "host": host,
            "port": port,
            "username": str(row.get("username") or ""),
            "password": str(row.get("password") or ""),
            "proxy_scheme": scheme,
            "country": row.get("country") or "",
            "source": "supabase",
        }

    def list_hops(self) -> List[Dict[str, Any]]:
        rows = self._rpc("list_active_hops", {})
        if not isinstance(rows, list):
            return []
        hops = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            hop = self._to_hop(row)
            if hop:
                hops.append(hop)
        return hops

    def upsert_hops(self, hops: List[Dict[str, Any]]) -> bool:
        if not self.enabled or not hops:
            return False
        rows = self._rpc("upsert_hop_proxies", {"p_hops": hops})
        return rows is not None


def list_hops(config_path: Optional[str] = None) -> List[Dict[str, Any]]:
    return HopRegistry(config_path=config_path).list_hops()


def upsert_hops(
    hops: List[Dict[str, Any]], config_path: Optional[str] = None
) -> bool:
    return HopRegistry(config_path=config_path).upsert_hops(hops)