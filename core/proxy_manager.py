"""
Proxy Management Module
Satu-satunya source of truth untuk daftar proxy, status validasi,
status penggunaan, dan posisi cursor rotasi persisten di proxies.json.
"""

import os
import json
import time
import re
import uuid
import threading
import concurrent.futures
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List, Union, Tuple
import requests

# Path default ke data/proxies.json di root project
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROXY_FILE = os.path.join(PROJECT_ROOT, "data", "proxies.json")

CHECK_URL = "http://api.ipify.org?format=json"
CHECK_TIMEOUT = 7
CACHE_VALIDITY_SECONDS = 1800  # 30 menit validasi ALIVE tetap dianggap fresh
MAX_FAIL_THRESHOLD = 3  # Batas toleransi error sebelum revalidasi ketat

# Status Constants
HEALTH_UNKNOWN = "UNKNOWN"
HEALTH_ALIVE = "ALIVE"
HEALTH_DEAD = "DEAD"
HEALTH_COOLDOWN = "COOLDOWN"

USAGE_IDLE = "IDLE"
USAGE_IN_USE = "IN_USE"

# Channel/consumer yang memakai pool proxy yang sama.
# Automation memakai kolom default; GoLogin memakai kolom berakhiran _gologin
# agar lease, usage, health, dan target cooldown tidak saling mengunci.
CHANNEL_AUTOMATION = "automation"
CHANNEL_GOLOGIN = "gologin"

# Error yang muncul karena browser/page sengaja ditutup (Ctrl+C, stop script).
# Ini BUKAN kegagalan proxy, jadi health tidak boleh diubah.
SHUTDOWN_ERROR_HINTS = (
    "target page, context or browser has been closed",
    "targetclosederror",
    "targetclosed",
    "target closed",
    "browser has been closed",
    "browserclosed",
    "context or browser has been closed",
    "page has been closed",
    "page closed",
    "browser closed",
    "operation was canceled",
    "operation cancelled",
    "cancellederror",
)

UNREACHABLE_ERRORS = (
    "ConnectionRefused",
    "connection refused",
    "ConnectionReset",
    "connection reset",
    "connection closed",
    "ConnectionClosed",
    "HostUnreachable",
    "no route to host",
    "network unreachable",
    "NetworkUnreachable",
    "ENETUNREACH",
    "EHOSTUNREACH",
    "ECONNREFUSED",
    "ECONNRESET",
    "NameResolutionError",
    "getaddrinfo failed",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_PROXY_CONNECTION_FAILED",
    "Tunnel connection failed",
    "Proxy Authentication Required",
    "407",
    "ProxyError",
    "SOCKSHTTPConnection",
    "SSLError",
    "CERTIFICATE_VERIFY_FAILED",
)

TIMEOUT_ERRORS = (
    "Timeout",
    "timeout",
    "ConnectTimeout",
    "ReadTimeout",
    "TimeoutError",
    "exceeded",
    "timed out",
    "ETIMEDOUT",
    "ERR_TIMED_OUT",
    "ERR_CONNECTION_TIMED_OUT",
)

KNOWN_PROXY_ERRORS = UNREACHABLE_ERRORS + TIMEOUT_ERRORS


