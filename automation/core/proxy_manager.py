#!/usr/bin/env python3
"""
automation.core.proxy_manager - Robust Residential Proxy Management Engine
Handles thread-safe pool rotation, Just-in-Time (JIT) health checks,
dead proxy flagging, auto-backup recovery, and strict anti-leak protection.
"""

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import requests


class ProxyUnavailableError(Exception):
    """Exception raised when a proxy is required but unavailable, preventing local IP leakage."""
    pass


DEFAULT_TARGET = "https://read.riztama.my.id"


def resolve_proxy_path(proxy_source_path: str, base_dir: Optional[Path] = None) -> Path:
    """Mencari lokasi absolut dari file proksi."""
    p = Path(proxy_source_path)
    if p.is_absolute():
        return p

    search_dirs = [
        base_dir or Path(__file__).resolve().parent.parent,
        (base_dir or Path(__file__).resolve().parent.parent).parent,
    ]

    for d in search_dirs:
        candidate = d / p.name
        if candidate.exists():
            return candidate
        candidate_rel = d / p
        if candidate_rel.exists():
            return candidate_rel

    return p


def load_proxies(proxy_source_path: str, base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Membaca database proxies.json dengan proteksi anti-kosong / auto-recovery dari proxies_backup.json.
    """
    p = resolve_proxy_path(proxy_source_path, base_dir=base_dir)
    if not p.exists():
        print(f"[-] Warning: Proxy file not found at {proxy_source_path}")
        return []

    try:
        raw_text = p.read_text(encoding="utf-8").strip()
        if not raw_text:
            backup = p.parent / "proxies_backup.json"
            if backup.exists() and backup.stat().st_size > 0:
                try:
                    shutil.copy2(backup, p)
                    raw_text = p.read_text(encoding="utf-8").strip()
                    print(f"[*] [PROKSI-GUARD] File {p.name} kosong, dipulihkan dari {backup.name}")
                except Exception:
                    return []
            else:
                return []

        data = json.loads(raw_text)
        if isinstance(data, list):
            print(f"[+] Loaded {len(data)} proxies from {p.name}")
            return data
        return []
    except Exception as e:
        print(f"[-] Error loading proxies: {e}")
        return []


def proxy_identity(proxy_info: Dict[str, Any]) -> Tuple[str, str, str]:
    """Kunci identitas stabil sebuah proksi, tidak terpengaruh urutan index."""
    return (
        str(proxy_info.get("host", "")).strip().lower(),
        str(proxy_info.get("port", "")).strip(),
        str(proxy_info.get("username", "")).strip(),
    )


def build_proxy_url(proxy_info: Dict[str, Any]) -> str:
    host = proxy_info.get("host")
    port = proxy_info.get("port")
    user = proxy_info.get("username", "")
    pwd = proxy_info.get("password", "")
    if user and pwd:
        return f"http://{user}:{pwd}@{host}:{port}"
    return f"http://{host}:{port}"


def probe_proxy_target(
    proxy_info: Dict[str, Any],
    target_url: str = DEFAULT_TARGET,
    timeout: float = 10.0,
) -> Tuple[bool, str]:
    """
    Menguji proksi langsung ke website target.
    Hanya respons HTTP 200 OK yang dianggap lolos dan layak dipakai browser.
    """
    if not proxy_info:
        return True, "Direct Connection"
    host = proxy_info.get("host")
    port = proxy_info.get("port")
    if not host or not port:
        return False, "Host/Port tidak valid"

    px_url = build_proxy_url(proxy_info)
    proxies_dict = {"http": px_url, "https": px_url}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

    try:
        resp = requests.get(
            target_url,
            proxies=proxies_dict,
            timeout=timeout,
            headers=headers,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            return True, "HTTP 200 OK"
        return False, f"HTTP {resp.status_code} (bukan 200 OK)"
    except requests.exceptions.ProxyError as e:
        err = str(e)
        if "402" in err:
            return False, "402 Payment Required (saldo/akun proxy habis)"
        if "407" in err:
            return False, "Autentikasi Gagal (407 Proxy Unauthorized)"
        return False, f"Tunneling Proksi Gagal: {err[:45]}"
    except requests.exceptions.ConnectTimeout:
        return False, f"Koneksi Timeout (> {timeout}s)"
    except requests.exceptions.ReadTimeout:
        return False, f"Respon Timeout (> {timeout}s)"
    except Exception as e:
        err_s = str(e).splitlines()[0] if str(e) else "Unknown"
        return False, f"Koneksi gagal: {err_s[:45]}"


class ProxyManager:
    """
    Manager Pengelolaan Proksi Residensial yang Cerdas & Rapi:
    - Strictly sequential: hanya satu worker yang boleh memilih + menguji proksi
      pada satu waktu. Worker lain menunggu giliran (antrean linear).
    - Hanya proksi yang merespons HTTP 200 OK dari website target yang dipakai.
    - Gagal sesaat TIDAK langsung membunuh proksi. Diperlukan beberapa kegagalan
      berturut-turut sebelum proksi ditandai mati (in-memory).
    - Sebelum menandai mati, target dicek langsung. Jika target sendiri sedang
      bermasalah, kegagalan proksi tidak dihitung sebagai proxy mati.
    - Status mati tidak pernah ditulis ke proxies.json. File proksi tetap utuh,
      proxy baru yang ditambahkan saat bot berjalan otomatis ikut terdeteksi.
    """

    def __init__(
        self,
        proxy_file_path: Optional[str] = None,
        proxies: Optional[List[Dict[str, Any]]] = None,
        target_concurrency: int = 1,
        failure_threshold: int = 3,
        check_attempts: int = 2,
        check_timeout: float = 6.5,
        sync_from_disk: bool = True,
        persist_runtime_state: bool = False,
    ):
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.test_lock = threading.Lock()
        self.file_path = Path(proxy_file_path) if proxy_file_path else None
        self.proxies = [dict(px) for px in proxies] if proxies else []
        self.next_index = 0
        self.in_use_indices = set()
        self.dead_indices = set()
        self.target_concurrency = max(1, target_concurrency)

        self.failure_threshold = max(1, failure_threshold)
        self.check_attempts = max(1, check_attempts)
        self.check_timeout = max(1.0, check_timeout)
        self.sync_from_disk = bool(sync_from_disk) and self.file_path is not None
        self.persist_runtime_state = bool(persist_runtime_state)

        self.failure_counts: Dict[int, int] = {}
        self.nav_failures: Dict[int, int] = {}
        self.consecutive_failures = 0
        self.last_success_at = 0.0
        self._last_disk_sync = 0.0
        self._backup_created = False
        self._target_check_at = 0.0
        self._target_check_result: Optional[bool] = None
        self._target_unhealthy_until = 0.0
        self._target_guard_ttl = 10.0

        ignored_dead = 0
        for px in self.proxies:
            if px.pop("dead", False):
                ignored_dead += 1
            px.pop("fail_count", None)
            px.pop("fail_streak", None)
            px.pop("dead_at", None)
        if ignored_dead:
            print(
                f"[*] [PROKSI-GUARD] {ignored_dead} flag 'dead' lama diabaikan; "
                "semua proksi akan diuji ulang secara adil pada sesi ini."
            )

    @property
    def dead_proxy_count(self) -> int:
        with self.lock:
            return len(self.dead_indices)

    def _max_consecutive_failures(self) -> int:
        return max(6, self.target_concurrency)

    def create_backup_if_needed(self):
        """Membuat backup otomatis 1x proxies_backup.json sebelum modifikasi."""
        if not self._backup_created and self.file_path and self.file_path.exists():
            backup_file = self.file_path.parent / "proxies_backup.json"
            if not backup_file.exists():
                try:
                    shutil.copy2(self.file_path, backup_file)
                    print(f"[*] [PROKSI-GUARD] Backup proksi asli aman disimpan di: {backup_file.name}")
                    self._backup_created = True
                except Exception:
                    pass

    def save_proxies_to_disk(self):
        """
        Menyimpan proksi ke disk hanya jika persist_runtime_state diaktifkan.

        Default-nya status runtime (dead/failure) TIDAK ditulis ke proxies.json
        agar file bersama tidak pernah kehilangan proksi baru atau menyimpan
        status mati yang sudah basi.
        """
        if not self.file_path or not self.persist_runtime_state:
            return
        self.create_backup_if_needed()
        try:
            temp_file = self.file_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.proxies, f, indent=2)
            temp_file.replace(self.file_path)
        except Exception as e:
            print(f"[-] [PROKSI-GUARD] Gagal menyimpan proxies.json: {e}")

    def sync_new_proxies_from_disk(self, force: bool = False):
        """Menambahkan proksi baru dari proxies.json tanpa mengubah index yang sudah ada."""
        if not self.sync_from_disk or not self.file_path:
            return
        now = time.monotonic()
        if not force and (now - self._last_disk_sync) < 5.0:
            return
        self._last_disk_sync = now
        try:
            if not self.file_path.exists():
                return
            raw = self.file_path.read_text(encoding="utf-8").strip()
            if not raw:
                return
            data = json.loads(raw)
        except Exception:
            return
        if not isinstance(data, list):
            return

        with self.condition:
            known = {proxy_identity(px): i for i, px in enumerate(self.proxies)}
            added = 0
            for px in data:
                if not isinstance(px, dict):
                    continue
                key = proxy_identity(px)
                if not key[0] or not key[1]:
                    continue
                if key in known:
                    existing = self.proxies[known[key]]
                    for field in ("password", "country", "connection_type", "proxy_url"):
                        if field in px and existing.get(field) != px.get(field):
                            existing[field] = px[field]
                    continue
                new_px = dict(px)
                new_px.pop("dead", None)
                new_px.pop("fail_count", None)
                new_px.pop("fail_streak", None)
                new_px.pop("dead_at", None)
                known[key] = len(self.proxies)
                self.proxies.append(new_px)
                added += 1
            if added:
                print(
                    f"[+] [PROKSI-GUARD] {added} proksi baru terdeteksi dari {self.file_path.name} "
                    f"(total sekarang: {len(self.proxies)})."
                )
                self.condition.notify_all()

    def check_proxy_alive(
        self,
        proxy_info: Dict[str, Any],
        target_url: str = DEFAULT_TARGET,
        timeout: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Uji proksi langsung ke website target; hanya HTTP 200 OK yang lolos."""
        return probe_proxy_target(
            proxy_info,
            target_url=target_url or DEFAULT_TARGET,
            timeout=timeout if timeout is not None else self.check_timeout,
        )

    def _target_healthy_direct(
        self,
        target_url: Optional[str] = None,
        timeout: float = 8.0,
        force: bool = False,
    ) -> bool:
        """
        Cek target tanpa proksi. Dipakai sebagai pembanding sebelum proksi ditandai mati.
        Jika target sendiri tidak merespons 200 OK, kegagalan proksi tidak dihitung.
        """
        now = time.monotonic()
        if (
            not force
            and self._target_check_result is not None
            and (now - self._target_check_at) < self._target_guard_ttl
        ):
            return self._target_check_result

        ok = False
        reason = "Tidak diketahui"
        try:
            session = requests.Session()
            session.trust_env = False
            resp = session.get(
                target_url or DEFAULT_TARGET,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
                allow_redirects=True,
            )
            ok = resp.status_code == 200
            reason = f"HTTP {resp.status_code}"
        except Exception as e:
            reason = str(e).splitlines()[0][:60] if str(e) else "Unknown"

        self._target_check_at = now
        self._target_check_result = ok
        if not ok:
            print(
                f"[*] [PROKSI-GUARD] [TARGET-GUARD] Target tidak sehat saat dicek langsung "
                f"({reason}). Kegagalan proksi TIDAK akan ditandai mati."
            )
        return ok

    def _check_candidate(self, candidate: Dict[str, Any], target_url: str) -> Tuple[bool, str]:
        last_reason = "Gagal tanpa alasan"
        for attempt in range(self.check_attempts):
            is_alive, reason = self.check_proxy_alive(
                candidate,
                target_url=target_url,
                timeout=self.check_timeout,
            )
            if is_alive:
                return True, reason
            last_reason = reason
            if "402" in reason or "407" in reason or "Autentikasi Gagal" in reason:
                return False, reason
            if attempt < self.check_attempts - 1:
                time.sleep(0.8 * (attempt + 1))
        return False, last_reason

    def _select_candidate_locked(self, now: float, preferred_index: Optional[int], consume: bool = True):
        total_px = len(self.proxies)
        if total_px == 0:
            return None, 0.0, "empty"

        order: List[int] = []
        if preferred_index is not None and 0 <= preferred_index < total_px:
            order.append(preferred_index)
        for offset in range(total_px):
            idx = (self.next_index + offset) % total_px
            if idx not in order:
                order.append(idx)

        for idx in order:
            if idx in self.in_use_indices or idx in self.dead_indices:
                continue
            if consume:
                self.next_index = (idx + 1) % total_px
            return idx, 0.0, "ok"

        if len(self.dead_indices) >= total_px:
            return None, 0.0, "all_dead"
        return None, 1.0, "wait"

    def _record_failure_locked(
        self,
        idx: int,
        reason: str,
        source: str = "health-check",
        allow_dead: bool = True,
        hard_failure: bool = False,
    ) -> bool:
        self.consecutive_failures += 1
        px_num = idx + 1
        px = self.proxies[idx] if 0 <= idx < len(self.proxies) else {}
        country = px.get("country", "Global")
        host = px.get("host", "?")
        port = px.get("port", "?")

        if not allow_dead:
            self.failure_counts[idx] = 0
            self.nav_failures[idx] = 0
            self._target_unhealthy_until = time.monotonic() + self._target_guard_ttl
            print(
                f"[*] ⏸️ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({host}:{port}) gagal "
                f"({reason}), tetapi target juga tidak sehat. Kegagalan tidak dihitung; "
                "proksi tetap hidup dan akan dicoba lagi."
            )
            return False

        count = self.failure_threshold if hard_failure else self.failure_counts.get(idx, 0) + 1
        self.failure_counts[idx] = count

        if count >= self.failure_threshold:
            self.dead_indices.add(idx)
            self.failure_counts[idx] = 0
            self.nav_failures[idx] = 0
            detail = "error definitif" if hard_failure else f"{count}x gagal berturut-turut"
            print(
                f"[*] ❌ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({host}:{port}) MATI "
                f"({reason}) - {detail} ({source}). "
                "Dilewati untuk sesi ini; tidak dihapus dari proxies.json."
            )
            return True

        print(
            f"[*] ⚠️ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({host}:{port}) gagal "
            f"({reason}) [{count}/{self.failure_threshold}]. Belum dianggap mati."
        )
        return False

    def get_valid_proxy(
        self,
        target_url: str = "https://read.riztama.my.id",
        preferred_index: Optional[int] = None,
        worker_id: int = 1,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        tag = f"[B{worker_id}]" if worker_id else "[*]"

        while True:
            now = time.monotonic()
            if now < self._target_unhealthy_until:
                with self.condition:
                    self.condition.wait(timeout=min(max(self._target_unhealthy_until - now, 0.5), 5.0))
                continue

            self.sync_new_proxies_from_disk()
            with self.lock:
                if not self.proxies:
                    return None, None
                now = time.monotonic()
                _, wait_s, state = self._select_candidate_locked(now, preferred_index, consume=False)

            if state == "empty":
                return None, None

            if state == "all_dead":
                print(
                    f"{tag} 🛑 [PROKSI-POOL] Semua proksi sudah ditandai mati pada sesi ini. "
                    "Sesi dihentikan; proxies.json tidak diubah dan semua proksi akan diuji ulang "
                    "pada sesi berikutnya."
                )
                return None, None

            if state == "wait":
                with self.condition:
                    self.condition.wait(timeout=min(max(wait_s, 0.5), 2.0))
                continue

            with self.test_lock:
                self.sync_new_proxies_from_disk()
                with self.lock:
                    now = time.monotonic()
                    idx, wait_s, state = self._select_candidate_locked(now, preferred_index)
                    if state != "ok":
                        continue
                    self.in_use_indices.add(idx)
                    candidate = self.proxies[idx]

                px_num = idx + 1
                host = candidate.get("host")
                port = int(candidate.get("port", 10080))
                country = candidate.get("country", "Global")
                print(
                    f"{tag} 🔍 [PROKSI-TEST] [PX#{px_num}] Menguji kelayakan proksi #{px_num} "
                    f"{country} ({host}:{port}) sebelum dipakai..."
                )

                is_alive, reason = self._check_candidate(candidate, target_url)
                allow_dead = is_alive or self._target_healthy_direct(target_url)

                with self.condition:
                    if is_alive:
                        self.in_use_indices.add(idx)
                        self.failure_counts[idx] = 0
                        self.dead_indices.discard(idx)
                        self.consecutive_failures = 0
                        self.last_success_at = time.monotonic()
                        self._target_check_result = True
                        self._target_check_at = time.monotonic()
                        self._target_unhealthy_until = 0.0
                        self.condition.notify_all()
                        print(
                            f"{tag} ✅ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} "
                            f"({host}:{port}) AKTIF & VALID ({reason})! Siap digunakan browser."
                        )
                        return candidate, idx

                    self.in_use_indices.discard(idx)
                    hard_failure = any(
                        marker in reason
                        for marker in ("402", "407", "Autentikasi Gagal")
                    )
                    self._record_failure_locked(
                        idx,
                        reason,
                        source="health-check",
                        allow_dead=allow_dead,
                        hard_failure=hard_failure,
                    )
                    self.condition.notify_all()
                    if not allow_dead and self.consecutive_failures >= self._max_consecutive_failures():
                        print(
                            f"{tag} 🛑 [PROKSI-GUARD] [CIRCUIT-BREAKER] "
                            f"{self.consecutive_failures} kegagalan beruntun saat target tidak sehat. "
                            "Sesi dihentikan sementara demi keamanan anti-leak."
                        )
                        return None, None

    def release_proxy(self, proxy_idx: Optional[int], worker_id: int = 1):
        if proxy_idx is None:
            return
        with self.condition:
            was_in_use = proxy_idx in self.in_use_indices
            self.in_use_indices.discard(proxy_idx)
            is_dead = proxy_idx in self.dead_indices
            tag = f"[B{worker_id}]" if worker_id else "[*]"
            px_num = proxy_idx + 1
            if is_dead:
                print(f"{tag} [*] [PX#{px_num}] Proksi mati pada sesi ini, tidak dikembalikan ke pool idle.")
            elif was_in_use:
                print(f"{tag} [*] [PX#{px_num}] Selesai digunakan, dikembalikan ke pool idle.")
            self.condition.notify_all()

    def mark_dead(
        self,
        proxy_idx: Optional[int],
        reason: str = "",
        target_url: Optional[str] = None,
    ):
        """Catat kegagalan navigasi. Proksi hanya mati setelah beberapa kegagalan."""
        if proxy_idx is None:
            return

        allow_dead = self._target_healthy_direct(target_url)

        with self.condition:
            self.in_use_indices.discard(proxy_idx)
            px_num = proxy_idx + 1
            if 0 <= proxy_idx < len(self.proxies):
                px = self.proxies[proxy_idx]
                country = px.get("country", "Global")
                host = px.get("host", "?")
                port = px.get("port", "?")
            else:
                country, host, port = "Global", "?", "?"

            if not allow_dead:
                self.nav_failures[proxy_idx] = 0
                self.failure_counts[proxy_idx] = 0
                self._target_unhealthy_until = time.monotonic() + self._target_guard_ttl
                print(
                    f"[*] ⏸️ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({host}:{port}) "
                    f"gagal navigasi ({reason}), tetapi target juga tidak sehat. "
                    "Kegagalan tidak dihitung."
                )
                self.condition.notify_all()
                return

            count = self.nav_failures.get(proxy_idx, 0) + 1
            self.nav_failures[proxy_idx] = count

            if count >= self.failure_threshold:
                self.dead_indices.add(proxy_idx)
                self.nav_failures[proxy_idx] = 0
                self.failure_counts[proxy_idx] = 0
                print(
                    f"[*] ❌ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({host}:{port}) MATI "
                    f"saat navigasi ({reason}) setelah {count}x gagal berturut-turut. "
                    "Dilewati untuk sesi ini; tidak dihapus dari proxies.json."
                )
            else:
                print(
                    f"[*] ⚠️ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({host}:{port}) "
                    f"gagal navigasi ({reason}) [{count}/{self.failure_threshold}]. "
                    "Belum dianggap mati."
                )
            self.condition.notify_all()

    def report_session_success(self, proxy_idx: Optional[int], worker_id: int = 1):
        """Reset hitungan kegagalan navigasi setelah sesi benar-benar sukses."""
        if proxy_idx is None:
            return
        with self.condition:
            self.nav_failures.pop(proxy_idx, None)
            self.failure_counts[proxy_idx] = 0
            self.consecutive_failures = 0
            self._target_check_result = True
            self._target_check_at = time.monotonic()
            self._target_unhealthy_until = 0.0
            self.condition.notify_all()

    def remove_dead_proxy(
        self,
        proxy_dict_or_idx,
        reason: str = "",
        target_url: Optional[str] = None,
    ):
        if isinstance(proxy_dict_or_idx, int):
            self.mark_dead(proxy_dict_or_idx, reason, target_url=target_url)
        elif isinstance(proxy_dict_or_idx, dict):
            key = proxy_identity(proxy_dict_or_idx)
            with self.lock:
                for idx, px in enumerate(self.proxies):
                    if proxy_identity(px) == key:
                        target_idx = idx
                        break
                else:
                    return
            self.mark_dead(target_idx, reason, target_url=target_url)

    def prune_dead_proxies(self):
        """
        Kompatibilitas API lama. Status dead sekarang hanya in-memory dan tidak
        pernah menghapus proksi dari proxies.json.
        """
        with self.lock:
            alive_count = len(self.proxies) - len(self.dead_indices)
        print(
            f"[*] [PROKSI-GUARD] Status runtime: {len(self.dead_indices)} proksi mati pada sesi ini, "
            f"{alive_count} proksi siap diuji/dipakai. File proxies.json tidak diubah."
        )
