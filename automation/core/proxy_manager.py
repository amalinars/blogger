#!/usr/bin/env python3
"""
automation.core.proxy_manager - Robust Residential Proxy Management Engine
Handles thread-safe pool rotation, Just-in-Time (JIT) health checks,
dead proxy flagging, auto-backup recovery, and strict anti-leak protection.
"""

import json
import shutil
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import requests


class ProxyUnavailableError(Exception):
    """Exception raised when a proxy is required but unavailable, preventing local IP leakage."""
    pass


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


class ProxyManager:
    """
    Manager Pengelolaan Proksi Residensial yang Cerdas & Rapi:
    - On-Demand sequential testing: menguji proksi satu per satu berurutan tanpa lompat.
    - Proksi yang mati selama sesi bot ditandai dengan flag "dead": true di proxies.json,
      BUKAN dihapus. Ini mencegah bot berhenti tiba-tiba saat proxy dipangkas.
    - Proksi dead diskip saat seleksi, tetapi tetap ada di daftar & GUI (terlihat sebagai Mati).
    - Pembersihan (penghapusan) proksi dead dilakukan HANYA saat GUI pertama kali dibuka.
    """

    def __init__(
        self,
        proxy_file_path: Optional[str] = None,
        proxies: Optional[List[Dict[str, Any]]] = None,
        target_concurrency: int = 1,
    ):
        self.lock = threading.RLock()
        self.test_lock = threading.Lock()
        self.file_path = Path(proxy_file_path) if proxy_file_path else None
        self.proxies = list(proxies) if proxies else []
        self.next_index = 0
        self.in_use_indices = set()
        self.dead_indices = set()
        self.target_concurrency = max(1, target_concurrency)
        self.initial_batch_pruned = False
        self._backup_created = False

        # Deteksi proksi yang sudah di-flag dead dari sesi sebelumnya
        for idx, px in enumerate(self.proxies):
            if px.get("dead", False):
                self.dead_indices.add(idx)

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
        """Menyimpan list proksi (termasuk yang dead) ke proxies.json secara aman (atomic write)."""
        if not self.file_path:
            return
        self.create_backup_if_needed()
        try:
            temp_file = self.file_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.proxies, f, indent=2)
            temp_file.replace(self.file_path)
        except Exception as e:
            print(f"[-] [PROKSI-GUARD] Gagal menyimpan proxies.json: {e}")

    def check_proxy_alive(
        self,
        proxy_info: Dict[str, Any],
        target_url: str = "https://blog.riztama.my.id",
        timeout: float = 5.5,
    ) -> Tuple[bool, str]:
        """
        Uji kelayakan proksi sesaat sebelum diserahkan ke browser:
        Lightweight HTTP HEAD request memastikan autentikasi & tunneling aktif ke target URL.
        Batas timeout 5.5 detik disesuaikan dengan latensi rata-rata proksi residensial (~3.4 detik).
        """
        if not proxy_info:
            return True, "Direct Connection"
        host = proxy_info.get("host")
        port = proxy_info.get("port")
        if not host or not port:
            return False, "Host/Port tidak valid"

        try:
            user = proxy_info.get("username", "")
            pwd = proxy_info.get("password", "")
            if user and pwd:
                px_url = f"http://{user}:{pwd}@{host}:{port}"
            else:
                px_url = f"http://{host}:{port}"

            proxies_dict = {"http": px_url, "https": px_url}
            resp = requests.head(
                target_url,
                proxies=proxies_dict,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
            )
            if resp.status_code < 500:
                return True, f"HTTP {resp.status_code} OK"
            return False, f"Server mengembalikan HTTP {resp.status_code}"
        except requests.exceptions.ProxyError as e:
            err = str(e)
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

    def prune_dead_proxies(self):
        """
        Menandai semua proksi mati dengan flag 'dead': true di proxies.json.
        Proksi TIDAK dihapus dari daftar — hanya di-flag agar diskip saat seleksi.
        """
        with self.lock:
            if not self.dead_indices:
                return

            flagged_count = 0
            for idx in self.dead_indices:
                if 0 <= idx < len(self.proxies):
                    if not self.proxies[idx].get("dead", False):
                        self.proxies[idx]["dead"] = True
                        flagged_count += 1

            alive_count = sum(1 for i, px in enumerate(self.proxies) if i not in self.dead_indices)
            self.save_proxies_to_disk()
            print(
                f"[-] 🏷️ [PROKSI-GUARD] [BATCH-FLAG] {flagged_count} proksi mati ditandai 'dead' di proxies.json "
                f"(diskip saat seleksi). Proksi aktif tersisa: {alive_count}."
            )

    def get_valid_proxy(
        self,
        target_url: str = "https://blog.riztama.my.id",
        preferred_index: Optional[int] = None,
        worker_id: int = 1,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
        tag = f"[B{worker_id}]" if worker_id else "[*]"

        while True:
            candidate = None
            candidate_idx = None

            with self.test_lock:
                with self.lock:
                    total_px = len(self.proxies)
                    if total_px == 0:
                        return None, None

                    if preferred_index is not None and 0 <= preferred_index < total_px:
                        if (
                            preferred_index not in self.in_use_indices
                            and preferred_index not in self.dead_indices
                            and not self.proxies[preferred_index].get("dead", False)
                        ):
                            candidate_idx = preferred_index
                            candidate = self.proxies[candidate_idx]
                            self.in_use_indices.add(candidate_idx)

                    if candidate is None:
                        attempts = 0
                        while attempts < total_px:
                            idx = self.next_index % total_px
                            self.next_index = (self.next_index + 1) % total_px
                            attempts += 1

                            if (
                                idx not in self.in_use_indices
                                and idx not in self.dead_indices
                                and not self.proxies[idx].get("dead", False)
                            ):
                                candidate_idx = idx
                                candidate = self.proxies[candidate_idx]
                                self.in_use_indices.add(candidate_idx)
                                break

                        if candidate is None:
                            return None, None

                px_num = candidate_idx + 1
                h = candidate.get("host")
                p = int(candidate.get("port", 10080))
                country = candidate.get("country", "Global")

                print(f"{tag} 🔍 [PROKSI-TEST] [PX#{px_num}] Menguji kelayakan proksi #{px_num} {country} ({h}:{p}) sebelum dipakai...")
                is_alive, reason = self.check_proxy_alive(candidate, target_url=target_url, timeout=5.5)

                if is_alive:
                    print(f"{tag} ✅ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({h}:{p}) AKTIF & VALID ({reason})! Siap digunakan browser.")

                    with self.lock:
                        alive_count = sum(
                            1 for i, px in enumerate(self.proxies)
                            if i not in self.dead_indices and not px.get("dead", False)
                        )
                        if not self.initial_batch_pruned and len(self.in_use_indices) >= min(self.target_concurrency, alive_count):
                            self.initial_batch_pruned = True
                            if self.dead_indices:
                                self.prune_dead_proxies()

                    return candidate, candidate_idx
                else:
                    # PROKSI MATI: Flag "dead": true langsung di dict & simpan ke disk
                    with self.lock:
                        self.in_use_indices.discard(candidate_idx)
                        self.dead_indices.add(candidate_idx)
                        if 0 <= candidate_idx < len(self.proxies):
                            self.proxies[candidate_idx]["dead"] = True
                        self.save_proxies_to_disk()

                    print(f"{tag} ❌ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} {country} ({h}:{p}) MATI ({reason}). Di-flag dead di proxies.json!")

    def release_proxy(self, proxy_idx: Optional[int], worker_id: int = 1):
        if proxy_idx is None:
            return
        with self.lock:
            self.in_use_indices.discard(proxy_idx)
            tag = f"[B{worker_id}]" if worker_id else "[*]"
            px_num = proxy_idx + 1
            print(f"{tag} [*] [PX#{px_num}] Selesai digunakan, dikembalikan ke pool idle.")

    def mark_dead(self, proxy_idx: Optional[int], reason: str = ""):
        if proxy_idx is None:
            return
        with self.lock:
            self.in_use_indices.discard(proxy_idx)
            self.dead_indices.add(proxy_idx)
            px_num = proxy_idx + 1
            if 0 <= proxy_idx < len(self.proxies):
                self.proxies[proxy_idx]["dead"] = True
            print(f"[*] ❌ [PROKSI-TEST] [PX#{px_num}] Proksi #{px_num} MATI saat navigasi ({reason}). Di-flag dead di proxies.json.")
            self.save_proxies_to_disk()

    def remove_dead_proxy(self, proxy_dict_or_idx, reason: str = ""):
        if isinstance(proxy_dict_or_idx, int):
            self.mark_dead(proxy_dict_or_idx, reason)
        elif isinstance(proxy_dict_or_idx, dict):
            for idx, px in enumerate(self.proxies):
                if px == proxy_dict_or_idx:
                    self.mark_dead(idx, reason)
                    break