class ProxyManager:
    def __init__(
        self,
        filepath: str = DEFAULT_PROXY_FILE,
        check_url: str = CHECK_URL,
        timeout: int = CHECK_TIMEOUT,
        reset_stale_usage: bool = False,
        reset_cursor: bool = False,
        enable_supabase: Optional[bool] = None,
        node_id: Optional[str] = None,
    ):
        self.filepath = os.path.abspath(filepath)
        self.check_url = check_url
        self.timeout = timeout
        self._lock = threading.RLock()
        self._ensure_file()

        # Supabase Distributed Coordination (Zero Race Condition across VPS / Colab)
        is_default_file = (self.filepath == os.path.abspath(DEFAULT_PROXY_FILE))
        should_use_supabase = enable_supabase if enable_supabase is not None else is_default_file
        raw_node = node_id or os.environ.get("BOT_NODE_ID") or f"node_{uuid.uuid4().hex[:6]}"
        self.node_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(raw_node))
        self.supabase_enabled = False
        self.supabase_rpc_available = False
        self._gologin_rpc_warned = False
        if should_use_supabase:
            sb_cfg_file = os.path.join(PROJECT_ROOT, "data", "supabase_config.json")
            if not os.path.exists(sb_cfg_file):
                sb_cfg_file = os.path.join(PROJECT_ROOT, "data", "telemetry_config.json")
            if os.path.exists(sb_cfg_file):
                try:
                    with open(sb_cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    self.supabase_url = cfg.get("supabase_url", "").rstrip("/")
                    self.supabase_key = cfg.get("supabase_key", "")
                    self.supabase_schema = cfg.get("schema", "proxxies")
                    self.supabase_table = cfg.get("table", "proxy_list")
                    if self.supabase_url and self.supabase_key:
                        self.supabase_enabled = True
                except Exception:
                    pass

        if reset_stale_usage:
            self.reset_usage_to_idle()
        if reset_cursor:
            self.reset_cursor(0)

    @staticmethod
    def _is_shutdown_error(error_message: Optional[str]) -> bool:
        """True jika error berasal dari browser/context yang ditutup saat stop, bukan proxy mati."""
        msg = str(error_message or "").strip().lower()
        if not msg:
            return False
        return any(hint in msg for hint in SHUTDOWN_ERROR_HINTS)

    @staticmethod
    def _resolve_channel(identifier: Any, channel: str) -> str:
        """Pastikan proxy hasil acquire gologin tetap tercatat ke kolom gologin meski caller lupa pass channel."""
        if isinstance(identifier, dict) and identifier.get("channel") == CHANNEL_GOLOGIN and channel == CHANNEL_AUTOMATION:
            return CHANNEL_GOLOGIN
        return channel or CHANNEL_AUTOMATION

    @staticmethod
    def _channel_keys(channel: Optional[str] = None) -> Dict[str, str]:
        """Nama field state proxy sesuai channel (automation vs GoLogin)."""
        suffix = "_gologin" if (channel or CHANNEL_AUTOMATION) == CHANNEL_GOLOGIN else ""
        return {
            "health": f"health{suffix}",
            "usage": f"usage{suffix}",
            "leased_by": f"leased_by{suffix}",
            "lease_time": f"lease_time{suffix}",
            "target_usage": f"target_usage{suffix}",
            "fail_count": f"fail_count{suffix}",
            "last_error": f"last_error{suffix}",
            "last_checked": f"last_checked{suffix}",
            "ip_detected": f"ip_detected{suffix}",
            "latency_ms": f"latency_ms{suffix}",
            "cooldown_until": f"cooldown_until{suffix}",
        }

    def _supabase_rpc(self, fn_name: str, payload: Dict[str, Any], timeout: float = 8.0) -> Tuple[Any, int]:
        """Memanggil PostgreSQL Stored Procedure (RPC) di Supabase dengan aman."""
        if not self.supabase_enabled:
            return None, 0
        endpoint = f"{self.supabase_url}/rest/v1/rpc/{fn_name}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept-Profile": self.supabase_schema,
            "Content-Profile": self.supabase_schema,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in (200, 201):
                return resp.json(), resp.status_code
            return None, resp.status_code
        except Exception:
            return None, 0

    def _acquire_proxy_supabase(
        self,
        caller_id: str,
        target: Optional[str] = None,
        max_uses_per_day: int = 2,
        cooldown_seconds: float = 6 * 3600,
        lease_seconds: int = 600,
        window_seconds: float = 24 * 3600,
        channel: str = CHANNEL_AUTOMATION,
    ) -> Optional[Dict[str, Any]]:
        """
        Mengambil 1 proxy dari Supabase dengan PostgreSQL atomic lock (FOR UPDATE SKIP LOCKED).
        Menjamin 100% bebas race condition meskipun dijalankan di puluhan VPS / Colab sekaligus.

        channel="gologin" memakai RPC & kolom *_gologin sehingga tidak bertabrakan
        dengan lease/usage/health milik automation.
        """
        payload = {
            "p_caller_id": caller_id,
            "p_target": target or "monetag",
            "p_max_uses_per_day": int(max_uses_per_day),
            "p_cooldown_seconds": int(cooldown_seconds),
            "p_lease_seconds": int(lease_seconds),
            "p_window_seconds": int(window_seconds),
        }
        is_gologin = channel == CHANNEL_GOLOGIN
        fn_name = "acquire_proxy_gologin" if is_gologin else "acquire_proxy"
        res, status = self._supabase_rpc(fn_name, payload)
        used_channel = channel
        if is_gologin and status == 404:
            # Jangan pernah fallback ke kolom automation: state GoLogin bisa tercampur.
            if not self._gologin_rpc_warned:
                self._gologin_rpc_warned = True
                print(
                    "RPC GoLogin belum ada di Supabase. Jalankan setup_supabase_gologin.sql "
                    "dan setup_supabase_chain_gologin.sql. Operasi gologin dibatalkan.",
                    flush=True,
                )
            return None
        if status in (200, 201):
            self.supabase_rpc_available = True
            if isinstance(res, list) and len(res) > 0:
                row = res[0]
                host = row.get("host")
                port = int(row.get("port"))
                user = row.get("username", "")
                pwd = row.get("password", "")
                proxy_url = f"http://{user}:{pwd}@{host}:{port}" if user and pwd else f"http://{host}:{port}"
                keys = self._channel_keys(used_channel)
                return {
                    "id": row.get("id"),
                    "supabase_id": row.get("id"),
                    "host": host,
                    "port": port,
                    "username": user,
                    "password": pwd,
                    "proxy_url": proxy_url,
                    "country": row.get("country", "US"),
                    "connection_type": row.get("connection_type", "residential"),
                    "health": row.get(keys["health"], row.get("health", "ALIVE")),
                    "usage": "IN_USE",
                    "leased_by": caller_id,
                    "lease_token": caller_id,
                    "target_usage": row.get(keys["target_usage"], row.get("target_usage")) or {},
                    "channel": used_channel,
                    "supabase_channel": used_channel,
                    "source": "supabase_rpc",
                }
            return None  # RPC sukses tapi tidak ada kandidat proxy tersedia saat ini
        return None

    def _ensure_file(self):
        """Memastikan direktori dan proxies.json ada, melakukan migrasi jika masih berupa format array lama."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            self._save_raw({"cursor": 0, "proxies": []})
        else:
            # Validasi isi file dan migrasi jika perlu
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    self._save_raw({"cursor": 0, "proxies": []})
                    return
                data = json.loads(content)
                if isinstance(data, list):
                    # Migrasi format list lama ke format dictionary dengan cursor
                    converted = []
                    for idx, item in enumerate(data):
                        converted.append(self._normalize_proxy(item, idx))
                    self._save_raw({"cursor": 0, "proxies": converted})
                elif isinstance(data, dict):
                    if "proxies" not in data or not isinstance(data["proxies"], list):
                        data["proxies"] = []
                    if "cursor" not in data or not isinstance(data["cursor"], int):
                        data["cursor"] = 0
                    # Normalisasi properti proxy yang mungkin kurang
                    modified = False
                    for idx, item in enumerate(data["proxies"]):
                        norm = self._normalize_proxy(item, idx)
                        if norm != item:
                            data["proxies"][idx] = norm
                            modified = True
                    if modified:
                        self._save_raw(data)
            except Exception:
                # File korup / tidak valid: inisialisasi aman
                self._save_raw({"cursor": 0, "proxies": []})

    def _normalize_proxy(self, p: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
        """Menjamin seluruh properti kesehatan, penggunaan, dan identitas ada pada proxy."""
        item = dict(p)
        # Identitas unik
        if "id" not in item or not item["id"]:
            # Gunakan proxy_url atau buat ID stabil
            item["id"] = f"proxy_{idx + 1}_{uuid.uuid4().hex[:6]}"

        # Health status
        raw_health = str(item.get("health", item.get("status", HEALTH_UNKNOWN))).upper()
        if raw_health in (HEALTH_ALIVE, "ACTIVE"):
            item["health"] = HEALTH_ALIVE
        elif raw_health in (HEALTH_DEAD, "INACTIVE", "FAILED"):
            item["health"] = HEALTH_DEAD
        elif raw_health == HEALTH_COOLDOWN:
            item["health"] = HEALTH_COOLDOWN
        else:
            item["health"] = HEALTH_UNKNOWN

        # Usage status
        raw_usage = str(item.get("usage", "")).upper()
        if raw_usage == USAGE_IN_USE:
            item["usage"] = USAGE_IN_USE
        else:
            item["usage"] = USAGE_IDLE

        # Metadata validasi & tracking
        item.setdefault("last_checked", None)
        item.setdefault("latency_ms", None)
        item.setdefault("ip_detected", None)
        item.setdefault("fail_count", 0)
        item.setdefault("last_error", None)
        item.setdefault("leased_by", None)
        item.setdefault("lease_time", None)

        # Modular target usage flags (misal: adsterra, youtube)
        if "target_usage" not in item or not isinstance(item["target_usage"], dict):
            item["target_usage"] = {}

        # State terpisah untuk channel GoLogin
        item.setdefault("health_gologin", item["health"])
        item.setdefault("usage_gologin", USAGE_IDLE)
        item.setdefault("leased_by_gologin", None)
        item.setdefault("lease_time_gologin", None)
        item.setdefault("fail_count_gologin", 0)
        item.setdefault("last_error_gologin", None)
        item.setdefault("last_checked_gologin", None)
        item.setdefault("ip_detected_gologin", None)
        item.setdefault("latency_ms_gologin", None)
        item.setdefault("cooldown_until_gologin", None)
        if "target_usage_gologin" not in item or not isinstance(item["target_usage_gologin"], dict):
            item["target_usage_gologin"] = {}

        # Hapus key lama status jika bentrok
        if "status" in item and item["status"] in ("idle", "in_use", "active", "alive", "dead"):
            del item["status"]

        return item

    def _load_raw(self) -> Dict[str, Any]:
        """Membaca proxies.json secara aman."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "proxies" in data:
                return data
        except Exception:
            pass
        return {"cursor": 0, "proxies": []}

    def _save_raw(self, data: Dict[str, Any]):
        """Menyimpan ke proxies.json secara atomic dengan file temp untuk mencegah file rusak."""
        dir_name = os.path.dirname(self.filepath)
        temp_file = os.path.join(dir_name, f".proxies_tmp_{uuid.uuid4().hex}.json")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.filepath)
        except Exception as e:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            raise e

    # =========================================================================
    # 1. MANAJEMEN PROXY
    # =========================================================================

    def _parse_proxy_input(self, item: Union[Dict[str, Any], str]) -> Optional[Dict[str, Any]]:
        """Mengonversi input proxy (dict atau string baris) menjadi dictionary standar."""
        if isinstance(item, dict):
            return dict(item)
        if isinstance(item, str):
            line = item.strip()
            if not line:
                return None
            try:
                if "://" in line:
                    parsed = urlparse(line)
                    host = parsed.hostname
                    port = parsed.port
                    username = parsed.username or ""
                    password = parsed.password or ""
                    proxy_url = line
                else:
                    parts = line.split(":")
                    if len(parts) == 4:
                        host, port, username, password = parts
                        port = int(port)
                        proxy_url = f"http://{username}:{password}@{host}:{port}"
                    else:
                        return None

                country = "Residential (FloppyData)" if "geo.floppydata.com" in (host or "") else "Unknown"
                return {
                    "country": country,
                    "connection_type": "residential",
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                    "proxy_url": proxy_url,
                }
            except Exception:
                return None
        return None

    def append_proxy(self, proxy_data: Union[Dict[str, Any], str]) -> Optional[Dict[str, Any]]:
        """Menambahkan/meng-append satu proxy ke proxies.json jika belum ada."""
        parsed = self._parse_proxy_input(proxy_data)
        if not parsed:
            return None

        with self._lock:
            data = self._load_raw()
            proxies = data["proxies"]

            url = parsed.get("proxy_url")
            if url:
                for p in proxies:
                    if p.get("proxy_url") == url:
                        return p  # Sudah ada

            normalized = self._normalize_proxy(parsed, len(proxies))
            proxies.append(normalized)
            self._save_raw(data)
            return normalized

    def append_proxies(self, proxy_list: List[Union[Dict[str, Any], str]]) -> int:
        """Menambahkan/meng-append banyak proxy sekaligus ke proxies.json tanpa duplikasi proxy_url."""
        with self._lock:
            data = self._load_raw()
            existing_urls = {p.get("proxy_url") for p in data["proxies"] if p.get("proxy_url")}
            added = 0
            for raw in proxy_list:
                parsed = self._parse_proxy_input(raw)
                if not parsed:
                    continue
                url = parsed.get("proxy_url")
                if not url or url not in existing_urls:
                    normalized = self._normalize_proxy(parsed, len(data["proxies"]))
                    data["proxies"].append(normalized)
                    if url:
                        existing_urls.add(url)
                    added += 1
            if added > 0:
                self._save_raw(data)
            return added

    # Alias add_proxy / add_proxies
    add_proxy = append_proxy
    add_proxies = append_proxies

    def get_proxy_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        """Mengambil proxy berdasarkan indeks urutan di proxies.json."""
        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])
            if 0 <= index < len(proxies):
                return dict(proxies[index])
            return None

    def remove_proxy(self, identifier: str) -> bool:
        """Menghapus proxy berdasarkan id atau proxy_url."""
        with self._lock:
            data = self._load_raw()
            proxies = data["proxies"]
            original_len = len(proxies)
            data["proxies"] = [p for p in proxies if p.get("id") != identifier and p.get("proxy_url") != identifier]

            if len(data["proxies"]) < original_len:
                # Sesuaikan cursor jika melebihi panjang baru
                if data["proxies"]:
                    data["cursor"] = data["cursor"] % len(data["proxies"])
                else:
                    data["cursor"] = 0
                self._save_raw(data)
                return True
            return False

    def delete_dead_proxies(self) -> int:
        """Menghapus seluruh proxy yang berstatus DEAD dari proxies.json."""
        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])
            original_len = len(proxies)
            data["proxies"] = [p for p in proxies if p.get("health") != HEALTH_DEAD]
            deleted_count = original_len - len(data["proxies"])

            if deleted_count > 0:
                if data["proxies"]:
                    data["cursor"] = data.get("cursor", 0) % len(data["proxies"])
                else:
                    data["cursor"] = 0
                self._save_raw(data)

            return deleted_count

    delete_dead = delete_dead_proxies

    def get_proxies(self, health: Optional[str] = None, usage: Optional[str] = None) -> List[Dict[str, Any]]:
        """Melihat daftar proxy dengan filter opsional."""
        with self._lock:
            data = self._load_raw()
            res = data["proxies"]
            if health:
                res = [p for p in res if p.get("health") == health.upper()]
            if usage:
                res = [p for p in res if p.get("usage") == usage.upper()]
            return [dict(p) for p in res]

    def get_stats(self) -> Dict[str, Any]:
        """Melihat ringkasan statistik kesehatan dan alokasi proxy."""
        with self._lock:
            data = self._load_raw()
            proxies = data["proxies"]
            stats = {
                "total": len(proxies),
                "cursor": data.get("cursor", 0),
                "alive": sum(1 for p in proxies if p.get("health") == HEALTH_ALIVE),
                "dead": sum(1 for p in proxies if p.get("health") == HEALTH_DEAD),
                "unknown": sum(1 for p in proxies if p.get("health") == HEALTH_UNKNOWN),
                "cooldown": sum(1 for p in proxies if p.get("health") == HEALTH_COOLDOWN),
                "idle": sum(1 for p in proxies if p.get("usage") == USAGE_IDLE),
                "in_use": sum(1 for p in proxies if p.get("usage") == USAGE_IN_USE),
            }
            return stats

    # =========================================================================
    # 2. VALIDASI PROXY
    # =========================================================================

    def _test_proxy_network(self, proxy_url: str) -> Dict[str, Any]:
        """Pengecekan jaringan HTTP langsung via proxy."""
        proxies = {"http": proxy_url, "https": proxy_url}
        start = time.time()
        try:
            resp = requests.get(self.check_url, proxies=proxies, timeout=self.timeout)
            latency = round((time.time() - start) * 1000, 2)
            if resp.status_code == 200:
                ip = resp.json().get("ip", "OK")
                return {"success": True, "ip": ip, "latency_ms": latency, "error": None}
            else:
                return {"success": False, "ip": None, "latency_ms": latency, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            err_msg = type(e).__name__ + (f": {str(e)}" if str(e) else "")
            return {"success": False, "ip": None, "latency_ms": None, "error": err_msg}

    def validate_proxy(self, identifier: str, force: bool = False) -> Dict[str, Any]:
        """
        Validasi apakah sebuah proxy benar-benar hidup.
        Jika hasil validasi sebelumnya masih berlaku (< CACHE_VALIDITY_SECONDS), skip pengujian jaringan.
        """
        with self._lock:
            data = self._load_raw()
            proxy = None
            for p in data["proxies"]:
                if p.get("id") == identifier or p.get("proxy_url") == identifier:
                    proxy = p
                    break

            if not proxy:
                raise ValueError(f"Proxy tidak ditemukan: {identifier}")

            # Jika sudah ALIVE dan belum expired, serta tidak dipaksa re-test
            now = time.time()
            if not force and proxy.get("health") == HEALTH_ALIVE:
                last_chk = proxy.get("last_checked")
                if last_chk and (now - last_chk) < CACHE_VALIDITY_SECONDS:
                    return dict(proxy)

            proxy_url = proxy.get("proxy_url")
            if not proxy_url:
                proxy["health"] = HEALTH_DEAD
                proxy["last_error"] = "No proxy_url provided"
                self._save_raw(data)
                return dict(proxy)

        # Tes jaringan di luar lock utama agar tidak memblok pemanggil lain terlalu lama
        test_res = self._test_proxy_network(proxy_url)

        with self._lock:
            # Muat ulang untuk sinkronisasi state
            data = self._load_raw()
            for p in data["proxies"]:
                if p.get("id") == proxy.get("id"):
                    p["last_checked"] = time.time()
                    if test_res["success"]:
                        p["health"] = HEALTH_ALIVE
                        p["ip_detected"] = test_res["ip"]
                        p["latency_ms"] = test_res["latency_ms"]
                        p["last_error"] = None
                        p["fail_count"] = 0
                    else:
                        p["health"] = HEALTH_DEAD
                        p["last_error"] = test_res["error"]
                    self._save_raw(data)
                    return dict(p)

            return dict(proxy)

    def revalidate_dead(self) -> Dict[str, int]:
        """
        Fungsi untuk meminta pengecekan ulang terhadap semua proxy yang sebelumnya DEAD.
        Mengembalikan jumlah proxy yang berhasil pulih (alive) dan yang tetap dead.
        """
        with self._lock:
            data = self._load_raw()
            dead_ids = [p["id"] for p in data["proxies"] if p.get("health") == HEALTH_DEAD]

        restored = 0
        still_dead = 0
        for pid in dead_ids:
            res = self.validate_proxy(pid, force=True)
            if res.get("health") == HEALTH_ALIVE:
                restored += 1
            else:
                still_dead += 1

        return {"restored": restored, "still_dead": still_dead, "total_tested": len(dead_ids)}

    def validate_all(self, force: bool = False, max_workers: int = 30) -> Dict[str, int]:
        """Validasi semua proxy dalam pool secara paralel."""
        with self._lock:
            data = self._load_raw()
            proxies_to_test = [
                {
                    "id": p.get("id"),
                    "proxy_url": p.get("proxy_url"),
                    "health": p.get("health"),
                    "last_checked": p.get("last_checked"),
                }
                for p in data.get("proxies", [])
            ]

        now = time.time()
        to_test = []
        cached_alive = 0
        for item in proxies_to_test:
            if not force and item.get("health") == HEALTH_ALIVE:
                last_chk = item.get("last_checked")
                if last_chk and (now - last_chk) < CACHE_VALIDITY_SECONDS:
                    cached_alive += 1
                    continue
            to_test.append(item)

        results = {}
        if to_test:
            def _test_one(it):
                pid = it["id"]
                url = it.get("proxy_url")
                if not url:
                    return pid, {"success": False, "error": "No proxy_url"}
                return pid, self._test_proxy_network(url)

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_test_one, it) for it in to_test]
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        pid, res = fut.result()
                        results[pid] = res
                    except Exception as e:
                        pass

        alive_count = cached_alive
        dead_count = 0
        with self._lock:
            data = self._load_raw()
            for p in data.get("proxies", []):
                pid = p.get("id")
                if pid in results:
                    test_res = results[pid]
                    p["last_checked"] = time.time()
                    if test_res.get("success"):
                        p["health"] = HEALTH_ALIVE
                        p["ip_detected"] = test_res.get("ip")
                        p["latency_ms"] = test_res.get("latency_ms")
                        p["last_error"] = None
                        p["fail_count"] = 0
                        alive_count += 1
                    else:
                        p["health"] = HEALTH_DEAD
                        p["last_error"] = test_res.get("error")
                        dead_count += 1
                elif p.get("health") == HEALTH_ALIVE:
                    pass
                elif p.get("health") == HEALTH_DEAD:
                    dead_count += 1

            self._save_raw(data)

        return {"alive": alive_count, "dead": dead_count, "total": len(data.get("proxies", []))}

    def test_and_delete_dead(self, force: bool = True, max_workers: int = 30) -> Dict[str, Any]:
        """Memvalidasi seluruh proxy secara paralel dan langsung menghapus yang berstatus DEAD."""
        val_res = self.validate_all(force=force, max_workers=max_workers)
        deleted = self.delete_dead_proxies()
        stats = self.get_stats()
        return {
            "tested_total": val_res["total"],
            "alive": val_res["alive"],
            "dead_found": val_res["dead"],
            "deleted_count": deleted,
            "remaining_total": stats["total"],
        }

    # =========================================================================
    # 3. ROTASI BERKELANJUTAN & ACQUIRE / RELEASE
    # =========================================================================

    def acquire_proxy(
        self,
        caller_id: Optional[str] = None,
        exclusive: bool = True,
        verify_alive: bool = False,
        target: Optional[str] = None,
        max_uses_per_day: int = 2,
        cooldown_seconds: float = 6 * 3600,
        window_seconds: float = 24 * 3600,
        auto_record: bool = False,
        channel: str = CHANNEL_AUTOMATION,
        strict_channel: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Mengambil proxy sehat berikutnya dengan rotasi berkelanjutan (cursor persisten).
        - Dimulai dari cursor terakhir yang tersimpan di proxies.json.
        - Proxy DEAD atau IN_USE dilewati.
        - Jika target ditentukan: proxy dicek terhadap kuota harian (max_uses_per_day)
          dan cooldown (cooldown_seconds). Otomatis di-reset jika sudah lewat window_seconds (24 jam).
        - Proxy UNKNOWN divalidasi langsung sebelum dialokasikan.
        - Jika verify_alive=True: status ALIVE di-recheck langsung (tidak langsung dipercaya).
        - Menandai proxy menjadi IN_USE dan memperbarui cursor rotasi secara persisten.
        - Tidak menyebabkan infinite loop jika tidak ada proxy tersedia.
        - channel="gologin" memakai state terpisah agar tidak mengunci/menghabiskan kuota automation.
        """
        with self._lock:
            # Safety: target "gologin" selalu berarti channel GoLogin.
            if channel == CHANNEL_AUTOMATION and target == CHANNEL_GOLOGIN:
                channel = CHANNEL_GOLOGIN
            lease_token = caller_id or f"lease_{uuid.uuid4().hex[:8]}"
            keys = self._channel_keys(channel)

            # 0. Prioritas Distributed RPC Supabase (Bebas Race Condition Antar Node)
            if self.supabase_enabled:
                sb_caller = f"{self.node_id}:{lease_token}" if not str(lease_token).startswith(f"{self.node_id}:") else lease_token
                for _attempt in range(5 if verify_alive else 1):
                    sb_proxy = self._acquire_proxy_supabase(
                        caller_id=sb_caller,
                        target=target,
                        max_uses_per_day=max_uses_per_day,
                        cooldown_seconds=cooldown_seconds,
                        window_seconds=window_seconds,
                        channel=channel,
                    )
                    if sb_proxy is None:
                        break
                    if verify_alive:
                        test_res = self._test_proxy_network(sb_proxy["proxy_url"])
                        if not test_res["success"]:
                            self.report_failure(sb_proxy, error_message=test_res["error"], is_proxy_error=True, channel=channel)
                            self.release_proxy(sb_proxy, caller_id=sb_caller, channel=channel)
                            continue
                        sb_proxy["ip_detected"] = test_res.get("ip")
                        sb_proxy["latency_ms"] = test_res.get("latency_ms")
                    return sb_proxy
                if self.supabase_rpc_available:
                    return None

            data = self._load_raw()
            proxies = data.get("proxies", [])
            total = len(proxies)
            if total == 0:
                return None

            cursor = data.get("cursor", 0) % total
            # Dua putaran bertingkat (Two-Tier Priority Queue):
            # Putaran 1 (require_fresh=True): Wajib cari proxy yang count == 0 (Fresh / belum pernah dipakai)
            # Putaran 2 (require_fresh=False): Jika stok fresh 0/2 habis total, baru ambil yang sekunder (1/2, lolos cooldown)
            passes = [True, False] if target else [False]

            for require_fresh in passes:
                # Loop maksimal 1 putaran penuh dari posisi cursor
                for offset in range(total):
                    idx = (cursor + offset) % total
                    candidate = proxies[idx]

                    # 1. Lewati jika sedang digunakan (jika exclusive)
                    if exclusive and candidate.get(keys["usage"]) == USAGE_IN_USE:
                        continue

                    # 2. Lewati jika DEAD
                    if candidate.get(keys["health"]) == HEALTH_DEAD:
                        continue

                    # 3. Cek modular target usage jika target ditentukan
                    if target:
                        t_usage = candidate.setdefault(keys["target_usage"], {})
                        if not isinstance(t_usage, dict):
                            t_usage = {}
                            candidate[keys["target_usage"]] = t_usage
                        t_data = t_usage.get(target)
                        if t_data and isinstance(t_data, dict):
                            count = int(t_data.get("count", 0) or 0)
                            last_used = float(t_data.get("last_used") or 0)
                            now = time.time()

                            # 3a. Auto-reset jika sudah lewat 24 jam sejak pemakaian terakhir -> kembali jadi Fresh (0/2)
                            if last_used > 0 and (now - last_used) >= window_seconds:
                                t_data["count"] = 0
                                t_data["history"] = []
                                count = 0

                            # 3b. PRIORITAS FRESH: Jika putaran 1, lewati jika sudah pernah dipakai (count > 0)
                            if require_fresh and count > 0:
                                continue

                            # 3c. Lewati jika kuota pemakaian per hari sudah habis
                            if count >= max_uses_per_day:
                                continue

                            # 3d. Lewati jika masih dalam masa cooldown antar pemakaian (misal jeda 6 jam)
                            if count > 0 and (now - last_used) < cooldown_seconds:
                                continue
                        else:
                            # Belum pernah ada data pemakaian untuk target ini -> otomatis count = 0 (Fresh)
                            count = 0

                    # 4. Jika COOLDOWN kesehatan jaringan, cek apakah sudah selesai cooldownnya
                    if candidate.get(keys["health"]) == HEALTH_COOLDOWN:
                        last_chk = candidate.get(keys["last_checked"], 0) or 0
                        if (time.time() - last_chk) < 60:  # 60 detik masa pendinginan
                            continue
                        # Selesai cooldown, kembalikan ke ALIVE untuk dicoba
                        candidate[keys["health"]] = HEALTH_ALIVE

                    # 5. Jika UNKNOWN, harus divalidasi terlebih dahulu
                    if candidate.get(keys["health"]) == HEALTH_UNKNOWN:
                        # Validasi
                        proxy_url = candidate.get("proxy_url")
                        if not proxy_url:
                            candidate[keys["health"]] = HEALTH_DEAD
                            continue

                        # Lepas lock sementara untuk network call
                        test_res = self._test_proxy_network(proxy_url)
                        candidate[keys["last_checked"]] = time.time()
                        if test_res["success"]:
                            candidate[keys["health"]] = HEALTH_ALIVE
                            candidate[keys["ip_detected"]] = test_res["ip"]
                            candidate[keys["latency_ms"]] = test_res["latency_ms"]
                            candidate[keys["fail_count"]] = 0
                            candidate[keys["last_error"]] = None
                        else:
                            candidate[keys["health"]] = HEALTH_DEAD
                            candidate[keys["last_error"]] = test_res["error"]
                            # Lanjutkan rotasi mencari yang lain
                            continue

                    # 6. Jika ALIVE dan memenuhi syarat, alokasikan!
                    if candidate.get(keys["health"]) == HEALTH_ALIVE:
                        # Jika verify_alive=True, re-verifikasi koneksi proxy di jaringan langsung!
                        if verify_alive:
                            proxy_url = candidate.get("proxy_url")
                            if not proxy_url:
                                candidate[keys["health"]] = HEALTH_DEAD
                                continue

                            test_res = self._test_proxy_network(proxy_url)
                            candidate[keys["last_checked"]] = time.time()
                            if test_res["success"]:
                                candidate[keys["health"]] = HEALTH_ALIVE
                                candidate[keys["ip_detected"]] = test_res["ip"]
                                candidate[keys["latency_ms"]] = test_res["latency_ms"]
                                candidate[keys["fail_count"]] = 0
                                candidate[keys["last_error"]] = None
                            else:
                                candidate[keys["health"]] = HEALTH_DEAD
                                candidate[keys["last_error"]] = test_res["error"]
                                # Proxy mati terkonfirmasi, lewati dan cari kandidat berikutnya
                                continue

                        target_info = None
                        if target:
                            t_usage = candidate.setdefault(keys["target_usage"], {})
                            if not isinstance(t_usage, dict):
                                t_usage = {}
                                candidate[keys["target_usage"]] = t_usage
                            t_data = t_usage.setdefault(target, {"count": 0, "last_used": None, "history": []})
                            now = time.time()
                            last = float(t_data.get("last_used") or 0)
                            if last > 0 and (now - last) >= window_seconds:
                                t_data["count"] = 0
                                t_data["history"] = []

                            if auto_record:
                                t_data["count"] = int(t_data.get("count", 0) or 0) + 1
                                t_data["last_used"] = now
                                hist = t_data.setdefault("history", [])
                                hist.append(now)
                                if len(hist) > 50:
                                    t_data["history"] = hist[-50:]

                            target_info = {
                                "target": target,
                                "count": int(t_data.get("count", 0) or 0),
                                "max_uses": max_uses_per_day,
                                "last_used": t_data.get("last_used"),
                                "cooldown_seconds": cooldown_seconds,
                            }

                        if exclusive:
                            candidate[keys["usage"]] = USAGE_IN_USE
                            candidate[keys["leased_by"]] = lease_token
                            candidate[keys["lease_time"]] = time.time()

                        # Simpan cursor berikutnya (setelah kandidat ini)
                        data["cursor"] = (idx + 1) % total
                        self._save_raw(data)

                        allocated = dict(candidate)
                        allocated["lease_token"] = lease_token
                        allocated["channel"] = channel
                        if target_info:
                            allocated["target_info"] = target_info
                        return allocated

            # Jika sudah 1 putaran tidak ada proxy yang bisa dipakai:
            # Tetap simpan cursor agar posisi tidak tersendat di index mati
            data["cursor"] = (cursor + 1) % total
            self._save_raw(data)
            return None

    def reset_usage_to_idle(self, caller_id: Optional[str] = None, channel: str = CHANNEL_AUTOMATION) -> int:
        """
        Membersihkan status IN_USE menjadi IDLE hanya untuk proxy yang disewa oleh node ini.
        Proxy milik VPS/Colab lain TIDAK AKAN DIGANGGU.
        Gunakan caller_id='__all__' hanya untuk maintenance reset global seluruh proxy.
        """
        keys = self._channel_keys(channel)
        usage_col = "usage_gologin" if channel == CHANNEL_GOLOGIN else "usage"
        leased_col = "leased_by_gologin" if channel == CHANNEL_GOLOGIN else "leased_by"
        lease_exp_col = "lease_expires_at_gologin" if channel == CHANNEL_GOLOGIN else "lease_expires_at"

        # 1. Bersihkan di Supabase via REST PATCH ter-filter
        if self.supabase_enabled:
            endpoint = f"{self.supabase_url}/rest/v1/{self.supabase_table}"
            if caller_id == "__all__":
                endpoint += f"?{usage_col}=eq.IN_USE"
            else:
                target_caller = caller_id or self.node_id
                endpoint += f"?{leased_col}=ilike.{target_caller}*"

            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Accept-Profile": self.supabase_schema,
                "Content-Profile": self.supabase_schema,
                "Content-Type": "application/json",
            }
            patch_data = {
                usage_col: "IDLE",
                leased_col: None,
                lease_exp_col: None,
            }
            try:
                requests.patch(endpoint, headers=headers, json=patch_data, timeout=6)
            except Exception:
                pass

        # 2. Bersihkan di file lokal
        with self._lock:
            data = self._load_raw()
            cleaned = 0
            for p in data.get("proxies", []):
                p_leased = str(p.get(keys["leased_by"]) or "")
                if caller_id == "__all__":
                    matches_caller = True
                elif caller_id:
                    matches_caller = p_leased.startswith(caller_id)
                elif self.supabase_enabled:
                    matches_caller = (not p_leased) or p_leased.startswith(self.node_id)
                else:
                    matches_caller = True
                if matches_caller and (p.get(keys["usage"]) == USAGE_IN_USE or p.get(keys["leased_by"]) is not None):
                    p[keys["usage"]] = USAGE_IDLE
                    p[keys["leased_by"]] = None
                    p[keys["lease_time"]] = None
                    cleaned += 1
            if cleaned > 0:
                self._save_raw(data)
            return cleaned

    def reset_cursor(self, to_index: int = 0) -> int:
        """
        Mereset posisi kursor rotasi (default ke index 0).
        Dipanggil ketika sebuah modul baru pertama kali berjalan.
        """
        with self._lock:
            data = self._load_raw()
            total = len(data.get("proxies", []))
            valid_cursor = to_index % total if total > 0 else 0
            data["cursor"] = valid_cursor
            self._save_raw(data)
            return valid_cursor

    def release_proxy(self, identifier: str, caller_id: Optional[str] = None, channel: str = CHANNEL_AUTOMATION, strict_channel: bool = False) -> bool:
        """
        Melepaskan alokasi proxy agar kembali IDLE.
        - Jika proxy DEAD, tetap DEAD (tidak otomatis jadi ALIVE).
        - Pemanggilan release aman dan tidak membatalkan alokasi milik caller lain.
        - channel="gologin" hanya melepas lease GoLogin, tidak menyentuh lease automation.
        """
        channel = self._resolve_channel(identifier, channel)
        keys = self._channel_keys(channel)
        is_gologin = channel == CHANNEL_GOLOGIN
        supabase_ok = False
        # Supabase Distributed Release
        if self.supabase_enabled:
            sb_id = None
            if isinstance(identifier, dict):
                sb_id = identifier.get("supabase_id") or identifier.get("id")
            elif isinstance(identifier, int):
                sb_id = identifier
            if sb_id and isinstance(sb_id, int):
                sb_caller = f"{self.node_id}:{caller_id}" if caller_id and not str(caller_id).startswith(f"{self.node_id}:") else caller_id
                fn_name = "release_proxy_gologin" if is_gologin else "release_proxy"
                _, status = self._supabase_rpc(fn_name, {"p_proxy_id": sb_id, "p_caller_id": sb_caller})
                if is_gologin and status == 404:
                    print(
                        "RPC release_proxy_gologin tidak ada; lease GoLogin tidak dilepas "
                        "ke kolom automation.",
                        flush=True,
                    )
                if status in (200, 201, 204):
                    supabase_ok = True
        if isinstance(identifier, dict):
            identifier = identifier.get("id") or identifier.get("proxy_url") or ""
        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])

            for p in proxies:
                matches_id = (p.get("id") == identifier or p.get("proxy_url") == identifier)
                matches_token = (p.get(keys["leased_by"]) == identifier)

                if matches_id or matches_token:
                    leased_by = p.get(keys["leased_by"])
                    if caller_id and leased_by and leased_by not in (caller_id, f"{self.node_id}:{caller_id}"):
                        return False  # Dimiliki oleh caller lain

                    p[keys["usage"]] = USAGE_IDLE
                    p[keys["leased_by"]] = None
                    p[keys["lease_time"]] = None
                    self._save_raw(data)
                    return True

            return supabase_ok

    # =========================================================================
    # 3b. MODULAR TARGET USAGE TRACKER (ADSTERRA, YOUTUBE, DLL)
    # =========================================================================

    def record_target_usage(
        self,
        identifier: str,
        target: str,
        window_seconds: float = 24 * 3600,
        channel: str = CHANNEL_AUTOMATION,
        strict_channel: bool = False,
    ) -> bool:
        """
        Mencatat pemakaian proxy untuk target tertentu (misal: 'adsterra', 'youtube').
        Menambah count, memperbarui last_used, dan menyimpan riwayat epoch.
        Otomatis me-reset count jika pemakaian terakhir sudah melebihi window 24 jam.
        channel="gologin" menulis ke target_usage_gologin & health_gologin.
        """
        channel = self._resolve_channel(identifier, channel)
        keys = self._channel_keys(channel)
        is_gologin = channel == CHANNEL_GOLOGIN
        # Supabase Distributed Target Hit Record
        if self.supabase_enabled:
            sb_id = None
            if isinstance(identifier, dict):
                sb_id = identifier.get("supabase_id") or identifier.get("id")
            elif isinstance(identifier, int):
                sb_id = identifier
            if sb_id and isinstance(sb_id, int):
                payload = {
                    "p_proxy_id": sb_id,
                    "p_target": target,
                    "p_window_seconds": int(window_seconds),
                }
                fn_name = "record_target_hit_gologin" if is_gologin else "record_target_hit"
                _, status = self._supabase_rpc(fn_name, payload)
                if is_gologin and status == 404:
                    print(
                        "RPC record_target_hit_gologin tidak ada; hit GoLogin tidak "
                        "dicatat ke kolom automation.",
                        flush=True,
                    )
        identifier_key = identifier
        if isinstance(identifier, dict):
            identifier_key = (
                identifier.get("id")
                or identifier.get("proxy_url")
                or identifier.get(keys["leased_by"])
                or ""
            )

        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])
            for p in proxies:
                matches_id = (p.get("id") == identifier_key or p.get("proxy_url") == identifier_key)
                matches_token = (p.get(keys["leased_by"]) == identifier_key)
                if matches_id or matches_token:
                    t_usage = p.setdefault(keys["target_usage"], {})
                    if not isinstance(t_usage, dict):
                        t_usage = {}
                        p[keys["target_usage"]] = t_usage
                    t_data = t_usage.setdefault(target, {"count": 0, "last_used": None, "history": []})
                    now = time.time()
                    last = float(t_data.get("last_used") or 0)
                    if last > 0 and (now - last) >= window_seconds:
                        t_data["count"] = 0
                        t_data["history"] = []

                    t_data["count"] = int(t_data.get("count", 0) or 0) + 1
                    t_data["last_used"] = now
                    hist = t_data.setdefault("history", [])
                    hist.append(now)
                    if len(hist) > 50:
                        t_data["history"] = hist[-50:]
                    # Reset kegagalan dan kembalikan ke ALIVE jika berhasil koneksi
                    p[keys["fail_count"]] = 0
                    if p.get(keys["health"]) != HEALTH_DEAD:
                        p[keys["health"]] = HEALTH_ALIVE
                    self._save_raw(data)
                    return True
            return False

    def get_target_usage(
        self,
        identifier: str,
        target: str,
        max_uses_per_day: int = 2,
        cooldown_seconds: float = 6 * 3600,
        window_seconds: float = 24 * 3600,
    ) -> Dict[str, Any]:
        """
        Mengambil status pemakaian proxy untuk target tertentu beserta sisa cooldown.
        """
        with self._lock:
            data = self._load_raw()
            for p in data.get("proxies", []):
                if p.get("id") == identifier or p.get("proxy_url") == identifier or p.get("leased_by") == identifier:
                    t_usage = p.get("target_usage") or {}
                    t_data = t_usage.get(target) or {}
                    count = int(t_data.get("count", 0) or 0)
                    last_used = float(t_data.get("last_used") or 0)
                    now = time.time()
                    if last_used > 0 and (now - last_used) >= window_seconds:
                        count = 0
                    cooldown_remaining = max(0.0, cooldown_seconds - (now - last_used)) if (count > 0 and last_used > 0) else 0.0
                    return {
                        "id": p.get("id"),
                        "target": target,
                        "count": count,
                        "max_uses": max_uses_per_day,
                        "last_used": last_used if last_used > 0 else None,
                        "cooldown_remaining": round(cooldown_remaining, 1),
                        "can_use": count < max_uses_per_day and cooldown_remaining <= 0,
                    }
            return {"target": target, "count": 0, "can_use": False, "status": "NOT_FOUND"}

    def get_target_usage_summary(
        self,
        proxy_or_id: Union[str, Dict[str, Any]],
        target: str = "monetag",
        max_uses_per_day: int = 2,
        cooldown_seconds: float = 6 * 3600,
    ) -> Dict[str, Any]:
        """Format ringkasan pemakaian IP per target (misal: 'Hit 1/2 (Baru)' atau 'Hit 2/2 (Sesi 2 - Lolos Cooldown 6 Jam)')."""
        if isinstance(proxy_or_id, dict) and "target_usage" in proxy_or_id and isinstance(proxy_or_id["target_usage"], dict):
            t_data = proxy_or_id["target_usage"].get(target) or {}
            count = int(t_data.get("count", 0) or 0)
        else:
            p_id = proxy_or_id.get("id") if isinstance(proxy_or_id, dict) else str(proxy_or_id)
            info = self.get_target_usage(
                p_id,
                target=target,
                max_uses_per_day=max_uses_per_day,
                cooldown_seconds=cooldown_seconds,
            )
            count = int(info.get("count", 0) or 0)

        curr = min(count + 1, max_uses_per_day)
        if count == 0:
            summary = f"Hit {curr}/{max_uses_per_day} (Baru)"
        elif count == 1:
            summary = f"Hit {curr}/{max_uses_per_day} (Sesi 2 - Lolos Cooldown 6 Jam)"
        else:
            summary = f"Hit {count}/{max_uses_per_day} (Habis Hari Ini)"

        return {
            "current_hit": curr,
            "count": count,
            "max_uses": max_uses_per_day,
            "summary_text": summary,
            "can_use": count < max_uses_per_day,
        }

    def record_target_hit(
        self,
        proxy_or_id: Union[str, Dict[str, Any]],
        target: str = "monetag",
        window_seconds: float = 24 * 3600,
        channel: str = CHANNEL_AUTOMATION,
        strict_channel: bool = False,
    ) -> bool:
        """Alias praktis untuk record_target_usage yang menerima dict proxy atau ID string."""
        return self.record_target_usage(
            identifier=proxy_or_id,
            target=target,
            window_seconds=window_seconds,
            channel=channel,
            strict_channel=strict_channel,
        )

    def get_proxy_info(self, proxy: Dict[str, Any]) -> Dict[str, Any]:
        """Mengekstrak informasi dasar IP, negara, dan id dari dictionary proxy."""
        ip = proxy.get("ip_detected") or proxy.get("host", "?")
        country = proxy.get("country", "?")
        return {"ip": ip, "country": country, "id": proxy.get("id")}

    def reset_target_usage(self, target: Optional[str] = None) -> int:
        """
        Mereset status target_usage (jika target=None, reset seluruh target).
        """
        with self._lock:
            data = self._load_raw()
            reset_count = 0
            for p in data.get("proxies", []):
                t_usage = p.get("target_usage")
                if isinstance(t_usage, dict):
                    if target:
                        if target in t_usage:
                            del t_usage[target]
                            reset_count += 1
                    else:
                        if t_usage:
                            t_usage.clear()
                            reset_count += 1
            if reset_count > 0:
                self._save_raw(data)
            return reset_count

    def get_target_stats(
        self,
        target: str,
        max_uses_per_day: int = 2,
        cooldown_seconds: float = 6 * 3600,
        window_seconds: float = 24 * 3600,
    ) -> Dict[str, Any]:
        """
        Melihat statistik ketersediaan proxy pool khusus untuk target tertentu.
        """
        with self._lock:
            data = self._load_raw()
            now = time.time()
            fresh = 0
            in_cooldown = 0
            ready_secondary = 0
            exhausted = 0
            alive_total = 0

            for p in data.get("proxies", []):
                if p.get("health") != HEALTH_ALIVE:
                    continue
                alive_total += 1
                t_usage = p.get("target_usage") or {}
                t_data = t_usage.get(target) or {}
                count = int(t_data.get("count", 0) or 0)
                last_used = float(t_data.get("last_used") or 0)

                if last_used > 0 and (now - last_used) >= window_seconds:
                    count = 0

                if count == 0:
                    fresh += 1
                elif count >= max_uses_per_day:
                    exhausted += 1
                else:
                    elapsed = now - last_used if last_used > 0 else 0
                    if elapsed < cooldown_seconds:
                        in_cooldown += 1
                    else:
                        ready_secondary += 1

            return {
                "target": target,
                "alive_total": alive_total,
                "fresh": fresh,
                "ready_secondary": ready_secondary,
                "in_cooldown": in_cooldown,
                "exhausted": exhausted,
                "available_now": fresh + ready_secondary,
            }

    # =========================================================================
    # 4. PENANGANAN KEGAGALAN SAAT DIGUNAKAN
    # =========================================================================

    def report_failure(self, identifier: Union[str, Dict[str, Any]], error_message: Optional[str] = None, is_proxy_error: bool = False, channel: str = CHANNEL_AUTOMATION, strict_channel: bool = False) -> Dict[str, Any]:
        """
        Melaporkan kegagalan penggunaan proxy saat mengakses web target.
        Aturan:
        1. Jika error bertipe TIMEOUT (page navigation timeout / slow response / read timeout):
           -> Status diubah ke COOLDOWN (agar diistirahatkan sementara, tidak langsung dimatikan).
        2. Jika koneksi TIDAK TERJANGKAU (connection refused, host unreachable, reset, tunnel/proxy dead, dns error):
           -> Jika sudah 3x mencoba (fail_count >= 3): status diubah menjadi DEAD (mati total).
           -> Jika belum mencapai 3x: status diberi COOLDOWN untuk dicoba kembali.
        3. Error fatal level driver/proxy test (test_proxy_network gagal):
           -> Langsung ditandai DEAD.
        channel="gologin" hanya mengubah health_gologin/fail_count_gologin, bukan automation.
        Error karena browser/page ditutup (stop script) diabaikan total: health TIDAK berubah.
        """
        channel = self._resolve_channel(identifier, channel)
        if self._is_shutdown_error(error_message):
            return {"status": "IGNORED_SHUTDOWN"}
        keys = self._channel_keys(channel)
        is_gologin = channel == CHANNEL_GOLOGIN
        # Supabase Distributed Failure / Cooldown Report
        if self.supabase_enabled:
            sb_id = None
            if isinstance(identifier, dict):
                sb_id = identifier.get("supabase_id") or identifier.get("id")
            elif isinstance(identifier, int):
                sb_id = identifier
            if sb_id and isinstance(sb_id, int):
                payload = {
                    "p_proxy_id": sb_id,
                    "p_error": str(error_message or "Error")[:200],
                    "p_is_fatal": is_proxy_error,
                }
                fn_name = "report_failure_gologin" if is_gologin else "report_failure"
                _, status = self._supabase_rpc(fn_name, payload)
                if is_gologin and status == 404:
                    print(
                        "RPC report_failure_gologin tidak ada; kegagalan GoLogin tidak "
                        "dicatat ke kolom automation.",
                        flush=True,
                    )

        if isinstance(identifier, dict):
            identifier = identifier.get("id") or identifier.get("proxy_url") or identifier.get(keys["leased_by"]) or ""
        proxy_id = None
        proxy_url = None
        fail_count = 0

        with self._lock:
            data = self._load_raw()
            proxy = None
            for p in data["proxies"]:
                if p.get("id") == identifier or p.get("proxy_url") == identifier or p.get(keys["leased_by"]) == identifier:
                    proxy = p
                    break

            if not proxy:
                return {"status": "NOT_FOUND"}

            err_str = str(error_message or "")
            proxy[keys["last_error"]] = err_str
            proxy[keys["last_checked"]] = time.time()
            proxy[keys["fail_count"]] = int(proxy.get(keys["fail_count"], 0) or 0) + 1
            fail_count = proxy[keys["fail_count"]]
            proxy_id = proxy.get("id")
            proxy_url = proxy.get("proxy_url")

            err_lower = err_str.lower()
            is_timeout = any(k.lower() in err_lower for k in TIMEOUT_ERRORS)
            is_unreachable = (
                is_proxy_error
                or any(k.lower() in err_lower for k in UNREACHABLE_ERRORS)
            )

            # 1. Jika murni Timeout (lambat/stalled load halaman): Berikan COOLDOWN
            if is_timeout and not is_unreachable:
                proxy[keys["health"]] = HEALTH_COOLDOWN
                self._save_raw(data)
                return dict(proxy)

            # 2. Jika koneksi tidak terjangkau / fatal network error:
            # Jika sudah 3 kali mencoba -> Dianggap MATI TOTAL (DEAD)
            if fail_count >= MAX_FAIL_THRESHOLD:
                proxy[keys["health"]] = HEALTH_DEAD
                proxy[keys["last_error"]] = f"DEAD (Koneksi tidak terjangkau {fail_count}x): {err_str[:120]}"
                self._save_raw(data)
                return dict(proxy)

            # 3. Jika belum mencapai 3x tapi diduga proxy error, lakukan verifikasi cepat:
            if is_unreachable and proxy_url:
                test_res = self._test_proxy_network(proxy_url)
                if not test_res["success"]:
                    proxy[keys["health"]] = HEALTH_DEAD
                    proxy[keys["last_error"]] = f"Dead confirmed: {test_res['error']}"
                else:
                    proxy[keys["health"]] = HEALTH_COOLDOWN
                    proxy[keys["latency_ms"]] = test_res.get("latency_ms")
            else:
                proxy[keys["health"]] = HEALTH_COOLDOWN

            self._save_raw(data)
            return dict(proxy)

        with self._lock:
            data = self._load_raw()
            for p in data["proxies"]:
                if p.get("id") == proxy_id:
                    return dict(p)
            return {"status": "NOT_FOUND"}

    def record_probe(
        self,
        identifier: Union[str, Dict[str, Any]],
        ip_detected: Optional[str] = None,
        latency_ms: Optional[float] = None,
        channel: str = CHANNEL_GOLOGIN,
        strict_channel: bool = False,
    ) -> bool:
        """Simpan hasil probe chain (exit IP + latency) ke kolom channel yang benar."""
        channel = self._resolve_channel(identifier, channel)
        keys = self._channel_keys(channel)
        is_gologin = channel == CHANNEL_GOLOGIN
        supabase_ok = False

        if self.supabase_enabled and is_gologin:
            sb_id = None
            if isinstance(identifier, dict):
                sb_id = identifier.get("supabase_id") or identifier.get("id")
            elif isinstance(identifier, int):
                sb_id = identifier
            if sb_id and isinstance(sb_id, int):
                payload = {
                    "p_proxy_id": sb_id,
                    "p_ip": ip_detected,
                    "p_latency_ms": latency_ms,
                }
                _, status = self._supabase_rpc("record_probe_gologin", payload)
                if status in (200, 201, 204):
                    supabase_ok = True
                elif status == 404:
                    print(
                        "RPC record_probe_gologin tidak ada. Jalankan "
                        "setup_supabase_chain_gologin.sql.",
                        flush=True,
                    )

        identifier_key = identifier
        if isinstance(identifier, dict):
            identifier_key = (
                identifier.get("id")
                or identifier.get("proxy_url")
                or identifier.get(keys["leased_by"])
                or ""
            )

        with self._lock:
            data = self._load_raw()
            for proxy in data.get("proxies", []):
                if (
                    proxy.get("id") == identifier_key
                    or proxy.get("proxy_url") == identifier_key
                    or proxy.get(keys["leased_by"]) == identifier_key
                ):
                    if ip_detected is not None:
                        proxy[keys["ip_detected"]] = ip_detected
                    if latency_ms is not None:
                        proxy[keys["latency_ms"]] = latency_ms
                    proxy[keys["last_checked"]] = time.time()
                    proxy[keys["cooldown_until"]] = None
                    if proxy.get(keys["health"]) != HEALTH_DEAD:
                        proxy[keys["health"]] = HEALTH_ALIVE
                        proxy[keys["fail_count"]] = 0
                        proxy[keys["last_error"]] = None
                    self._save_raw(data)
                    return True
        return supabase_ok

    def report_cooldown(
        self,
        identifier: Union[str, Dict[str, Any]],
        reason: str,
        cooldown_seconds: float = 900,
        channel: str = CHANNEL_GOLOGIN,
        strict_channel: bool = False,
    ) -> bool:
        """Tandai COOLDOWN dengan alasan jelas tanpa menambah fail_count."""
        channel = self._resolve_channel(identifier, channel)
        keys = self._channel_keys(channel)
        is_gologin = channel == CHANNEL_GOLOGIN
        supabase_ok = False

        if self.supabase_enabled and is_gologin:
            sb_id = None
            if isinstance(identifier, dict):
                sb_id = identifier.get("supabase_id") or identifier.get("id")
            elif isinstance(identifier, int):
                sb_id = identifier
            if sb_id and isinstance(sb_id, int):
                payload = {
                    "p_proxy_id": sb_id,
                    "p_reason": str(reason or "Cooldown")[:500],
                    "p_cooldown_seconds": int(cooldown_seconds),
                }
                _, status = self._supabase_rpc("mark_cooldown_gologin", payload)
                if status in (200, 201, 204):
                    supabase_ok = True
                elif status == 404:
                    print(
                        "RPC mark_cooldown_gologin tidak ada. Jalankan "
                        "setup_supabase_chain_gologin.sql.",
                        flush=True,
                    )

        identifier_key = identifier
        if isinstance(identifier, dict):
            identifier_key = (
                identifier.get("id")
                or identifier.get("proxy_url")
                or identifier.get(keys["leased_by"])
                or ""
            )

        with self._lock:
            data = self._load_raw()
            for proxy in data.get("proxies", []):
                if (
                    proxy.get("id") == identifier_key
                    or proxy.get("proxy_url") == identifier_key
                    or proxy.get(keys["leased_by"]) == identifier_key
                ):
                    if proxy.get(keys["health"]) != HEALTH_DEAD:
                        proxy[keys["health"]] = HEALTH_COOLDOWN
                    proxy[keys["last_error"]] = str(reason or "Cooldown")[:500]
                    proxy[keys["last_checked"]] = time.time()
                    proxy[keys["cooldown_until"]] = time.time() + float(cooldown_seconds)
                    self._save_raw(data)
                    return True
        return supabase_ok

    def report_dead(
        self,
        identifier: Union[str, Dict[str, Any]],
        reason: str,
        is_fatal: bool = False,
        force_dead: bool = False,
        cooldown_seconds: float = 900,
        channel: str = CHANNEL_GOLOGIN,
        strict_channel: bool = False,
    ) -> bool:
        """Hitung kegagalan hanya saat proxy benar-benar tidak bisa connect."""
        channel = self._resolve_channel(identifier, channel)
        keys = self._channel_keys(channel)
        is_gologin = channel == CHANNEL_GOLOGIN
        supabase_ok = False

        if self.supabase_enabled and is_gologin:
            sb_id = None
            if isinstance(identifier, dict):
                sb_id = identifier.get("supabase_id") or identifier.get("id")
            elif isinstance(identifier, int):
                sb_id = identifier
            if sb_id and isinstance(sb_id, int):
                payload = {
                    "p_proxy_id": sb_id,
                    "p_reason": str(reason or "Unreachable")[:500],
                    "p_fatal": bool(is_fatal or force_dead),
                    "p_cooldown_seconds": int(cooldown_seconds),
                }
                _, status = self._supabase_rpc("mark_dead_gologin", payload)
                if status in (200, 201, 204):
                    supabase_ok = True
                elif status == 404:
                    print(
                        "RPC mark_dead_gologin tidak ada. Jalankan "
                        "setup_supabase_chain_gologin.sql.",
                        flush=True,
                    )

        identifier_key = identifier
        if isinstance(identifier, dict):
            identifier_key = (
                identifier.get("id")
                or identifier.get("proxy_url")
                or identifier.get(keys["leased_by"])
                or ""
            )

        with self._lock:
            data = self._load_raw()
            for proxy in data.get("proxies", []):
                if (
                    proxy.get("id") == identifier_key
                    or proxy.get("proxy_url") == identifier_key
                    or proxy.get(keys["leased_by"]) == identifier_key
                ):
                    fail_count = int(proxy.get(keys["fail_count"], 0) or 0) + 1
                    proxy[keys["fail_count"]] = fail_count
                    if is_fatal or force_dead or fail_count >= MAX_FAIL_THRESHOLD:
                        proxy[keys["health"]] = HEALTH_DEAD
                        proxy[keys["cooldown_until"]] = None
                        suffix = " [DEAD]"
                    else:
                        proxy[keys["health"]] = HEALTH_COOLDOWN
                        proxy[keys["cooldown_until"]] = time.time() + float(cooldown_seconds)
                        suffix = f" [gagal {fail_count}/{MAX_FAIL_THRESHOLD}]"
                    proxy[keys["last_error"]] = f"{reason or 'Unreachable'}{suffix}"[:500]
                    proxy[keys["last_checked"]] = time.time()
                    self._save_raw(data)
                    return True
        return supabase_ok

    def sync_from_supabase(self, config_file: Optional[str] = None) -> int:
        """Mengambil data proxy dari database Supabase (REST API) dan menyimpannya ke proxies.json."""
        default_cfg = os.path.join(PROJECT_ROOT, "data", "supabase_config.json")
        cfg_path = config_file or default_cfg
        if not os.path.exists(cfg_path):
            alt_path = os.path.join(PROJECT_ROOT, "data", "telemetry_config.json")
            if os.path.exists(alt_path):
                cfg_path = alt_path

        if not os.path.exists(cfg_path):
            return 0

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return 0

        url = cfg.get("supabase_url", "https://supabase.riztama.my.id").rstrip("/")
        key = cfg.get("supabase_key", "")
        schema = cfg.get("schema", "proxxies")
        table = cfg.get("table", "proxy_list")

        if not url or not key:
            return 0

        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept-Profile": schema,
            "Content-Profile": schema,
        }

        try:
            records = []
            offset = 0
            limit = 1000
            while True:
                endpoint = f"{url}/rest/v1/{table}?select=*&limit={limit}&offset={offset}"
                resp = requests.get(endpoint, headers=headers, timeout=12)
                if resp.status_code != 200:
                    break
                chunk = resp.json()
                if not isinstance(chunk, list) or not chunk:
                    break
                records.extend(chunk)
                if len(chunk) < limit:
                    break
                offset += limit

            if not records:
                return 0

            with self._lock:
                data = self._load_raw()
                proxies = data.get("proxies", [])
                existing_map = {f"{p.get('host')}:{p.get('port')}:{p.get('username', '')}": idx for idx, p in enumerate(proxies)}

                added = 0
                for row in records:
                    host = row.get("host")
                    port = row.get("port")
                    if not host or not port:
                        continue
                    try:
                        port = int(port)
                    except ValueError:
                        continue

                    user = row.get("username") or ""
                    pwd = row.get("password") or ""
                    country = row.get("country") or "US"
                    conn_type = row.get("connection_type") or "residential"
                    health = str(row.get("health", HEALTH_ALIVE)).upper()

                    if user and pwd:
                        proxy_url = f"http://{user}:{pwd}@{host}:{port}"
                    else:
                        proxy_url = f"http://{host}:{port}"

                    item = {
                        "host": host,
                        "port": port,
                        "username": user,
                        "password": pwd,
                        "proxy_url": proxy_url,
                        "country": country,
                        "connection_type": conn_type,
                        "health": health,
                        "usage": USAGE_IDLE,
                        "target_usage": {},
                        "health_gologin": str(row.get("health_gologin", health)).upper(),
                        "usage_gologin": USAGE_IDLE,
                        "target_usage_gologin": {},
                    }
                    normalized = self._normalize_proxy(item, len(proxies))

                    key_id = f"{host}:{port}:{user}"
                    if key_id in existing_map:
                        existing_idx = existing_map[key_id]
                        proxies[existing_idx]["username"] = user
                        proxies[existing_idx]["password"] = pwd
                        proxies[existing_idx]["proxy_url"] = proxy_url
                        proxies[existing_idx]["country"] = country
                        proxies[existing_idx]["connection_type"] = conn_type
                        proxies[existing_idx]["health"] = health
                        proxies[existing_idx]["health_gologin"] = str(row.get("health_gologin", health)).upper()
                    else:
                        proxies.append(normalized)
                        existing_map[key_id] = len(proxies) - 1
                        added += 1

                data["proxies"] = proxies
                self._save_raw(data)
                return added
        except Exception:
            return 0

    def upload_to_supabase(self, proxy_list: List[Union[Dict[str, Any], str]], config_file: Optional[str] = None) -> int:
        """Mengupload daftar proxy ke tabel Supabase (REST API)."""
        default_cfg = os.path.join(PROJECT_ROOT, "data", "supabase_config.json")
        cfg_path = config_file or default_cfg
        if not os.path.exists(cfg_path):
            alt_path = os.path.join(PROJECT_ROOT, "data", "telemetry_config.json")
            if os.path.exists(alt_path):
                cfg_path = alt_path

        if not os.path.exists(cfg_path):
            return 0

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return 0

        url = cfg.get("supabase_url", "https://supabase.riztama.my.id").rstrip("/")
        key = cfg.get("supabase_key", "")
        schema = cfg.get("schema", "proxxies")
        table = cfg.get("table", "proxy_list")

        if not url or not key:
            return 0

        endpoint = f"{url}/rest/v1/{table}?on_conflict=host,port,username"
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept-Profile": schema,
            "Content-Profile": schema,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

        seen = set()
        payloads = []
        for p in proxy_list:
            parsed = self._parse_proxy_input(p)
            if not parsed:
                continue
            host = parsed.get("host")
            try:
                port = int(parsed.get("port"))
            except (ValueError, TypeError):
                continue
            username = parsed.get("username", "")
            key_tuple = (host, port, username)
            if key_tuple in seen:
                continue
            seen.add(key_tuple)

            payloads.append({
                "host": host,
                "port": port,
                "username": username,
                "password": parsed.get("password", ""),
                "country": parsed.get("country", "US"),
                "connection_type": parsed.get("connection_type", "residential"),
                "health": "ALIVE",
            })

        if not payloads:
            return 0

        batch_size = 100
        uploaded = 0
        for i in range(0, len(payloads), batch_size):
            chunk = payloads[i:i + batch_size]
            try:
                resp = requests.post(endpoint, headers=headers, json=chunk, timeout=15)
                if resp.status_code in (200, 201):
                    uploaded += len(chunk)
                else:
                    print(f"⚠️ Gagal upload batch ke Supabase: HTTP {resp.status_code} - {resp.text[:200]}")
            except Exception as e:
                print(f"⚠️ Error koneksi saat upload ke Supabase: {e}")

        return uploaded

# =============================================================================
# SINGLETON INSTANCE & CONVENIENCE FUNCTIONS
# =============================================================================

_default_manager: Optional[ProxyManager] = None
_manager_lock = threading.Lock()


def get_manager(filepath: str = DEFAULT_PROXY_FILE) -> ProxyManager:
    """Mendapatkan atau menginisialisasi singleton instance ProxyManager."""
    global _default_manager
    with _manager_lock:
        if _default_manager is None or _default_manager.filepath != os.path.abspath(filepath):
            _default_manager = ProxyManager(filepath=filepath)
        return _default_manager


# API functions yang dapat langsung dipanggil oleh modul lain:
def acquire_proxy(
    caller_id: Optional[str] = None,
    exclusive: bool = True,
    verify_alive: bool = False,
    target: Optional[str] = None,
    max_uses_per_day: int = 2,
    cooldown_seconds: float = 6 * 3600,
    window_seconds: float = 24 * 3600,
    auto_record: bool = False,
    channel: str = CHANNEL_AUTOMATION,
    strict_channel: bool = False,
) -> Optional[Dict[str, Any]]:
    """Mengambil proxy sehat berikutnya dengan continuous rotation dan target usage check."""
    return get_manager().acquire_proxy(
        caller_id=caller_id,
        exclusive=exclusive,
        verify_alive=verify_alive,
        target=target,
        max_uses_per_day=max_uses_per_day,
        cooldown_seconds=cooldown_seconds,
        window_seconds=window_seconds,
        auto_record=auto_record,
        channel=channel,
        strict_channel=strict_channel,
    )


def record_target_usage(identifier: str, target: str, window_seconds: float = 24 * 3600, channel: str = CHANNEL_AUTOMATION, strict_channel: bool = False) -> bool:
    """Mencatat pemakaian proxy untuk target tertentu."""
    return get_manager().record_target_usage(identifier=identifier, target=target, window_seconds=window_seconds, channel=channel, strict_channel=strict_channel)


def record_target_hit(identifier: str, target: str = "monetag", window_seconds: float = 24 * 3600, channel: str = CHANNEL_AUTOMATION, strict_channel: bool = False) -> bool:
    """Alias record_target_usage yang menerima dict proxy atau ID."""
    return get_manager().record_target_hit(proxy_or_id=identifier, target=target, window_seconds=window_seconds, channel=channel, strict_channel=strict_channel)


def get_target_usage(
    identifier: str,
    target: str,
    max_uses_per_day: int = 2,
    cooldown_seconds: float = 6 * 3600,
    window_seconds: float = 24 * 3600,
) -> Dict[str, Any]:
    """Melihat status pemakaian proxy untuk target tertentu."""
    return get_manager().get_target_usage(
        identifier=identifier,
        target=target,
        max_uses_per_day=max_uses_per_day,
        cooldown_seconds=cooldown_seconds,
        window_seconds=window_seconds,
    )


def reset_target_usage(target: Optional[str] = None) -> int:
    """Mereset status target_usage."""
    return get_manager().reset_target_usage(target=target)


def get_target_stats(
    target: str,
    max_uses_per_day: int = 2,
    cooldown_seconds: float = 6 * 3600,
    window_seconds: float = 24 * 3600,
) -> Dict[str, Any]:
    """Melihat statistik ketersediaan proxy khusus untuk target tertentu."""
    return get_manager().get_target_stats(
        target=target,
        max_uses_per_day=max_uses_per_day,
        cooldown_seconds=cooldown_seconds,
        window_seconds=window_seconds,
    )


def release_proxy(identifier: str, caller_id: Optional[str] = None, channel: str = CHANNEL_AUTOMATION, strict_channel: bool = False) -> bool:
    """Melepaskan proxy setelah selesai digunakan."""
    return get_manager().release_proxy(identifier=identifier, caller_id=caller_id, channel=channel, strict_channel=strict_channel)


def report_failure(identifier: str, error_message: Optional[str] = None, is_proxy_error: bool = False, channel: str = CHANNEL_AUTOMATION, strict_channel: bool = False) -> Dict[str, Any]:
    """Melaporkan error saat menggunakan proxy."""
    return get_manager().report_failure(identifier=identifier, error_message=error_message, is_proxy_error=is_proxy_error, channel=channel, strict_channel=strict_channel)


def record_probe(
    identifier: str,
    ip_detected: Optional[str] = None,
    latency_ms: Optional[float] = None,
    channel: str = CHANNEL_GOLOGIN,
    strict_channel: bool = False,
) -> bool:
    """Menyimpan exit IP + latency hasil probe chain."""
    return get_manager().record_probe(
        identifier=identifier,
        ip_detected=ip_detected,
        latency_ms=latency_ms,
        channel=channel,
        strict_channel=strict_channel,
    )


def report_cooldown(
    identifier: str,
    reason: str,
    cooldown_seconds: float = 900,
    channel: str = CHANNEL_GOLOGIN,
    strict_channel: bool = False,
) -> bool:
    """Menandai COOLDOWN dengan alasan jelas tanpa menambah fail_count."""
    return get_manager().report_cooldown(
        identifier=identifier,
        reason=reason,
        cooldown_seconds=cooldown_seconds,
        channel=channel,
        strict_channel=strict_channel,
    )


def report_dead(
    identifier: str,
    reason: str,
    is_fatal: bool = False,
    force_dead: bool = False,
    cooldown_seconds: float = 900,
    channel: str = CHANNEL_GOLOGIN,
    strict_channel: bool = False,
) -> bool:
    """Menghitung kegagalan hanya saat proxy benar-benar tidak bisa connect."""
    return get_manager().report_dead(
        identifier=identifier,
        reason=reason,
        is_fatal=is_fatal,
        force_dead=force_dead,
        cooldown_seconds=cooldown_seconds,
        channel=channel,
        strict_channel=strict_channel,
    )


def validate_proxy(identifier: str, force: bool = False) -> Dict[str, Any]:
    """Memvalidasi proxy tertentu."""
    return get_manager().validate_proxy(identifier=identifier, force=force)


def revalidate_dead() -> Dict[str, int]:
    """Meminta pengecekan ulang terhadap semua proxy yang berstatus DEAD."""
    return get_manager().revalidate_dead()


def validate_all(force: bool = False, max_workers: int = 30) -> Dict[str, int]:
    """Memvalidasi seluruh proxy dalam pool secara paralel."""
    return get_manager().validate_all(force=force, max_workers=max_workers)


def test_and_delete_dead(force: bool = True, max_workers: int = 30) -> Dict[str, Any]:
    """Memvalidasi seluruh proxy secara paralel dan langsung menghapus yang berstatus DEAD."""
    return get_manager().test_and_delete_dead(force=force, max_workers=max_workers)


def append_proxy(proxy_data: Union[Dict[str, Any], str]) -> Optional[Dict[str, Any]]:
    """Menambahkan/meng-append satu proxy ke proxies.json."""
    return get_manager().append_proxy(proxy_data)


def append_proxies(proxy_list: List[Union[Dict[str, Any], str]]) -> int:
    """Menambahkan/meng-append daftar proxy baru ke proxies.json."""
    return get_manager().append_proxies(proxy_list)

def upload_to_supabase(proxy_list: List[Union[Dict[str, Any], str]], config_file: Optional[str] = None) -> int:
    """Mengupload daftar proxy ke database Supabase (REST API)."""
    return get_manager().upload_to_supabase(proxy_list, config_file=config_file)


def get_proxy_by_index(index: int) -> Optional[Dict[str, Any]]:
    """Mengambil proxy berdasarkan indeks di proxies.json."""
    return get_manager().get_proxy_by_index(index)


def add_proxy(proxy_data: Union[Dict[str, Any], str]) -> Optional[Dict[str, Any]]:
    """Menambahkan proxy baru."""
    return get_manager().add_proxy(proxy_data)


def add_proxies(proxy_list: List[Union[Dict[str, Any], str]]) -> int:
    """Menambahkan daftar proxy baru."""
    return get_manager().add_proxies(proxy_list)


def remove_proxy(identifier: str) -> bool:
    """Menghapus proxy."""
    return get_manager().remove_proxy(identifier)


def delete_dead_proxies() -> int:
    """Menghapus seluruh proxy yang berstatus DEAD dari proxies.json."""
    return get_manager().delete_dead_proxies()


delete_dead = delete_dead_proxies


def get_proxies(health: Optional[str] = None, usage: Optional[str] = None) -> List[Dict[str, Any]]:
    """Melihat daftar proxy."""
    return get_manager().get_proxies(health=health, usage=usage)


def get_stats() -> Dict[str, Any]:
    """Melihat statistik proxy pool."""
    return get_manager().get_stats()


def reset_usage_to_idle(channel: str = CHANNEL_AUTOMATION) -> int:
    """Membersihkan seluruh status IN_USE menjadi IDLE."""
    return get_manager().reset_usage_to_idle(channel=channel)


def reset_cursor(to_index: int = 0) -> int:
    """Mereset posisi kursor rotasi proxy."""
    return get_manager().reset_cursor(to_index)



if __name__ == "__main__":
    import sys
    stats = get_stats()
    print("=" * 60)
    print("📊 STATUS PROXY MANAGEMENT (data/proxies.json)")
    print("=" * 60)
    print(f"Total Proxy     : {stats['total']}")
    print(f"Posisi Cursor   : Index #{stats['cursor']}")
    print(f"Status ALIVE    : {stats['alive']}")
    print(f"Status DEAD     : {stats['dead']}")
    print(f"Status UNKNOWN  : {stats['unknown']}")
    print(f"Status COOLDOWN : {stats['cooldown']}")
    print(f"Penggunaan IDLE : {stats['idle']}")
    print(f"Penggunaan IN_USE: {stats['in_use']}")
    print("=" * 60)

    if "--test-and-delete" in sys.argv or "--test-and-clean" in sys.argv:
        print("⚡ Menjalankan Fast Tester paralel & otomatis hapus proxy DEAD...")
        res = test_and_delete_dead(force=True)
        print(f"📊 Hasil: Total Diuji: {res['tested_total']} | Hidup (ALIVE): {res['alive']} | Mati (DEAD): {res['dead_found']}")
        print(f"🗑️ Berhasil menghapus {res['deleted_count']} proxy mati dari data/proxies.json.")
        print(f"✅ Sisa Total Proxy Aktif: {res['remaining_total']}")
    elif "--delete-dead" in sys.argv or "--remove-dead" in sys.argv or "--clean-dead" in sys.argv:
        print("🗑️ Menjalankan pembersihan proxy DEAD...")
        removed = delete_dead_proxies()
        print(f"✅ Berhasil menghapus {removed} proxy berstatus DEAD dari data/proxies.json.")
        new_stats = get_stats()
        print(f"📊 Sisa Total Proxy: {new_stats['total']} (Cursor: #{new_stats['cursor']})")
    elif "--validate-all" in sys.argv:
        print("🔍 Menjalankan validasi seluruh proxy secara paralel...")
        res = validate_all(force=True)
        print(f"Hasil: {res}")
    elif "--revalidate-dead" in sys.argv:
        print("🔄 Menjalankan revalidasi proxy DEAD...")
        res = revalidate_dead()
        print(f"Hasil: {res}")
    elif "--help" in sys.argv or "-h" in sys.argv:
        print("\nOpsi CLI:")
        print("  --test-and-delete  Uji seluruh proxy secara cepat dan langsung hapus yang mati (DEAD)")
        print("  --delete-dead      Hapus semua proxy yang saat ini berstatus DEAD")
        print("  --validate-all     Validasi seluruh proxy di database secara paralel")
        print("  --revalidate-dead  Validasi ulang proxy yang berstatus DEAD")
