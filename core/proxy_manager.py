"""
Proxy Management Module
Satu-satunya source of truth untuk daftar proxy, status validasi,
status penggunaan, dan posisi cursor rotasi persisten di proxies.json.
"""

import os
import json
import time
import uuid
import threading
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List, Union
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

KNOWN_PROXY_ERRORS = (
    "ProxyError",
    "ConnectTimeout",
    "ConnectionRefused",
    "407",
    "Proxy Authentication Required",
    "Tunnel connection failed",
    "SOCKSHTTPConnection",
)


class ProxyManager:
    def __init__(
        self,
        filepath: str = DEFAULT_PROXY_FILE,
        check_url: str = CHECK_URL,
        timeout: int = CHECK_TIMEOUT,
        reset_stale_usage: bool = False,
        reset_cursor: bool = False,
    ):
        self.filepath = os.path.abspath(filepath)
        self.check_url = check_url
        self.timeout = timeout
        self._lock = threading.RLock()
        self._ensure_file()
        if reset_stale_usage:
            self.reset_usage_to_idle()
        if reset_cursor:
            self.reset_cursor(0)

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

    def validate_all(self, force: bool = False) -> Dict[str, int]:
        """Validasi semua proxy dalam pool."""
        with self._lock:
            data = self._load_raw()
            ids = [p["id"] for p in data["proxies"]]

        alive_count = 0
        dead_count = 0
        for pid in ids:
            res = self.validate_proxy(pid, force=force)
            if res.get("health") == HEALTH_ALIVE:
                alive_count += 1
            else:
                dead_count += 1

        return {"alive": alive_count, "dead": dead_count, "total": len(ids)}

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
        """
        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])
            total = len(proxies)
            if total == 0:
                return None

            cursor = data.get("cursor", 0) % total
            lease_token = caller_id or f"lease_{uuid.uuid4().hex[:8]}"

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
                    if exclusive and candidate.get("usage") == USAGE_IN_USE:
                        continue

                    # 2. Lewati jika DEAD
                    if candidate.get("health") == HEALTH_DEAD:
                        continue

                    # 3. Cek modular target usage jika target ditentukan
                    if target:
                        t_usage = candidate.setdefault("target_usage", {})
                        if not isinstance(t_usage, dict):
                            t_usage = {}
                            candidate["target_usage"] = t_usage
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
                    if candidate.get("health") == HEALTH_COOLDOWN:
                        last_chk = candidate.get("last_checked", 0) or 0
                        if (time.time() - last_chk) < 60:  # 60 detik masa pendinginan
                            continue
                        # Selesai cooldown, kembalikan ke ALIVE untuk dicoba
                        candidate["health"] = HEALTH_ALIVE

                    # 5. Jika UNKNOWN, harus divalidasi terlebih dahulu
                    if candidate.get("health") == HEALTH_UNKNOWN:
                        # Validasi
                        proxy_url = candidate.get("proxy_url")
                        if not proxy_url:
                            candidate["health"] = HEALTH_DEAD
                            continue

                        # Lepas lock sementara untuk network call
                        test_res = self._test_proxy_network(proxy_url)
                        candidate["last_checked"] = time.time()
                        if test_res["success"]:
                            candidate["health"] = HEALTH_ALIVE
                            candidate["ip_detected"] = test_res["ip"]
                            candidate["latency_ms"] = test_res["latency_ms"]
                            candidate["fail_count"] = 0
                            candidate["last_error"] = None
                        else:
                            candidate["health"] = HEALTH_DEAD
                            candidate["last_error"] = test_res["error"]
                            # Lanjutkan rotasi mencari yang lain
                            continue

                    # 6. Jika ALIVE dan memenuhi syarat, alokasikan!
                    if candidate.get("health") == HEALTH_ALIVE:
                        # Jika verify_alive=True, re-verifikasi koneksi proxy di jaringan langsung!
                        if verify_alive:
                            proxy_url = candidate.get("proxy_url")
                            if not proxy_url:
                                candidate["health"] = HEALTH_DEAD
                                continue

                            test_res = self._test_proxy_network(proxy_url)
                            candidate["last_checked"] = time.time()
                            if test_res["success"]:
                                candidate["health"] = HEALTH_ALIVE
                                candidate["ip_detected"] = test_res["ip"]
                                candidate["latency_ms"] = test_res["latency_ms"]
                                candidate["fail_count"] = 0
                                candidate["last_error"] = None
                            else:
                                candidate["health"] = HEALTH_DEAD
                                candidate["last_error"] = test_res["error"]
                                # Proxy mati terkonfirmasi, lewati dan cari kandidat berikutnya
                                continue

                        target_info = None
                        if target:
                            t_usage = candidate.setdefault("target_usage", {})
                            if not isinstance(t_usage, dict):
                                t_usage = {}
                                candidate["target_usage"] = t_usage
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
                            candidate["usage"] = USAGE_IN_USE
                            candidate["leased_by"] = lease_token
                            candidate["lease_time"] = time.time()

                        # Simpan cursor berikutnya (setelah kandidat ini)
                        data["cursor"] = (idx + 1) % total
                        self._save_raw(data)

                        allocated = dict(candidate)
                        allocated["lease_token"] = lease_token
                        if target_info:
                            allocated["target_info"] = target_info
                        return allocated

            # Jika sudah 1 putaran tidak ada proxy yang bisa dipakai:
            # Tetap simpan cursor agar posisi tidak tersendat di index mati
            data["cursor"] = (cursor + 1) % total
            self._save_raw(data)
            return None

    def reset_usage_to_idle(self) -> int:
        """
        Membersihkan seluruh status IN_USE menjadi IDLE.
        Menangani kasus jika ada proses sebelumnya yang mati mendadak (killed/crashed)
        sehingga status proxy tidak terkunci di IN_USE.
        """
        with self._lock:
            data = self._load_raw()
            cleaned = 0
            for p in data.get("proxies", []):
                if p.get("usage") == USAGE_IN_USE or p.get("leased_by") is not None:
                    p["usage"] = USAGE_IDLE
                    p["leased_by"] = None
                    p["lease_time"] = None
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

    def release_proxy(self, identifier: str, caller_id: Optional[str] = None) -> bool:
        """
        Melepaskan alokasi proxy agar kembali IDLE.
        - Jika proxy DEAD, tetap DEAD (tidak otomatis jadi ALIVE).
        - Pemanggilan release aman dan tidak membatalkan alokasi milik caller lain.
        """
        if isinstance(identifier, dict):
            identifier = identifier.get("id") or identifier.get("proxy_url") or ""

        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])

            for p in proxies:
                matches_id = (p.get("id") == identifier or p.get("proxy_url") == identifier)
                matches_token = (p.get("leased_by") == identifier)

                if matches_id or matches_token:
                    # Cek kepemilikan caller_id jika disertakan
                    if caller_id and p.get("leased_by") and p.get("leased_by") != caller_id:
                        return False  # Dimiliki oleh caller lain

                    p["usage"] = USAGE_IDLE
                    p["leased_by"] = None
                    p["lease_time"] = None
                    self._save_raw(data)
                    return True

            return False

    # =========================================================================
    # 3b. MODULAR TARGET USAGE TRACKER (ADSTERRA, YOUTUBE, DLL)
    # =========================================================================

    def record_target_usage(
        self,
        identifier: str,
        target: str,
        window_seconds: float = 24 * 3600,
    ) -> bool:
        """
        Mencatat pemakaian proxy untuk target tertentu (misal: 'adsterra', 'youtube').
        Menambah count, memperbarui last_used, dan menyimpan riwayat epoch.
        Otomatis me-reset count jika pemakaian terakhir sudah melebihi window 24 jam.
        """
        with self._lock:
            data = self._load_raw()
            proxies = data.get("proxies", [])
            for p in proxies:
                matches_id = (p.get("id") == identifier or p.get("proxy_url") == identifier)
                matches_token = (p.get("leased_by") == identifier)
                if matches_id or matches_token:
                    t_usage = p.setdefault("target_usage", {})
                    if not isinstance(t_usage, dict):
                        t_usage = {}
                        p["target_usage"] = t_usage
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
        """Format ringkasan pemakaian IP per target (misal: 'Hit 1/2 (Baru)' atau 'Hit 2/2 (Sesi 2)')."""
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
            summary = f"Hit {curr}/{max_uses_per_day} (Sesi 2)"
        else:
            summary = f"Hit {count}/{max_uses_per_day} (Habis)"
        return {
            "current_hit": curr,
            "count": count,
            "max_uses": max_uses_per_day,
            "summary_text": summary,
            "can_use": info.get("can_use", True),
        }

    def record_target_hit(
        self,
        proxy_or_id: Union[str, Dict[str, Any]],
        target: str = "monetag",
        window_seconds: float = 24 * 3600,
    ) -> bool:
        """Alias praktis untuk record_target_usage yang menerima dict proxy atau ID string."""
        p_id = proxy_or_id.get("id") if isinstance(proxy_or_id, dict) else str(proxy_or_id)
        return self.record_target_usage(identifier=p_id, target=target, window_seconds=window_seconds)

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

    def report_failure(self, identifier: str, error_message: Optional[str] = None, is_proxy_error: bool = False) -> Dict[str, Any]:
        """
        Melaporkan kegagalan penggunaan proxy.
        - Membedakan kegagalan proxy dari kegagalan website tujuan/gangguan sesaat.
        - Tidak langsung menandai DEAD jika bukan kegagalan proxy yang fatal.
        - Jika is_proxy_error=True atau fail_count mencapai batas: lakukan pengetesan ulang.
          Jika pengetesan membuktikan proxy mati, status diubah menjadi DEAD.
        """
        proxy_id = None
        proxy_url = None
        suspected_proxy_fault = False
        fail_count = 0

        with self._lock:
            data = self._load_raw()
            proxy = None
            for p in data["proxies"]:
                if p.get("id") == identifier or p.get("proxy_url") == identifier or p.get("leased_by") == identifier:
                    proxy = p
                    break

            if not proxy:
                return {"status": "NOT_FOUND"}

            err_str = str(error_message or "")
            proxy["last_error"] = err_str
            proxy["fail_count"] = proxy.get("fail_count", 0) + 1
            fail_count = proxy["fail_count"]
            proxy_id = proxy.get("id")
            proxy_url = proxy.get("proxy_url")

            # Deteksi apakah error menunjukkan proxy rusak
            suspected_proxy_fault = is_proxy_error or any(k.lower() in err_str.lower() for k in KNOWN_PROXY_ERRORS)
            self._save_raw(data)

        # Jika diduga kuat proxy mati atau gagal berulang kali, lakukan tes kepastian
        if suspected_proxy_fault or fail_count >= MAX_FAIL_THRESHOLD:
            if proxy_url:
                test_res = self._test_proxy_network(proxy_url)
                with self._lock:
                    data = self._load_raw()
                    for p in data["proxies"]:
                        if p.get("id") == proxy_id:
                            p["last_checked"] = time.time()
                            if not test_res["success"]:
                                p["health"] = HEALTH_DEAD
                                p["last_error"] = f"Dead confirmed: {test_res['error']}"
                            else:
                                # Ternyata jaringannya masih hidup, pasang status COOLDOWN
                                p["health"] = HEALTH_COOLDOWN
                                p["latency_ms"] = test_res["latency_ms"]
                            self._save_raw(data)
                            return dict(p)
            else:
                with self._lock:
                    data = self._load_raw()
                    for p in data["proxies"]:
                        if p.get("id") == proxy_id:
                            p["health"] = HEALTH_DEAD
                            self._save_raw(data)
                            return dict(p)
        else:
            # Kesalahan sementara (misal website tujuan 502/rate-limit)
            with self._lock:
                data = self._load_raw()
                for p in data["proxies"]:
                    if p.get("id") == proxy_id:
                        # Masukkan ke COOLDOWN sementara agar tidak langsung dihantam request lagi
                        p["health"] = HEALTH_COOLDOWN
                        p["last_checked"] = time.time()
                        self._save_raw(data)
                        return dict(p)

        with self._lock:
            data = self._load_raw()
            for p in data["proxies"]:
                if p.get("id") == proxy_id:
                    return dict(p)
            return {"status": "NOT_FOUND"}


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
    )


def record_target_usage(identifier: str, target: str, window_seconds: float = 24 * 3600) -> bool:
    """Mencatat pemakaian proxy untuk target tertentu."""
    return get_manager().record_target_usage(identifier=identifier, target=target, window_seconds=window_seconds)


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


def release_proxy(identifier: str, caller_id: Optional[str] = None) -> bool:
    """Melepaskan proxy setelah selesai digunakan."""
    return get_manager().release_proxy(identifier=identifier, caller_id=caller_id)


def report_failure(identifier: str, error_message: Optional[str] = None, is_proxy_error: bool = False) -> Dict[str, Any]:
    """Melaporkan error saat menggunakan proxy."""
    return get_manager().report_failure(identifier=identifier, error_message=error_message, is_proxy_error=is_proxy_error)


def validate_proxy(identifier: str, force: bool = False) -> Dict[str, Any]:
    """Memvalidasi proxy tertentu."""
    return get_manager().validate_proxy(identifier=identifier, force=force)


def revalidate_dead() -> Dict[str, int]:
    """Meminta pengecekan ulang terhadap semua proxy yang berstatus DEAD."""
    return get_manager().revalidate_dead()


def validate_all(force: bool = False) -> Dict[str, int]:
    """Memvalidasi seluruh proxy dalam pool."""
    return get_manager().validate_all(force=force)


def append_proxy(proxy_data: Union[Dict[str, Any], str]) -> Optional[Dict[str, Any]]:
    """Menambahkan/meng-append satu proxy ke proxies.json."""
    return get_manager().append_proxy(proxy_data)


def append_proxies(proxy_list: List[Union[Dict[str, Any], str]]) -> int:
    """Menambahkan/meng-append daftar proxy baru ke proxies.json."""
    return get_manager().append_proxies(proxy_list)


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


def reset_usage_to_idle() -> int:
    """Membersihkan seluruh status IN_USE menjadi IDLE."""
    return get_manager().reset_usage_to_idle()


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

    if "--delete-dead" in sys.argv or "--remove-dead" in sys.argv or "--clean-dead" in sys.argv:
        print("🗑️ Menjalankan pembersihan proxy DEAD...")
        removed = delete_dead_proxies()
        print(f"✅ Berhasil menghapus {removed} proxy berstatus DEAD dari data/proxies.json.")
        new_stats = get_stats()
        print(f"📊 Sisa Total Proxy: {new_stats['total']} (Cursor: #{new_stats['cursor']})")
    elif "--validate-all" in sys.argv:
        print("🔍 Menjalankan validasi seluruh proxy...")
        res = validate_all(force=True)
        print(f"Hasil: {res}")
    elif "--revalidate-dead" in sys.argv:
        print("🔄 Menjalankan revalidasi proxy DEAD...")
        res = revalidate_dead()
        print(f"Hasil: {res}")
    elif "--help" in sys.argv or "-h" in sys.argv:
        print("\nOpsi CLI:")
        print("  --delete-dead     Hapus semua proxy berstatus DEAD")
        print("  --validate-all    Validasi seluruh proxy di database")
        print("  --revalidate-dead Validasi ulang proxy yang berstatus DEAD")
