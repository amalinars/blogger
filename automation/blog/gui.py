#!/usr/bin/env python3
"""
Chronicle Traffic Bot & Ad Impression Suite — Beginner-Friendly GUI Dashboard
Didesain khusus agar mudah dipahami, informatif, dan rapi untuk pengguna awam.
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QCheckBox, QSlider,
    QComboBox, QTextEdit, QGroupBox, QFrame, QGridLayout, QProgressBar,
    QTabWidget, QScrollArea, QSizePolicy, QDialog, QRadioButton, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QFont, QColor, QTextCursor, QIcon

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
PROXIES_PATH = BASE_DIR / "proxies.json" if (BASE_DIR / "proxies.json").exists() else BASE_DIR.parent / "proxies.json"


def load_config_data():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "target_base_url": "https://read.riztama.my.id",
        "local_test_url": "http://localhost:3000",
        "dwell_time": {"min_seconds": 35, "max_seconds": 55},
        "headless": False,
        "multi_page_navigation": True,
        "smartlink_click_chance": 0.08
    }


def load_proxies_data():
    if PROXIES_PATH.exists():
        try:
            with open(PROXIES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_proxies_data(proxies):
    """Atomic write agar proses bot yang sedang membaca file tidak melihat JSON setengah jadi."""
    temp_file = PROXIES_PATH.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(proxies, f, indent=2)
    temp_file.replace(PROXIES_PATH)


def parse_proxy_line(raw: str):
    """
    Parses proxy string format:
    geolocation://username:password@host:port:Country
    or http://username:password@host:port
    or host:port:username:password:Country
    """
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    
    clean = re.sub(r"^[a-zA-Z]+://", "", raw)
    if "@" in clean:
        creds, rest = clean.split("@", 1)
        u_p = creds.split(":", 1)
        username = u_p[0]
        password = u_p[1] if len(u_p) > 1 else ""
        rest_parts = rest.split(":")
        host = rest_parts[0]
        port = int(rest_parts[1]) if len(rest_parts) > 1 and rest_parts[1].isdigit() else 10080
        country = rest_parts[2] if len(rest_parts) > 2 else "Global"
    else:
        parts = clean.split(":")
        if len(parts) >= 4:
            host, port_s, username, password = parts[0], parts[1], parts[2], parts[3]
            port = int(port_s) if port_s.isdigit() else 10080
            country = parts[4] if len(parts) > 4 else "Global"
        else:
            return None

    return {
        "country": country.strip(),
        "connection_type": "residential",
        "host": host.strip(),
        "port": port,
        "username": username.strip(),
        "password": password.strip(),
        "proxy_url": f"http://{username.strip()}:{password.strip()}@{host.strip()}:{port}"
    }


class BotProcessWorker(QThread):
    # Signals to communicate cleanly with UI
    log_signal = Signal(str, str, str)  # timestamp, level, message
    status_signal = Signal(str, str)    # short_status, detailed_step
    session_progress_signal = Signal(int, int) # current, total
    proxy_info_signal = Signal(str, str) # country, host_port
    ad_action_signal = Signal(str)      # ad event notification
    worker_activity_signal = Signal(int, str) # worker_id, status (NAVIGATE, READING, ADS, IDLE)
    worker_flow_signal = Signal(int, dict)     # worker_id, flow_data_dict
    proxy_status_signal = Signal(object, str, str) # proxy_ref (int px_num or str host_port), status_type, extra
    proxy_pruned_signal = Signal(object, int)      # Emitted when dead proxies are pruned: (proxy_ref, remaining_count)
    finished_signal = Signal()

    def __init__(self, cmd_args):
        super().__init__()
        self.cmd_args = cmd_args
        self.process = None
        self._is_stopped = False

    def run(self):
        import subprocess

        self.status_signal.emit("RUNNING", "Menyiapkan browser Chromium & environment...")
        python_exec = sys.executable

        bot_script = BASE_DIR / "bot.py"
        if not bot_script.exists():
            bot_script = BASE_DIR / "traffic_bot.py"
        full_cmd = [python_exec, "-u", str(bot_script)] + self.cmd_args
        self.emit_log("INFO", f"Memulai bot engine: {' '.join(self.cmd_args) if self.cmd_args else 'Default Settings'}")

        try:
            self.process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(BASE_DIR.parent.parent)
            )

            for raw_line in iter(self.process.stdout.readline, ''):
                if self._is_stopped:
                    break
                line = raw_line.strip()
                if line:
                    try:
                        self.parse_line(line)
                    except Exception as parse_err:
                        self.emit_log("WARN", f"Log parser notice: {parse_err}")

            self.process.stdout.close()
            self.process.wait()

        except Exception as e:
            self.emit_log("ERROR", f"Terjadi kesalahan: {e}")
            self.status_signal.emit("ERROR", f"Error: {e}")
        finally:
            self.status_signal.emit("IDLE", "Bot selesai & siap digunakan kembali.")
            self.finished_signal.emit()

    def emit_log(self, level: str, msg: str, prefix: str = ""):
        now_str = datetime.now().strftime("%H:%M:%S")
        full_msg = f"{prefix}{msg}" if prefix else msg
        self.log_signal.emit(now_str, level, full_msg)

    def parse_line(self, line: str):
        # Ignore raw separator lines
        if line.startswith("=====") or line.startswith("-----") or "CHRONICLE TRAFFIC BOT" in line:
            return

        worker_prefix = ""
        w_id = 1
        import re
        match = re.match(r"^(\[B(\d+)\])\s*(.*)", line)
        if match:
            worker_prefix = match.group(1) + " "
            w_id = int(match.group(2))
            line = match.group(3)

            # Emit visual activity indicator for each specific browser worker
            if "Navigating to" in line or "Target Awal" in line or "Membuka browser" in line:
                self.worker_activity_signal.emit(w_id, "NAVIGATE")
            elif "Dwell time" in line:
                self.worker_activity_signal.emit(w_id, "DWELL")
            elif "Membaca artikel" in line or "Scroll" in line or "Artikel" in line:
                self.worker_activity_signal.emit(w_id, "READING")
            elif "TAB-GUARD" in line or "ad overlay" in line or "Smartlink" in line or "popunder" in line:
                self.worker_activity_signal.emit(w_id, "ADS")
            elif "Closing browser" in line or "selesai dinikmati" in line or "Clean shutdown" in line:
                self.worker_activity_signal.emit(w_id, "IDLE")

        def emit(lvl: str, txt: str):
            self.emit_log(lvl, txt, prefix=worker_prefix)

        # Extract proxy index tag if present e.g. [PX#1]
        m_px_num = re.search(r"\[PX#(\d+)\]", line)
        px_num = int(m_px_num.group(1)) if m_px_num else None
        px_hp = ""

        # Real-time On-Demand Just-In-Time Proxy Testing events
        if "[PROKSI-TEST]" in line:
            m_px = re.search(r"proksi\s+(?:#\d+\s+)?(.*?)\s*\((.*?):(\d+)\)", line, re.IGNORECASE)
            px_country = m_px.group(1).strip() if m_px else "Global"
            px_hp = f"{m_px.group(2)}:{m_px.group(3)}" if m_px else ""
            px_disp = f"#{px_num} {px_country}" if px_num else (f"{px_country} ({px_hp})" if px_hp else line)
            proxy_ref = px_num if px_num is not None else px_hp

            if "MATI" in line or "dihapus" in line:
                if proxy_ref:
                    self.proxy_status_signal.emit(proxy_ref, "DEAD", "Gagal / Timeout")
                self.worker_flow_signal.emit(w_id, {
                    "step": "PROXY_DEAD",
                    "status_text": "❌ Proksi Mati (Ganti)",
                    "proxy_str": px_disp
                })
                emit("WARN", line)
                return
            elif "AKTIF" in line or "VALID" in line:
                if proxy_ref:
                    self.proxy_status_signal.emit(proxy_ref, "VALID", "HTTP 200 OK")
                self.worker_flow_signal.emit(w_id, {
                    "step": "PROXY_OK",
                    "status_text": "✅ Proksi Lolos Uji",
                    "proxy_str": px_disp
                })
                emit("SUCCESS", line)
                return
            elif "Menguji" in line:
                if proxy_ref:
                    self.proxy_status_signal.emit(proxy_ref, "TESTING", f"Browser #{w_id}")
                self.worker_flow_signal.emit(w_id, {
                    "step": "PROXY",
                    "status_text": f"🔍 Menguji Proksi #{px_num}..." if px_num else "🔍 Menguji Proksi...",
                    "proxy_str": px_disp
                })
                emit("INFO", line)
                return
            elif "gagal" in line.lower() or "diistirahatkan" in line.lower():
                if proxy_ref:
                    self.proxy_status_signal.emit(proxy_ref, "COOLDOWN", "Belum mati")
                emit("WARN", line)
                return

        # Real-time Proxy-Guard events (Auto-flagging dead proxies)
        if "[PROKSI-GUARD]" in line:
            m_rem = re.search(r"tersisa:\s*(\d+)", line, re.IGNORECASE)
            px_remaining = int(m_rem.group(1)) if m_rem else 0

            # Jika ini BATCH-FLAG (seluruh worker sudah dapat proksi dan proksi mati di-flag sekaligus)
            if "[BATCH-FLAG]" in line:
                self.proxy_pruned_signal.emit(None, px_remaining)
                emit("WARN", line)
                return

            m_user = re.search(r"\[USER:([^\]]+)\]", line)
            px_user = m_user.group(1).strip() if m_user else None

            proxy_ref = px_num if px_num is not None else (px_user or (px_hp if px_hp else None))

            # Jika ini single dead proxy warning, tandai status saja tanpa mengubah baris tabel
            if proxy_ref:
                self.proxy_status_signal.emit(proxy_ref, "DEAD", "Di-flag Dead oleh Proxy-Guard")

            if "Di-flag dead" in line or "ditandai" in line:
                emit("WARN", line)
                return
            elif "Beralih otomatis ke Direct Connection" in line or "Seluruh proksi" in line:
                emit("WARN", line)
                return

        # Anti-Leak Guard trigger
        if "ANTI-LEAK GUARD" in line:
            self.status_signal.emit("ERROR", "Anti-Leak Guard: Sesi dibatalkan demi keamanan IP asli!")
            emit("WARN", line)
            return

        # Stealth fingerprint & geo profile info
        if "[STEALTH]" in line:
            emit("SUCCESS", line)
            return

        # Proksi dilepas kembali ke pool idle setelah sesi selesai
        if "dikembalikan ke pool idle" in line:
            if px_num is not None:
                self.proxy_status_signal.emit(px_num, "STANDBY", "")
            emit("INFO", line)
            return

        # Sesi indicator
        if ">>> Running Session" in line:
            try:
                parts = line.split("Session")[1].split("of")
                current = int(parts[0].strip())
                total = int(parts[1].replace("<<<", "").strip())
                self.session_progress_signal.emit(current, total)
                self.status_signal.emit("RUNNING", f"Menjalankan Sesi {current} dari {total}")
                self.worker_flow_signal.emit(w_id, {
                    "session": current,
                    "total_sessions": total,
                    "step": "START",
                    "status_text": f"Sesi {current}/{total}"
                })
                emit("SUCCESS", f"🚀 Memulai Sesi {current} dari total {total} sesi")
            except Exception:
                emit("INFO", line)
            return

        # Proxy identification
        if "[*] Proxy:" in line:
            proxy_str = line.replace("[*] Proxy:", "").strip()
            if "Direct" in proxy_str:
                self.proxy_info_signal.emit("Direct (Tanpa Proxy)", "-")
                self.worker_flow_signal.emit(w_id, {
                    "proxy_str": "Direct (Tanpa Proksi)"
                })
                emit("INFO", "🌐 Menggunakan koneksi langsung (Tanpa Proxy)")
            else:
                country = "Global"
                px_hp = ""
                m_g = re.search(r"(.*?):(\d+)", proxy_str)
                if m_g:
                    px_hp = f"{m_g.group(1).strip()}:{m_g.group(2).strip()}"
                if "Geo:" in proxy_str:
                    try:
                        country = proxy_str.split("Geo:")[1].replace(")", "").strip()
                    except Exception:
                        pass
                proxy_ref = px_num if px_num is not None else px_hp
                if proxy_ref:
                    self.proxy_status_signal.emit(proxy_ref, "IN_USE", f"Browser #{w_id}")
                self.proxy_info_signal.emit(country, proxy_str)
                self.worker_flow_signal.emit(w_id, {
                    "proxy_str": f"#{px_num} {country}" if px_num else (f"{country} ({px_hp})" if px_hp else proxy_str)
                })
                emit("INFO", f"🛡️ Browser #{w_id} Terhubung ke Proksi #{px_num if px_num else ''} ({country})")
            return

        # Navigation
        if "[*] Target Awal:" in line or "[*] Navigating to" in line:
            url = line.split("Target Awal:")[-1].strip() if "Target Awal:" in line else line.split("Navigating to")[-1].strip()
            self.status_signal.emit("SURFING", f"Membuka halaman: {url}")
            self.worker_flow_signal.emit(w_id, {
                "step": "LANDING",
                "status_text": "🌐 Membuka Beranda",
                "url": url
            })
            emit("INFO", f"🌐 Membuka halaman web: {url}")
            return

        # Initial click / Popunder trigger
        if "physical mouse click at coordinates" in line or "Hits ad overlay" in line:
            self.status_signal.emit("ADS", "Memicu klik pertama (Membuka Popunder)...")
            self.worker_flow_signal.emit(w_id, {
                "step": "ADS",
                "status_text": "💥 Viewability / Popunder"
            })
            emit("POPUP", "💥 Melakukan klik koordinat alami untuk mengaktifkan Popunder")
            return

        # Strict Single-Tab Guard & Ad tabs cleanup
        if "[TAB-GUARD]" in line or "tab tambahan" in line or "Menutup tab smartlink" in line:
            if "Terdeteksi" in line:
                self.status_signal.emit("ADS", "Tab smartlink/iklan terdeteksi...")
                emit("ADS", "💥 Terdeteksi tab iklan/smartlink baru terbuka! Diberi jeda agar impresi tercatat...")
            elif "Menutup tab" in line:
                tab_url = line.split("Menutup tab smartlink/iklan:")[-1].strip(" .")
                emit("CLEAN", f"🧹 Menutup tab iklan otomatis: {tab_url}")
            elif "Hanya 1 tab aktif tersisa" in line:
                self.status_signal.emit("SURFING", "Fokus dikembalikan ke domain target.")
                emit("SUCCESS", "✅ Tab iklan ditutup bersih. Hanya 1 tab domain target aktif!")
            return

        # Legacy tab catch
        if "Detected" in line and "extra ad/smartlink tab" in line:
            try:
                count = line.split("Detected")[1].split("extra")[0].strip()
                self.status_signal.emit("ADS", f"Menunggu iklan tercatat ({count} tab iklan)...")
                emit("ADS", f"👁️ Terdeteksi {count} tab iklan baru. Diberi waktu agar impresi tercatat...")
            except Exception:
                pass
            return

        if "Closing ad tab" in line:
            tab_url = line.split("Closing ad tab")[-1].strip().strip("().")
            emit("CLEAN", f"🧹 Menutup tab iklan otomatis: {tab_url[:45]}...")
            return

        if "All extra ad tabs closed cleanly" in line or ("[✓]" in line and "closed" in line):
            self.status_signal.emit("SURFING", "Fokus kembali ke artikel blog.")
            emit("SUCCESS", "✅ Semua tab iklan ditutup bersih. Layar kembali fokus membaca artikel.")
            return

        # Scroll behavior
        if "[BERANDA] Menjelajahi Beranda santai" in line:
            self.status_signal.emit("READING", "Scroll santai di Beranda (Viewability)...")
            self.worker_flow_signal.emit(w_id, {
                "step": "LANDING",
                "status_text": "📜 Scroll Iklan Beranda"
            })
            emit("SCROLL", "📜 Menjelajahi Beranda santai agar seluruh banner iklan terlihat")
            return

        if "Scroll Beranda selesai" in line:
            self.worker_flow_signal.emit(w_id, {
                "step": "LANDING",
                "status_text": "✨ Iklan Beranda Dirender"
            })
            emit("SUCCESS", "✨ Seluruh posisi banner iklan di Beranda telah selesai dilihat!")
            return

        if "[BERANDA FEED] Menjelajahi kembali feed Beranda" in line:
            self.status_signal.emit("READING", "Scroll feed Beranda (Refresh Iklan)...")
            self.worker_flow_signal.emit(w_id, {
                "step": "LANDING",
                "status_text": "🏠 Refresh Iklan Beranda"
            })
            emit("SCROLL", "📜 Menjelajahi kembali feed Beranda santai agar seluruh posisi iklan ter-refresh")
            return

        if "Membaca artikel perlahan" in line or "Starting organic reading scroll" in line:
            self.status_signal.emit("READING", "Scroll membaca artikel (Viewability)...")
            emit("SCROLL", "📜 Membaca artikel perlahan ke bawah agar semua banner iklan masuk viewport")
            return

        if "Scroll artikel selesai" in line or "Scroll segment completed" in line:
            self.worker_flow_signal.emit(w_id, {
                "step": "ADS",
                "status_text": "✨ Iklan Selesai Dirender"
            })
            emit("SUCCESS", "✨ Seluruh posisi banner iklan di halaman telah selesai dilihat!")
            return

        # Smartlink CTA
        if "SMARTLINK BERANDA" in line:
            self.status_signal.emit("SMARTLINK", "Berinteraksi dengan Smartlink di Beranda...")
            self.worker_flow_signal.emit(w_id, {
                "step": "SMARTLINK",
                "status_text": "🎯 Smartlink Beranda"
            })
            emit("CLICK", "🎯 Melakukan interaksi klik pada tombol Smartlink/CTA di Beranda")
            return

        if "Tab smartlink telah ditutup bersih" in line or "Menutup tab smartlink bersih" in line:
            self.worker_flow_signal.emit(w_id, {
                "step": "ADS",
                "status_text": "🧹 Tab Smartlink Ditutup"
            })
            emit("CLEAN", "🧹 Tab Smartlink ditutup bersih. Layar kembali fokus di artikel untuk dwell time.")
            return

        if "Tab iklan/smartlink terbuka" in line:
            m_sec = re.search(r"\((\d+)s\)", line)
            ad_rem = int(m_sec.group(1)) if m_sec else 18
            self.status_signal.emit("SMARTLINK", f"Membaca landing page pengiklan ({ad_rem}s)...")
            self.worker_flow_signal.emit(w_id, {
                "step": "SMARTLINK",
                "status_text": f"🎯 Dwell Iklan ({ad_rem}s)",
                "dwell_seconds": ad_rem,
                "dwell_label": "Dwell Iklan"
            })
            emit("ADS", f"💥 {line}")
            return

        if "Smartlink ad dwell remaining:" in line:
            m_sec = re.search(r"remaining:\s*(\d+)", line)
            if m_sec:
                ad_rem = int(m_sec.group(1))
                self.worker_flow_signal.emit(w_id, {
                    "step": "SMARTLINK",
                    "status_text": f"🎯 Dwell Iklan ({ad_rem}s)",
                    "dwell_seconds": ad_rem,
                    "dwell_label": "Dwell Iklan"
                })
            return

        if "SMARTLINK" in line and ("Engaging with Smartlink" in line or "Physically clicking Smartlink" in line or "Organic roll SUCCESS" in line):
            self.status_signal.emit("SMARTLINK", "Berinteraksi dengan tombol Smartlink...")
            self.worker_flow_signal.emit(w_id, {
                "step": "SMARTLINK",
                "status_text": "🎯 Klik Smartlink CTA"
            })
            emit("CLICK", "🎯 Melakukan interaksi klik pada link Smartlink dengan jeda aman")
            return

        # Dwell time
        if "Dwell time" in line and any(k in line for k in ["aktif", "remaining", "di Beranda", "di Artikel"]):
            try:
                m_sec = re.search(r"(?:aktif|remaining|di Beranda|di Artikel|Dwell time.*?):\s*(\d+)", line, re.IGNORECASE)
                rem = int(m_sec.group(1)) if m_sec else 30
                is_beranda = "Beranda" in line
                dwell_label = "Dwell Beranda" if is_beranda else "Dwell Time"
                step_key = "DWELL_BERANDA" if is_beranda else "DWELL"

                self.status_signal.emit("DWELL", f"Menunggu auto-refresh iklan ({rem}s)...")
                self.worker_flow_signal.emit(w_id, {
                    "step": step_key,
                    "status_text": f"⏳ {dwell_label} ({rem}s)",
                    "dwell_seconds": rem,
                    "dwell_label": dwell_label
                })

                if "remaining:" in line:
                    if rem % 10 == 0 or rem <= 5:
                        emit("TIMER", f"⏳ {dwell_label} tersisa: {rem} detik...")
                else:
                    emit("TIMER", f"⏳ {dwell_label}: {rem} detik (Membaca santai & scrolling naik-turun)")
            except Exception:
                pass
            return

        if "Dwell time selesai" in line:
            self.worker_flow_signal.emit(w_id, {
                "step": "DWELL_DONE",
                "status_text": "⌛ Dwell Selesai",
                "dwell_seconds": 0
            })
            emit("TIMER", "⌛ Dwell time selesai. Melanjutkan flow...")
            return

        # Multi-Hop exploration indicators
        if "[Artikel" in line or ">>> [HOP" in line:
            try:
                m_art = re.search(r"\[Artikel\s+(\d+)/(\d+)\]", line)
                if m_art:
                    hop_num = int(m_art.group(1))
                    tot = int(m_art.group(2))
                    url = line.split("Membaca artikel:")[-1].replace("<<<", "").strip() if "Membaca artikel:" in line else ""
                    self.status_signal.emit("SURFING", f"Membaca Artikel {hop_num} dari {tot}")
                    self.worker_flow_signal.emit(w_id, {
                        "step": "ARTICLE",
                        "hop": hop_num,
                        "status_text": f"📖 Artikel {hop_num}/{tot}",
                        "url": url
                    })
                    emit("PAGE2", f"📖 <b>[Artikel {hop_num}/{tot}]</b> Membaca artikel: {url}")
                    return
                elif "[HOP" in line:
                    parts = line.split("[HOP")[1].split("]")[0].strip()
                    m_h = re.search(r"(\d+)", parts)
                    hop_num = int(m_h.group(1)) if m_h else 1
                    url = line.split("Aktif di:")[-1].replace("<<<", "").strip() if "Aktif di:" in line else ""
                    self.status_signal.emit("SURFING", f"Hop {parts}: {url}")
                    self.worker_flow_signal.emit(w_id, {
                        "step": "ARTICLE",
                        "hop": hop_num,
                        "status_text": f"📖 Membaca Artikel {hop_num}",
                        "url": url
                    })
                    emit("PAGE2", f"📖 <b>[HOP {parts}]</b> Menjelajahi artikel: {url}")
                    return
            except Exception:
                pass

        if "Pola Pembaca Organik: Kembali ke Beranda" in line:
            self.status_signal.emit("SURFING", "Kembali ke Beranda...")
            self.worker_flow_signal.emit(w_id, {
                "step": "LANDING",
                "status_text": "🏠 Kembali ke Beranda",
                "url": "Beranda"
            })
            emit("INFO", "🏠 Pola Pembaca Organik: Kembali ke Beranda sebelum memilih artikel baru...")
            return

        if "Melihat daftar feed di Beranda" in line:
            emit("SCROLL", "📜 Melihat daftar feed di Beranda (Iklan Feed terpicu)")
            return

        if "Memilih artikel #" in line or "Memilih artikel baru untuk dijelajahi" in line:
            art = line.split(":")[-1].strip()
            self.status_signal.emit("NAVIGATE", f"Membuka artikel: {art}")
            self.worker_flow_signal.emit(w_id, {
                "status_text": "➡️ Membuka Artikel..."
            })
            emit("CLICK", f"➡️ Memilih & mengklik artikel: {art}")
            return

        # Multi-page internal click (legacy fallback)
        if "Moving physical mouse to link coordinates" in line:
            target_link = line.split("coordinates:")[-1].strip()
            self.status_signal.emit("NAVIGATE", "Membuka artikel berikutnya...")
            emit("PAGE2", f"➡️ Membaca artikel berikutnya: {target_link}")
            return

        # Cooldown between sessions
        if "Cooling down for" in line:
            m_cd = re.search(r"for\s+(\d+)s", line)
            cd = int(m_cd.group(1)) if m_cd else 5
            self.status_signal.emit("COOLDOWN", f"Istirahat {cd} detik sebelum sesi berikutnya...")
            self.worker_flow_signal.emit(w_id, {
                "step": "COOLDOWN",
                "status_text": f"☕ Cooldown ({cd}s)",
                "dwell_seconds": cd,
                "dwell_label": "Cooldown"
            })
            emit("TIMER", f"☕ Jeda antar sesi: {cd} detik agar pola lalu lintas tampak alami")
            return

        if "MEMULAI PUTARAN KE-" in line:
            cycle_text = line.replace("=", "").strip()
            self.status_signal.emit("RUNNING", cycle_text)
            emit("SUCCESS", f"🔁 <b>{cycle_text}</b>")
            return

        if "Putaran" in line and "selesai" in line and "Istirahat" in line:
            self.status_signal.emit("COOLDOWN", "Putaran selesai, istirahat sejenak...")
            emit("TIMER", f"☕ {line}")
            return

        if "Closing browser session cleanly" in line or "Clean shutdown" in line:
            self.worker_flow_signal.emit(w_id, {
                "step": "DONE",
                "status_text": "✅ Sesi Selesai (Tutup Browser)"
            })
            emit("INFO", "🔒 Menutup sesi browser dan merapikan resource...")
            return

        if "All automation sessions completed successfully" in line:
            self.status_signal.emit("DONE", "Semua sesi telah selesai dengan sukses!")
            emit("SUCCESS", "🎉 SEMUA SESI OTOMASI TELAH SELESAI DENGAN SUKSES!")
        # Diagnostic & Resilience notices (HOLD, RECOVERY, ERROR, NAV-FALLBACK, etc.)
        if "HOLD/RECOVERY" in line or "RECOVERY" in line:
            self.worker_flow_signal.emit(w_id, {
                "status_text": "🔄 Pemulihan Halaman..."
            })
            emit("WARN", f"🔄 {line}")
            return

        if "HOLD/ERROR" in line or "RECOVERY-ERROR" in line:
            emit("WARN", f"❌ {line}")
            return

        if "NAV-FALLBACK" in line or "NAV-NOTICE" in line:
            emit("INFO", f"🧭 {line}")
            return

        if any(tag in line for tag in ["SCROLL-NOTICE", "CLICK-NOTICE", "DWELL-NOTICE", "TAB-GUARD-NOTICE"]):
            emit("WARN", f"⚠️ {line}")
            return

        # Default fallback
        if line.startswith("[+]"):
            emit("SUCCESS", line[3:].strip())
        elif line.startswith("[-]"):
            emit("WARN", line[3:].strip())
        elif line.startswith("[*]"):
            emit("INFO", line[3:].strip())
        else:
            emit("RAW", line)

    def stop(self):
        self._is_stopped = True
        if self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass


class ProxyImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah / Import Proksi Residensial")
        self.resize(650, 500)
        self.setMinimumSize(550, 400)
        self.parent_gui = parent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Title & Info
        title = QLabel("📥 IMPORT PROKSI RESIDENSIAL")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: #38bdf8;")
        layout.addWidget(title)

        info = QLabel(
            "Paste daftar proksi Anda di kotak bawah (1 baris per proksi).\n"
            "Format yang didukung secara otomatis:\n"
            "• geolocation://username:password@geo.floppydata.com:10080:United States\n"
            "• http://username:password@host:port (atau host:port:user:pass:Negara)"
        )
        info.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        layout.addWidget(info)

        # Text Area
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "geolocation://1ttpkYiRqmq9gNS0:wlIhn8AYGUYJCQtc@geo.floppydata.com:10080:United States\n"
            "geolocation://jGRG7GDmHiJgw22W:UvWkVbu6ND5BsfhI@geo.floppydata.com:10080:United Kingdom\n"
            "geolocation://rEWlQ6pzh4I5qGC0:yEjvzp3pnfzvbYXm@geo.floppydata.com:10080:France\n"
            "geolocation://oR0BacOMZvtBCpmS:xG03ZukcawtUFTmu@geo.floppydata.com:10080:Canada\n"
            "geolocation://hatZkebSAhtKH0yW:7vvzNNQj0SzrVboj@geo.floppydata.com:10080:Australia"
        )
        self.text_edit.setFont(QFont("Monospace", 9))
        self.text_edit.setObjectName("TerminalBox")
        self.text_edit.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.text_edit)

        # Counter Label
        self.count_lbl = QLabel("0 proksi valid terdeteksi.")
        self.count_lbl.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 11px;")
        layout.addWidget(self.count_lbl)

        # Options: Append or Replace
        opt_layout = QHBoxLayout()
        self.append_radio = QRadioButton("Tambahkan ke daftar yang ada (Append)")
        self.append_radio.setChecked(True)
        self.replace_radio = QRadioButton("Ganti seluruh daftar lama (Replace all)")
        opt_layout.addWidget(self.append_radio)
        opt_layout.addWidget(self.replace_radio)
        opt_layout.addStretch()
        layout.addLayout(opt_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Batal")
        self.cancel_btn.setObjectName("SecondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("💾 Simpan & Perbarui Proksi")
        self.save_btn.setObjectName("QuickTestBtn")
        self.save_btn.clicked.connect(self.save_proxies)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def on_text_changed(self):
        text = self.text_edit.toPlainText().strip()
        lines = [l for l in text.splitlines() if l.strip()]
        valid = [l for l in lines if parse_proxy_line(l) is not None]
        self.count_lbl.setText(f"✅ {len(valid)} proksi valid terdeteksi dari {len(lines)} baris.")
        if len(valid) > 0:
            self.count_lbl.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
        else:
            self.count_lbl.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 11px;")

    def save_proxies(self):
        text = self.text_edit.toPlainText().strip()
        parsed = []
        for line in text.splitlines():
            item = parse_proxy_line(line)
            if item:
                parsed.append(item)

        if not parsed:
            QMessageBox.warning(self, "Peringatan", "Tidak ada proksi valid yang terdeteksi dari teks yang dimasukkan.")
            return

        current_proxies = load_proxies_data()
        if self.append_radio.isChecked():
            existing_usernames = {px.get("username") for px in current_proxies}
            added_count = 0
            for p in parsed:
                if p["username"] not in existing_usernames:
                    current_proxies.append(p)
                    existing_usernames.add(p["username"])
                    added_count += 1
            final_list = current_proxies
            msg = f"Berhasil menambahkan {added_count} proksi baru! Total: {len(final_list)} proksi."
        else:
            final_list = parsed
            msg = f"Berhasil mengganti seluruh daftar dengan {len(final_list)} proksi baru!"

        try:
            save_proxies_data(final_list)

            if self.parent_gui:
                self.parent_gui.reload_proxies_ui()
                self.parent_gui.on_log_received(
                    datetime.now().strftime("%H:%M:%S"),
                    "SUCCESS",
                    f"🛡️ [PROKSI] {msg}"
                )

            QMessageBox.information(self, "Berhasil", msg)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Gagal Menyimpan", f"Error saat menyimpan file: {e}")


class ProxyTesterWorker(QThread):
    result_signal = Signal(int, dict)  # index, result_dict
    target_guard_signal = Signal(bool, str)  # target_ok, reason
    finished_signal = Signal(int, int, float, list)  # alive_count, dead_count, avg_latency, alive_list

    def __init__(self, proxies, target_url="https://read.riztama.my.id", timeout=8.0, max_threads=1):
        super().__init__()
        self.proxies = proxies
        self.target_url = target_url
        self.timeout = timeout
        self.max_threads = max_threads
        self._is_stopped = False

    def run(self):
        from automation.test_proxies import check_target_direct, test_proxy_http
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(self.proxies)
        if total == 0:
            self.finished_signal.emit(0, 0, 0.0, [])
            return

        target_ok, target_reason = check_target_direct(self.target_url, timeout=6.0)
        self.target_guard_signal.emit(target_ok, target_reason)

        alive_list = []
        dead_count = 0
        total_latency = 0.0

        max_workers = max(1, min(self.max_threads, total))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        futures = {
            executor.submit(test_proxy_http, px, self.target_url, self.timeout): (idx + 1, px)
            for idx, px in enumerate(self.proxies)
        }

        try:
            for fut in as_completed(futures):
                if self._is_stopped:
                    break
                idx, orig_px = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {
                        "host": orig_px.get("host", ""),
                        "port": orig_px.get("port", ""),
                        "country": orig_px.get("country", "Unknown"),
                        "http_ok": False,
                        "latency_ms": 0,
                        "error": str(e),
                    }

                if res.get("http_ok"):
                    alive_list.append(orig_px)
                    total_latency += res.get("latency_ms", 0.0)
                else:
                    dead_count += 1

                self.result_signal.emit(idx, res)
        finally:
            for fut in futures:
                fut.cancel()
            executor.shutdown(wait=True)

        if not self._is_stopped and dead_count > 0:
            final_ok, final_reason = check_target_direct(self.target_url, timeout=6.0)
            self.target_guard_signal.emit(final_ok, final_reason)

        alive_count = len(alive_list)
        avg_latency = (total_latency / alive_count) if alive_count > 0 else 0.0
        self.finished_signal.emit(alive_count, dead_count, avg_latency, alive_list)

    def stop(self):
        self._is_stopped = True


class ProxyTestDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pengujian Koneksi Proksi Residensial")
        self.resize(720, 520)
        self.setMinimumSize(600, 420)
        self.parent_gui = parent
        self.worker = None
        self.alive_proxies = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        # Title
        title = QLabel("⚡ PENGUJIAN KONEKSI PROKSI")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: #38bdf8;")
        layout.addWidget(title)

        info = QLabel("Uji apakah server proksi Anda aktif dan bisa membuka web target (https://read.riztama.my.id).")
        info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(info)

        speed_row = QHBoxLayout()
        speed_lbl = QLabel("Parallel:")
        speed_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        speed_row.addWidget(speed_lbl)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 10)
        self.threads_spin.setValue(4)
        self.threads_spin.setSuffix(" worker")
        self.threads_spin.setFixedWidth(100)
        self.threads_spin.setToolTip("Jumlah proxy yang diuji bersamaan. 1 = paling aman/linear, 4 = lebih cepat.")
        speed_row.addWidget(self.threads_spin)
        speed_row.addStretch()
        layout.addLayout(speed_row)

        # Status & Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        self.summary_lbl = QLabel("Tekan tombol 'Mulai Tes' di bawah untuk mengecek status proksi.")
        self.summary_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.summary_lbl)

        # Result Terminal Box
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Monospace", 9))
        self.result_text.setObjectName("TerminalBox")
        layout.addWidget(self.result_text)

        # Auto prune checkbox
        self.auto_prune_check = QCheckBox("🧹 Hapus permanen proksi yang benar-benar mati (hanya hasil tes penuh)")
        self.auto_prune_check.setChecked(False)
        self.auto_prune_check.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold; margin-top: 4px;")
        layout.addWidget(self.auto_prune_check)

        # Buttons
        btn_layout = QHBoxLayout()
        self.test_all_btn = QPushButton("▶️ Mulai Tes Semua Proksi")
        self.test_all_btn.setObjectName("QuickTestBtn")
        self.test_all_btn.clicked.connect(lambda: self.start_testing(limit=None))

        self.test_fast_btn = QPushButton("⚡ Tes Cepat (10 Sampel)")
        self.test_fast_btn.setObjectName("SecondaryBtn")
        self.test_fast_btn.clicked.connect(lambda: self.start_testing(limit=10))

        self.save_alive_btn = QPushButton("💾 Simpan Hanya Proksi Hidup")
        self.save_alive_btn.setObjectName("SecondaryBtn")
        self.save_alive_btn.setEnabled(False)
        self.save_alive_btn.clicked.connect(self.save_alive_only)

        self.stop_btn = QPushButton("⏹️ Stop Tes")
        self.stop_btn.setObjectName("SecondaryBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_testing)

        self.close_btn = QPushButton("Tutup")
        self.close_btn.setObjectName("SecondaryBtn")
        self.close_btn.clicked.connect(self.close)

        btn_layout.addWidget(self.test_all_btn)
        btn_layout.addWidget(self.test_fast_btn)
        btn_layout.addWidget(self.save_alive_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def start_testing(self, limit=None):
        proxies = load_proxies_data()
        if not proxies:
            QMessageBox.warning(self, "Peringatan", "Tidak ada proksi di dalam daftar (proxies.json kosong).")
            return

        self.target_ok = True
        self.target_reason = "Memeriksa target..."

        self.is_limited_test = bool(limit)
        if limit:
            proxies = proxies[:limit]
        self.tested_snapshot = list(proxies)

        self.total_to_test = len(proxies)
        self.tested_count = 0
        self.alive_count = 0
        self.dead_count = 0
        self.payment_error_count = 0
        self.alive_proxies = []
        self.was_stopped = False

        self.result_text.clear()
        self.progress_bar.setRange(0, self.total_to_test)
        self.progress_bar.setValue(0)
        self.test_all_btn.setEnabled(False)
        self.test_fast_btn.setEnabled(False)
        self.save_alive_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.threads_spin.setEnabled(False)
        self.summary_lbl.setText("Memeriksa kesehatan target...")

        self.worker = ProxyTesterWorker(
            proxies,
            timeout=6.0,
            max_threads=self.threads_spin.value(),
        )
        self.worker.target_guard_signal.connect(self.on_target_guard)
        self.worker.result_signal.connect(self.on_proxy_result)
        self.worker.finished_signal.connect(self.on_testing_finished)
        self.worker.start()

    def on_target_guard(self, ok: bool, reason: str):
        self.target_ok = ok
        self.target_reason = reason
        if ok:
            if self.tested_count == 0:
                self.summary_lbl.setText(f"Target OK. Menguji {self.total_to_test} proksi...")
            return

        self.result_text.append(
            f"<div style='color:#facc15;'><b>[TARGET-GUARD]</b> Target tidak merespons 200 OK "
            f"secara langsung ({reason}). Hasil gagal TIDAK dihitung sebagai proxy mati dan "
            "auto-prune dibatalkan.</div>"
        )
        if self.tested_count == 0:
            self.summary_lbl.setText(f"Target tidak sehat. Menguji {self.total_to_test} proksi untuk diagnosa...")

    def on_proxy_result(self, idx: int, res: dict):
        self.tested_count += 1
        self.progress_bar.setValue(self.tested_count)

        host_port = f"{res.get('host')}:{res.get('port')}"
        country = res.get("country", "Unknown")
        lat = f"{res.get('latency_ms', 0):.0f}ms"

        if res.get("http_ok"):
            self.alive_count += 1
            line = f"<div style='margin-bottom:2px; color:#4ade80;'>✅ #{idx} [{country}] {host_port} - OK ({lat})</div>"
        else:
            err = res.get("error", "Gagal")
            if "402" in err:
                self.payment_error_count += 1
            if self.target_ok:
                self.dead_count += 1
                line = f"<div style='margin-bottom:2px; color:#f43f5e;'>❌ #{idx} [{country}] {host_port} - MATI ({err})</div>"
            else:
                line = f"<div style='margin-bottom:2px; color:#facc15;'>⚠️ #{idx} [{country}] {host_port} - GAGAL, target tidak sehat ({err})</div>"

        self.result_text.append(line)
        self.result_text.moveCursor(QTextCursor.End)
        self.summary_lbl.setText(
            f"Progress: {self.tested_count}/{self.total_to_test} | "
            f"✅ {self.alive_count} Hidup | ❌ {self.dead_count} Mati"
        )

    def _merge_proxy_test_results(self, tested_snapshot: list, alive_list: list) -> list:
        """
        Menghapus hanya proksi yang benar-benar diuji dan gagal.
        Proksi baru yang ditambahkan saat tes berjalan tetap dipertahankan.
        """
        current = load_proxies_data()
        tested_keys = {(str(px.get("host", "")).lower(), str(px.get("port", "")), str(px.get("username", ""))) for px in tested_snapshot}
        alive_keys = {(str(px.get("host", "")).lower(), str(px.get("port", "")), str(px.get("username", ""))) for px in alive_list}
        merged = []
        for px in current:
            key = (str(px.get("host", "")).lower(), str(px.get("port", "")), str(px.get("username", "")))
            if key in tested_keys:
                if key in alive_keys:
                    clean = dict(px)
                    clean.pop("dead", None)
                    merged.append(clean)
            else:
                merged.append(px)
        return merged

    def on_testing_finished(self, alive: int, dead: int, avg_lat: float, alive_list: list):
        self.test_all_btn.setEnabled(True)
        self.test_fast_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.threads_spin.setEnabled(True)
        self.alive_proxies = alive_list

        completed = (
            not self.was_stopped
            and self.total_to_test > 0
            and self.tested_count >= self.total_to_test
        )
        full_test = completed and not self.is_limited_test

        if not completed:
            self.result_text.append(
                f"<br><span style='color:#facc15;'><b>[STOP]</b> Tes dihentikan setelah "
                f"{self.tested_count}/{self.total_to_test} proksi. Auto-prune dibatalkan agar "
                "proksi yang belum diuji tidak ikut terhapus.</span>"
            )

        if getattr(self, "auto_prune_check", None) and self.auto_prune_check.isChecked() and full_test and self.target_ok and dead > 0:
            backup_file = PROXIES_PATH.parent / "proxies_backup.json"
            if not backup_file.exists() and PROXIES_PATH.exists():
                try:
                    import shutil
                    shutil.copy2(PROXIES_PATH, backup_file)
                except Exception:
                    pass
            try:
                merged = self._merge_proxy_test_results(getattr(self, "tested_snapshot", []), alive_list)
                save_proxies_data(merged)
                if self.parent_gui:
                    self.parent_gui.reload_proxies_ui()
                self.result_text.append(f"<br><span style='color:#38bdf8;'><b>🧹 [AUTO-PRUNE]</b> {dead} proksi mati telah dihapus dari proxies.json. (Sisa: {len(merged)} proksi aktif). Salinan cadangan aman di proxies_backup.json.</span>")
            except Exception as e:
                self.result_text.append(f"<br><span style='color:#f43f5e;'>[-] Gagal auto-prune file proksi: {e}</span>")

        if not self.target_ok:
            self.save_alive_btn.setEnabled(False)
            self.summary_lbl.setText(
                f"⚠️ Tes selesai, tetapi target tidak sehat. ✅ {alive} lolos | "
                f"⚠️ {self.tested_count - alive} gagal (tidak dihitung mati)"
            )
            self.summary_lbl.setStyleSheet("color: #facc15; font-size: 11px; font-weight: bold;")
            self.result_text.append(
                "<br><b style='color:#facc15;'>[TARGET-GUARD] Hasil tidak valid untuk menghapus proxy. "
                "Cek target/Cloudflare lalu tes ulang.</b>"
            )
            return

        if not completed:
            self.save_alive_btn.setEnabled(False)
            self.summary_lbl.setText(
                f"⏹️ Tes dihentikan: {self.tested_count}/{self.total_to_test} diuji | "
                f"✅ {alive} Hidup | ❌ {dead} Mati"
            )
            self.summary_lbl.setStyleSheet("color: #facc15; font-size: 11px; font-weight: bold;")
            if self.payment_error_count > 0:
                self.result_text.append(
                    "<br><b style='color:#facc15;'>[PROXY-BILLING] Sebagian proxy ditolak 402 "
                    "Payment Required (saldo/akun provider habis).</b>"
                )
            return

        if self.payment_error_count > 0 and self.payment_error_count == dead:
            self.summary_lbl.setText(
                f"⚠️ Semua {dead} proxy ditolak 402 Payment Required (saldo/akun provider habis)"
            )
            self.summary_lbl.setStyleSheet("color: #facc15; font-size: 11px; font-weight: bold;")
            self.result_text.append(
                "<br><b style='color:#facc15;'>[PROXY-BILLING] 402 bukan bug tes dan bukan target down. "
                "Top up saldo/akun FloppyData, lalu tes ulang sebelum menghapus proxy.</b>"
            )
            self.save_alive_btn.setEnabled(completed and alive > 0)
            return

        if alive > 0:
            self.save_alive_btn.setEnabled(completed)
            self.summary_lbl.setText(f"🎉 Pengujian Selesai: ✅ {alive} Hidup ({avg_lat:.0f}ms) | ❌ {dead} Mati")
            self.summary_lbl.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
        else:
            self.save_alive_btn.setEnabled(False)
            self.summary_lbl.setText(f"⚠️ Pengujian Selesai: ❌ Semua {dead} Proksi MATI / DOWN!")
            self.summary_lbl.setStyleSheet("color: #f43f5e; font-size: 11px; font-weight: bold;")
            self.result_text.append("<br><b style='color:#facc15;'>[PANDUAN] Server proksi tidak merespons (FloppyData down). Solusi: Hilangkan centang 'Gunakan Proksi Residensial' di Dashboard untuk menjalankan bot secara langsung tanpa hambatan.</b>")

    def stop_testing(self):
        if self.worker and self.worker.isRunning():
            self.was_stopped = True
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            self.summary_lbl.setText(
                f"Menghentikan tes... ({self.tested_count}/{self.total_to_test} selesai)"
            )

    def save_alive_only(self):
        if not self.alive_proxies:
            return
        if not getattr(self, "target_ok", False):
            QMessageBox.warning(
                self,
                "Target Tidak Sehat",
                "Hasil tes tidak valid karena target tidak merespons 200 OK. Tes ulang dulu.",
            )
            return
        if getattr(self, "was_stopped", False) or self.tested_count < self.total_to_test:
            QMessageBox.warning(
                self,
                "Tes Belum Selesai",
                "Tes dihentikan sebelum semua proxy diuji. Jalankan tes penuh dulu agar "
                "proxy yang belum diuji tidak ikut terhapus.",
            )
            return
        try:
            merged = self._merge_proxy_test_results(getattr(self, "tested_snapshot", []), self.alive_proxies)
            save_proxies_data(merged)
            if self.parent_gui:
                self.parent_gui.reload_proxies_ui()
            QMessageBox.information(self, "Berhasil", f"Berhasil menyimpan {len(merged)} proksi aktif ke proxies.json!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal menyimpan: {e}")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.was_stopped = True
            self.auto_prune_check.setChecked(False)
            self.worker.stop()
            if not self.worker.wait(15000):
                QMessageBox.information(
                    self,
                    "Masih Menghentikan Tes",
                    "Proxy yang sedang diuji belum selesai. Tunggu sebentar lalu tutup lagi.",
                )
                event.ignore()
                return
        event.accept()


def generate_flow_steps(max_pages: int = 3, has_smartlink: bool = True):
    steps = ["Proksi", "Beranda"]
    for i in range(1, max(1, max_pages) + 1):
        steps.append(f"Art {i}")
    if has_smartlink:
        steps.append("Smartlink")
    steps.append("Dwell")
    steps.append("Selesai")
    return steps


def get_step_index(step_key: str, hop: int, max_pages: int, has_smartlink: bool = True) -> int:
    if step_key in ("PROXY", "PROXY_TEST"):
        return 0
    if step_key in ("PROXY_OK", "LANDING", "DWELL_BERANDA", "BERANDA"):
        return 1
    if step_key in ("ADS", "ARTICLE"):
        h = max(1, min(hop or 1, max_pages))
        return 1 + h
    if step_key == "SMARTLINK":
        return 2 + max_pages if has_smartlink else 2 + max_pages
    if step_key in ("DWELL", "DWELL_DONE"):
        return 2 + max_pages + (1 if has_smartlink else 0)
    if step_key in ("DONE", "COOLDOWN", "CLOSING"):
        return 3 + max_pages + (1 if has_smartlink else 0)
    return -1


class StepperBar(QWidget):
    """
    Horizontal Stepper Bar showing sequential flow execution with glowing active state.
    """
    def __init__(self, steps=None, parent=None):
        super().__init__(parent)
        self.steps = steps or ["Proksi", "Beranda", "Art 1", "Art 2", "Art 3", "Smartlink", "Dwell", "Selesai"]
        self.current_step = -1
        self.step_widgets = []
        self.init_ui()

    def set_steps(self, steps):
        self.steps = steps
        self.current_step = -1
        self.init_ui()

    def init_ui(self):
        if self.layout():
            while self.layout().count():
                item = self.layout().takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            layout = self.layout()
        else:
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(3)

        self.step_widgets = []
        for i, name in enumerate(self.steps):
            step_box = QFrame()
            step_box.setFixedHeight(24)
            s_layout = QHBoxLayout(step_box)
            s_layout.setContentsMargins(6, 2, 6, 2)
            s_layout.setSpacing(4)

            icon_lbl = QLabel(str(i + 1))
            icon_lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
            text_lbl = QLabel(name)
            text_lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))

            s_layout.addWidget(icon_lbl)
            s_layout.addWidget(text_lbl)
            layout.addWidget(step_box)

            self.step_widgets.append((step_box, icon_lbl, text_lbl))

            if i < len(self.steps) - 1:
                arrow = QLabel("›")
                arrow.setFont(QFont("Segoe UI", 10, QFont.Bold))
                arrow.setStyleSheet("color: #475569; margin: 0 1px;")
                layout.addWidget(arrow)

        layout.addStretch()
        self.update_style()

    def set_current_step(self, step_index):
        self.current_step = step_index
        self.update_style()

    def update_style(self):
        for i, (box, icon_lbl, text_lbl) in enumerate(self.step_widgets):
            if self.current_step == -1:
                # Idle
                box.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 5px;")
                icon_lbl.setText(str(i + 1))
                icon_lbl.setStyleSheet("color: #475569; font-size: 8px;")
                text_lbl.setStyleSheet("color: #64748b; font-size: 8px;")
            elif i < self.current_step:
                # Completed
                box.setStyleSheet("background: #064e3b; border: 1px solid #10b981; border-radius: 5px;")
                icon_lbl.setText("✓")
                icon_lbl.setStyleSheet("color: #34d399; font-weight: bold; font-size: 8px;")
                text_lbl.setStyleSheet("color: #a7f3d0; font-weight: bold; font-size: 8px;")
            elif i == self.current_step:
                # Active
                box.setStyleSheet("background: #0284c7; border: 1.5px solid #38bdf8; border-radius: 5px;")
                icon_lbl.setText("▶")
                icon_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 8px;")
                text_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 8px;")
            else:
                # Pending
                box.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 5px;")
                icon_lbl.setText(str(i + 1))
                icon_lbl.setStyleSheet("color: #475569; font-size: 8px;")
                text_lbl.setStyleSheet("color: #64748b; font-size: 8px;")


class WorkerCard(QFrame):
    """
    Realtime Card for each parallel Browser Worker.
    """
    WORKER_PALETTES = {
        1:  {"fg": "#38bdf8", "bg": "rgba(14, 165, 233, 0.15)", "border": "#0284c7"},  # Sky Blue
        2:  {"fg": "#a78bfa", "bg": "rgba(139, 92, 246, 0.15)", "border": "#7c3aed"},  # Violet
        3:  {"fg": "#34d399", "bg": "rgba(16, 185, 129, 0.15)", "border": "#059669"},  # Emerald
        4:  {"fg": "#fbbf24", "bg": "rgba(245, 158, 11, 0.15)", "border": "#d97706"},  # Amber
        5:  {"fg": "#fb7185", "bg": "rgba(244, 63, 94, 0.15)", "border": "#e11d48"},   # Rose
        6:  {"fg": "#22d3ee", "bg": "rgba(6, 182, 212, 0.15)", "border": "#0891b2"},   # Cyan
        7:  {"fg": "#e879f9", "bg": "rgba(217, 70, 239, 0.15)", "border": "#c026d3"},  # Fuchsia
        8:  {"fg": "#a3e635", "bg": "rgba(132, 204, 22, 0.15)", "border": "#65a30d"},  # Lime
        9:  {"fg": "#fb923c", "bg": "rgba(249, 115, 22, 0.15)", "border": "#ea580c"},  # Orange
        10: {"fg": "#818cf8", "bg": "rgba(99, 102, 241, 0.15)", "border": "#4f46e5"},  # Indigo
        11: {"fg": "#2dd4bf", "bg": "rgba(20, 184, 166, 0.15)", "border": "#0d9488"},  # Teal
        12: {"fg": "#f472b6", "bg": "rgba(236, 72, 153, 0.15)", "border": "#db2777"},  # Pink
        13: {"fg": "#facc15", "bg": "rgba(234, 179, 8, 0.15)", "border": "#ca8a04"},   # Yellow
        14: {"fg": "#c084fc", "bg": "rgba(168, 85, 247, 0.15)", "border": "#9333ea"},  # Purple
        15: {"fg": "#f87171", "bg": "rgba(239, 68, 68, 0.15)", "border": "#dc2626"},   # Red
        16: {"fg": "#60a5fa", "bg": "rgba(59, 130, 246, 0.15)", "border": "#2563eb"},  # Blue
        17: {"fg": "#4ade80", "bg": "rgba(34, 197, 94, 0.15)", "border": "#16a34a"},   # Green
        18: {"fg": "#fda4af", "bg": "rgba(251, 113, 133, 0.15)", "border": "#f43f5e"}, # Light Rose
        19: {"fg": "#38bdf8", "bg": "rgba(2, 132, 199, 0.15)", "border": "#0369a1"},  # Ocean
        20: {"fg": "#d8b4fe", "bg": "rgba(192, 132, 252, 0.15)", "border": "#7e22ce"}, # Lavender
    }

    def __init__(self, worker_id: int, max_pages: int = 3, has_smartlink: bool = True, parent=None):
        super().__init__(parent)
        self.worker_id = worker_id
        self.max_pages = max_pages
        self.has_smartlink = has_smartlink
        self.is_dwelling = False
        self.dwell_end_time = 0.0
        self.dwell_label = "Dwell Time"
        self._last_step_idx = -1  # Monotonic guard: stepper hanya maju, tidak mundur
        self.setObjectName("WorkerCard")
        self.init_ui()

    def init_ui(self):
        palette = self.WORKER_PALETTES.get(self.worker_id)
        if not palette:
            palette = self.WORKER_PALETTES.get(((self.worker_id - 1) % len(self.WORKER_PALETTES)) + 1, self.WORKER_PALETTES[1])
        self.setStyleSheet(f"""
            QFrame#WorkerCard {{
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-left: 4px solid {palette['fg']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        v_layout = QVBoxLayout(self)
        v_layout.setContentsMargins(10, 8, 10, 8)
        v_layout.setSpacing(6)

        # Header Row
        h_layout = QHBoxLayout()
        self.badge_lbl = QLabel(f"Browser #{self.worker_id}")
        self.badge_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.badge_lbl.setStyleSheet(f"background-color: {palette['bg']}; color: {palette['fg']}; border: 1px solid {palette['border']}; border-radius: 4px; padding: 2px 7px;")
        h_layout.addWidget(self.badge_lbl)

        self.session_lbl = QLabel("🎯 Sesi: Menunggu")
        self.session_lbl.setFont(QFont("Segoe UI", 9))
        self.session_lbl.setStyleSheet("color: #94a3b8; font-weight: bold;")
        h_layout.addWidget(self.session_lbl)

        h_layout.addStretch()

        self.status_pill = QLabel("⚪ STANDBY (SIAP)")
        self.status_pill.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.status_pill.setStyleSheet("background: #1e293b; color: #64748b; border: 1px solid #334155; border-radius: 4px; padding: 2px 8px;")
        h_layout.addWidget(self.status_pill)
        v_layout.addLayout(h_layout)

        # Info Row
        info_layout = QHBoxLayout()
        info_layout.setSpacing(12)

        self.proxy_lbl = QLabel("🛡️ Proksi: Belum Terhubung")
        self.proxy_lbl.setFont(QFont("Segoe UI", 9))
        self.proxy_lbl.setStyleSheet("color: #cbd5e1;")
        info_layout.addWidget(self.proxy_lbl, stretch=1)

        self.detail_lbl = QLabel("🔗 URL: -")
        self.detail_lbl.setFont(QFont("Segoe UI", 9))
        self.detail_lbl.setStyleSheet("color: #64748b;")
        info_layout.addWidget(self.detail_lbl, stretch=2)

        v_layout.addLayout(info_layout)

        # Stepper Row
        steps = generate_flow_steps(self.max_pages, self.has_smartlink)
        self.stepper = StepperBar(steps=steps)
        v_layout.addWidget(self.stepper)

    def reconfigure_flow(self, max_pages: int, has_smartlink: bool):
        self.max_pages = max_pages
        self.has_smartlink = has_smartlink
        steps = generate_flow_steps(max_pages, has_smartlink)
        self.stepper.set_steps(steps)

    def reset_state(self):
        self.is_dwelling = False
        self.dwell_end_time = 0.0
        self._last_step_idx = -1
        self.session_lbl.setText("🎯 Sesi: Menunggu")
        self.status_pill.setText("⚪ STANDBY (SIAP)")
        self.status_pill.setStyleSheet("background: #1e293b; color: #64748b; border: 1px solid #334155; border-radius: 4px; padding: 2px 8px;")
        self.proxy_lbl.setText("🛡️ Proksi: Belum Terhubung")
        self.detail_lbl.setText("🔗 URL: -")
        self.stepper.set_current_step(-1)

    def tick_second(self):
        if self.is_dwelling and self.dwell_end_time > 0:
            rem = max(0, int(self.dwell_end_time - time.time()))
            self.status_pill.setText(f"⏳ {self.dwell_label} ({rem}s)")
            if "Cooldown" in self.dwell_label:
                self.status_pill.setStyleSheet("background: #312e81; color: #c7d2fe; border: 1px solid #4f46e5; border-radius: 4px; padding: 2px 8px;")
            elif "Iklan" in self.dwell_label:
                self.status_pill.setStyleSheet("background: #831843; color: #fbcfe8; border: 1px solid #db2777; border-radius: 4px; padding: 2px 8px;")
            else:
                self.status_pill.setStyleSheet("background: #1e3a8a; color: #93c5fd; border: 1px solid #2563eb; border-radius: 4px; padding: 2px 8px;")

            if rem <= 0:
                self.is_dwelling = False
                if "Cooldown" in self.dwell_label:
                    self.status_pill.setText("☕ Siap Memulai Sesi")
                else:
                    self.status_pill.setText(f"⌛ {self.dwell_label} (Selesai)")

    def update_flow(self, data: dict):
        step_key = data.get("step", "")
        hop = data.get("hop", 1)

        if "session" in data:
            curr = data["session"]
            tot = data.get("total_sessions", "?")
            self.session_lbl.setText(f"🎯 Sesi: {curr} / {tot}")

        # Dwell countdown handling
        if "dwell_seconds" in data and data["dwell_seconds"] is not None:
            dwell_sec = int(data["dwell_seconds"])
            if dwell_sec > 0:
                self.is_dwelling = True
                self.dwell_end_time = time.time() + dwell_sec
                self.dwell_label = data.get("dwell_label", "Dwell Time")
            else:
                self.is_dwelling = False
                self.dwell_end_time = 0.0
        elif step_key and step_key not in ("DWELL", "DWELL_BERANDA", "SMARTLINK", "COOLDOWN"):
            self.is_dwelling = False
            self.dwell_end_time = 0.0

        if "status_text" in data:
            txt = data["status_text"]
            self.status_pill.setText(txt)
            if "Uji" in txt or "Menguji" in txt:
                self.status_pill.setStyleSheet("background: #78350f; color: #fde047; border: 1px solid #ca8a04; border-radius: 4px; padding: 2px 8px;")
            elif "Mati" in txt or "Gagal" in txt:
                self.status_pill.setStyleSheet("background: #4c0519; color: #fda4af; border: 1px solid #e11d48; border-radius: 4px; padding: 2px 8px;")
            elif "Valid" in txt or "Lolos" in txt:
                self.status_pill.setStyleSheet("background: #064e3b; color: #6ee7b7; border: 1px solid #059669; border-radius: 4px; padding: 2px 8px;")
            elif "Dwell" in txt:
                if "Iklan" in txt:
                    self.status_pill.setStyleSheet("background: #831843; color: #fbcfe8; border: 1px solid #db2777; border-radius: 4px; padding: 2px 8px;")
                else:
                    self.status_pill.setStyleSheet("background: #1e3a8a; color: #93c5fd; border: 1px solid #2563eb; border-radius: 4px; padding: 2px 8px;")
            elif "Selesai" in txt:
                self.status_pill.setStyleSheet("background: #064e3b; color: #34d399; border: 1px solid #10b981; border-radius: 4px; padding: 2px 8px;")
            elif "Cooldown" in txt:
                self.status_pill.setStyleSheet("background: #312e81; color: #c7d2fe; border: 1px solid #4f46e5; border-radius: 4px; padding: 2px 8px;")
            else:
                self.status_pill.setStyleSheet("background: #0c4a6e; color: #7dd3fc; border: 1px solid #0284c7; border-radius: 4px; padding: 2px 8px;")

        if "proxy_str" in data:
            p_str = data["proxy_str"]
            self.proxy_lbl.setText(f"🛡️ Proksi: {p_str}")

        if "url" in data and data["url"]:
            self.detail_lbl.setText(f"🔗 {data['url']}")

        if step_key:
            # Sesi baru dimulai → reset posisi stepper ke awal
            if step_key == "START":
                self._last_step_idx = -1
                self.stepper.set_current_step(-1)

            idx = get_step_index(step_key, hop, self.max_pages, self.has_smartlink)
            if idx >= 0:
                # Guard monotonis: stepper hanya boleh maju, tidak boleh mundur
                if idx > self._last_step_idx:
                    self._last_step_idx = idx
                    self.stepper.set_current_step(idx)
                elif idx == self._last_step_idx:
                    pass  # Posisi sama, tidak perlu update
                # idx < self._last_step_idx → diabaikan (bukan maju, buang)


class TrafficBotGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chronicle Traffic & Ad Impression Controller — Dashboard Otomasi")
        self.resize(1340, 820)
        self.setMinimumSize(1080, 720)

        # Bersihkan proksi dead dari sesi sebelumnya SEBELUM load data
        self._cleanup_dead_proxies_on_startup()

        self.config_data = load_config_data()
        self.proxies_data = load_proxies_data()
        self.worker = None

        # Session tracking stats
        self.total_sessions_target = 1
        self.completed_sessions_count = 0
        self.start_timestamp = None

        # Timer for elapsed time
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)

        self.init_ui()
        self.populate_proxy_table()
        self.apply_premium_theme()

    def _cleanup_dead_proxies_on_startup(self):
        """
        Saat GUI pertama kali dibuka, bersihkan flag runtime lama ("dead", "fail_count",
        dsb) agar semua proksi mendapat kesempatan diuji ulang. Daftar proksi TIDAK
        pernah dihapus di sini, sehingga proxy baru/berharga tidak hilang.
        """
        raw_text = ""
        if PROXIES_PATH.exists():
            try:
                raw_text = PROXIES_PATH.read_text(encoding="utf-8").strip()
            except Exception:
                raw_text = ""

        backup_path = PROXIES_PATH.parent / "proxies_backup.json"
        if not raw_text:
            if backup_path.exists() and backup_path.stat().st_size > 0:
                try:
                    import shutil
                    shutil.copy2(backup_path, PROXIES_PATH)
                    raw_text = PROXIES_PATH.read_text(encoding="utf-8").strip()
                    print(f"[*] [STARTUP-CLEANUP] File proxies.json kosong, dipulihkan dari cadangan {backup_path.name}")
                except Exception:
                    return
            else:
                try:
                    PROXIES_PATH.write_text("[]", encoding="utf-8")
                except Exception:
                    pass
                return

        try:
            all_proxies = json.loads(raw_text)

            if not isinstance(all_proxies, list):
                return

            revived_count = 0
            for px in all_proxies:
                if px.pop("dead", None) is not None:
                    revived_count += 1
                px.pop("fail_count", None)
                px.pop("fail_streak", None)
                px.pop("dead_at", None)

            if revived_count == 0:
                return

            save_proxies_data(all_proxies)

            print(f"[✓] [STARTUP-CLEANUP] {revived_count} proksi ber-flag mati telah diaktifkan kembali untuk diuji ulang. Total daftar tetap {len(all_proxies)} proksi (tidak ada yang dihapus).")
        except Exception as e:
            # Jika JSON rusak, coba pulihkan dari backup
            if backup_path.exists() and backup_path.stat().st_size > 0:
                try:
                    import shutil
                    shutil.copy2(backup_path, PROXIES_PATH)
                    print(f"[✓] [STARTUP-CLEANUP] proxies.json rusak ({e}), berhasil dipulihkan dari {backup_path.name}")
                    return
                except Exception:
                    pass
            print(f"[-] [STARTUP-CLEANUP] Gagal membersihkan proksi dead: {e}")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(18)

        # ==========================================
        # LEFT PANEL: Pengaturan Sederhana & Tombol
        # ==========================================
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(500)
        left_scroll.setMaximumWidth(620)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(6, 4, 14, 6)
        left_layout.setSpacing(14)

        # 1. Header Banner
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(16, 14, 16, 14)
        h_layout.setSpacing(4)

        title_lbl = QLabel("🤖 CHRONICLE TRAFFIC BOT")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_lbl.setStyleSheet("color: #38bdf8; letter-spacing: 0.5px;")

        desc_lbl = QLabel("Otomasi Tayangan Iklan dan Kunjungan Organik untuk read.riztama.my.id")
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        desc_lbl.setWordWrap(True)

        h_layout.addWidget(title_lbl)
        h_layout.addWidget(desc_lbl)
        left_layout.addWidget(header_card)

        # 2. Tombol Aksi Utama (Paling Atas agar Jelas)
        action_box = QFrame()
        action_box.setObjectName("Card")
        a_layout = QVBoxLayout(action_box)
        a_layout.setContentsMargins(14, 14, 14, 14)
        a_layout.setSpacing(10)

        action_title = QLabel("⚡ EKSEKUSI BOT")
        action_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        action_title.setStyleSheet("color: #cbd5e1;")
        a_layout.addWidget(action_title)

        # Quick Test Button
        self.quick_test_btn = QPushButton("🚀 Uji Coba Cepat (1 Kunjungan — Layar Terbuka)")
        self.quick_test_btn.setObjectName("QuickTestBtn")
        self.quick_test_btn.setToolTip("Membuka Chrome asli secara langsung agar Anda bisa menyaksikan bot bekerja dari awal sampai akhir.")
        self.quick_test_btn.clicked.connect(self.run_quick_test)
        a_layout.addWidget(self.quick_test_btn)

        # Start Button
        self.start_btn = QPushButton("▶ JALANKAN OTOMASI (Sesuai Pengaturan)")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.clicked.connect(self.start_bot)
        a_layout.addWidget(self.start_btn)

        # Stop Button
        self.stop_btn = QPushButton("⏹ HENTIKAN BOT")
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_bot)
        a_layout.addWidget(self.stop_btn)

        left_layout.addWidget(action_box)

        # 3. Target Website
        target_group = QGroupBox("1. Target Website")
        t_layout = QVBoxLayout(target_group)
        t_layout.setContentsMargins(14, 16, 14, 14)
        t_layout.setSpacing(8)

        t_lbl = QLabel("Pilih Alamat Web:")
        t_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.target_url_combo = QComboBox()
        self.target_url_combo.setEditable(True)
        self.target_url_combo.addItem("https://read.riztama.my.id (Server Live)")
        self.target_url_combo.addItem("http://localhost:3000 (Uji Coba Komputer Sendiri)")
        t_layout.addWidget(t_lbl)
        t_layout.addWidget(self.target_url_combo)

        slug_lbl = QLabel("Artikel Tertentu (Opsional / Kosongkan untuk Halaman Utama):")
        slug_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.slug_input = QLineEdit()
        self.slug_input.setPlaceholderText("Contoh: the-tactile-terminal-command-line-aesthetics")
        t_layout.addWidget(slug_lbl)
        t_layout.addWidget(self.slug_input)

        left_layout.addWidget(target_group)

        # 4. Target Kunjungan & Kecepatan (Jelas & Ramah Pemula)
        session_group = QGroupBox("2. Target Kunjungan dan Kecepatan")
        s_layout = QVBoxLayout(session_group)
        s_layout.setContentsMargins(14, 16, 14, 14)
        s_layout.setSpacing(10)

        total_proxies_init = len(self.proxies_data) if self.proxies_data else 120

        s_header_layout = QVBoxLayout()
        s_lbl = QLabel("Berapa Banyak Kunjungan (Pilihan Sesi):")
        s_lbl.setStyleSheet("font-weight: bold; color: #f8fafc;")
        s_header_layout.addWidget(s_lbl)

        s_input_row = QHBoxLayout()
        self.session_combo = QComboBox()
        self.session_combo.addItem("♾️ Mode Unlimited (Berputar Terus 24 Jam Non-Stop)")
        self.session_combo.addItem(f"🎯 {total_proxies_init} Sesi (1x Putar Seluruh Proksi)")
        self.session_combo.addItem(f"🔄 {total_proxies_init * 2} Sesi (2x Putar Seluruh Proksi)")
        self.session_combo.addItem(f"🚀 {total_proxies_init * 3} Sesi (3x Putar Seluruh Proksi)")
        self.session_combo.addItem("⚡ 60 Sesi (Setengah Putaran Proksi)")
        self.session_combo.addItem("🧪 10 Sesi (Uji Coba Cepat Ringan)")
        self.session_combo.addItem("✏️ Kustom / Masukkan Angka Sesi Bebas...")
        self.session_combo.setCurrentIndex(0)  # Default: Mode Unlimited sesuai permintaan
        s_input_row.addWidget(self.session_combo, stretch=2)

        self.custom_session_spin = QSpinBox()
        self.custom_session_spin.setRange(1, 50000)
        self.custom_session_spin.setValue(total_proxies_init)
        self.custom_session_spin.setSuffix(" Sesi Kustom")
        self.custom_session_spin.setVisible(False)
        s_input_row.addWidget(self.custom_session_spin, stretch=1)

        s_header_layout.addLayout(s_input_row)
        s_layout.addLayout(s_header_layout)

        self.session_helper = QLabel("♾️ Mode Unlimited Aktif: Bot akan memproses seluruh 120 proksi lalu otomatis mengulang dari awal tanpa henti 24 jam.")
        self.session_helper.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.session_helper.setWordWrap(True)
        s_layout.addWidget(self.session_helper)

        # Tombol Preset Pintar Berdasarkan Proksi
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)
        btn_preset_unlimited = QPushButton("♾️ Unlimited (Non-Stop)")
        btn_preset_unlimited.setObjectName("PresetBtn")
        btn_preset_unlimited.setToolTip("Mode Non-Stop 24 Jam terus berputar tanpa henti.")
        btn_preset_unlimited.clicked.connect(lambda: self.session_combo.setCurrentIndex(0))

        btn_preset_1 = QPushButton(f"🎯 {total_proxies_init} Sesi (1x Putar)")
        btn_preset_1.setObjectName("PresetBtn")
        btn_preset_1.setToolTip(f"Otomatis mengatur ke {total_proxies_init} kunjungan (1x putar).")
        btn_preset_1.clicked.connect(lambda: self.session_combo.setCurrentIndex(1))

        btn_preset_2 = QPushButton(f"🔄 {total_proxies_init * 2} Sesi (2x Putar)")
        btn_preset_2.setObjectName("PresetBtn")
        btn_preset_2.setToolTip(f"Otomatis mengatur ke {total_proxies_init * 2} kunjungan (2x putar).")
        btn_preset_2.clicked.connect(lambda: self.session_combo.setCurrentIndex(2))

        btn_preset_3 = QPushButton(f"🚀 {total_proxies_init * 3} Sesi (3x Putar)")
        btn_preset_3.setObjectName("PresetBtn")
        btn_preset_3.setToolTip(f"Otomatis mengatur ke {total_proxies_init * 3} kunjungan (3x putar).")
        btn_preset_3.clicked.connect(lambda: self.session_combo.setCurrentIndex(3))

        preset_layout.addWidget(btn_preset_unlimited)
        preset_layout.addWidget(btn_preset_1)
        preset_layout.addWidget(btn_preset_2)
        preset_layout.addWidget(btn_preset_3)
        s_layout.addLayout(preset_layout)

        self.session_combo.currentIndexChanged.connect(self.on_session_combo_changed)

        # Grid Pengaturan Perilaku & Browser
        s_grid = QGridLayout()
        s_grid.setSpacing(8)

        s_grid.addWidget(QLabel("Jumlah Worker (Browser Paralel):"), 0, 0)
        self.concurrency_combo = QComboBox()
        self.concurrency_combo.addItem("1 Worker (1 Browser — Ringan RAM)")
        self.concurrency_combo.addItem("2 Worker (2 Browser Bersamaan)")
        self.concurrency_combo.addItem("3 Worker (3 Browser — Cepat & Stabil)")
        self.concurrency_combo.addItem("5 Worker (5 Browser — Batching Sedang)")
        self.concurrency_combo.addItem("10 Worker (10 Browser — High Speed)")
        self.concurrency_combo.addItem("15 Worker (15 Browser — Ultra Traffic)")
        self.concurrency_combo.addItem("20 Worker (20 Browser — Maksimal Paralel)")

        c_to_idx = {1: 0, 2: 1, 3: 2, 5: 3, 10: 4, 15: 5, 20: 6}
        init_c = self.config_data.get("concurrency", 5)
        self.concurrency_combo.setCurrentIndex(c_to_idx.get(init_c, 3))
        s_grid.addWidget(self.concurrency_combo, 0, 1)

        c_info = QLabel("⚡ Tips: Pilihan hingga 20 Worker memungkinkan 20 browser berjalan paralel memproses sesi hingga 20x lebih cepat!")
        c_info.setStyleSheet("color: #4ade80; font-size: 10px;")
        s_grid.addWidget(c_info, 1, 0, 1, 2)

        # Indikator Real-time Keaktifan Semua Worker Browser
        ws_frame = QFrame()
        ws_frame.setStyleSheet("background-color: rgba(15, 23, 42, 0.7); border: 1px solid #1e293b; border-radius: 8px;")
        ws_vlayout = QVBoxLayout(ws_frame)
        ws_vlayout.setContentsMargins(8, 6, 8, 6)
        ws_vlayout.setSpacing(5)

        ws_head = QLabel("Status Realtime Worker Browser:")
        ws_head.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: bold; border: none;")
        ws_vlayout.addWidget(ws_head)

        ws_badges_layout = QGridLayout()
        ws_badges_layout.setSpacing(4)
        self.worker_badges = {}
        for w_i in range(1, 21):
            wb = QLabel(f"#B{w_i}: Siap")
            wb.setAlignment(Qt.AlignCenter)
            wb.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #1e293b; color: #64748b; border: 1px solid #334155;")
            self.worker_badges[w_i] = wb
            row = (w_i - 1) // 5
            col = (w_i - 1) % 5
            ws_badges_layout.addWidget(wb, row, col)
            wb.setVisible(w_i <= init_c)

        ws_vlayout.addLayout(ws_badges_layout)
        s_grid.addWidget(ws_frame, 2, 0, 1, 2)

        s_grid.addWidget(QLabel("Lama Diam di Web:"), 3, 0)
        dwell_layout = QHBoxLayout()
        self.min_dwell_spin = QSpinBox()
        self.min_dwell_spin.setRange(10, 180)
        self.min_dwell_spin.setValue(self.config_data.get("dwell_time", {}).get("min_seconds", 20))
        self.min_dwell_spin.setSuffix("s Min")

        dwell_sep = QLabel("s/d")
        dwell_sep.setStyleSheet("color: #64748b; font-size: 11px;")

        self.max_dwell_spin = QSpinBox()
        self.max_dwell_spin.setRange(15, 300)
        self.max_dwell_spin.setValue(self.config_data.get("dwell_time", {}).get("max_seconds", 32))
        self.max_dwell_spin.setSuffix("s Max")

        dwell_layout.addWidget(self.min_dwell_spin)
        dwell_layout.addWidget(dwell_sep)
        dwell_layout.addWidget(self.max_dwell_spin)
        s_grid.addLayout(dwell_layout, 3, 1)

        s_grid.addWidget(QLabel("Artikel Dijelajahi:"), 4, 0)
        self.pages_combo = QComboBox()
        self.pages_combo.addItem("2 Artikel (Rekomendasi Cepat & High eCPM)")
        self.pages_combo.addItem("1 Artikel Saja (Ultra Speed)")
        self.pages_combo.addItem("3 Artikel (Eksplorasi Santai)")
        self.pages_combo.addItem("4 Artikel (Eksplorasi Mendalam)")

        p_to_idx = {2: 0, 1: 1, 3: 2, 4: 3}
        init_p = self.config_data.get("max_pages_per_session", 2)
        self.pages_combo.setCurrentIndex(p_to_idx.get(init_p, 0))
        s_grid.addWidget(self.pages_combo, 4, 1)

        self.concurrency_combo.currentIndexChanged.connect(self.on_concurrency_combo_changed)
        self.pages_combo.currentIndexChanged.connect(self.on_pages_combo_changed)

        s_layout.addLayout(s_grid)

        self.return_home_check = QCheckBox("Kembali ke Beranda Dulu (Simulasi Pembaca Alami)")
        self.return_home_check.setChecked(self.config_data.get("return_home_between_posts", False))
        self.return_home_check.setStyleSheet("font-weight: 500;")
        s_layout.addWidget(self.return_home_check)

        self.headless_check = QCheckBox("Jalankan di Balik Layar (Sembunyikan Jendela Chrome)")
        self.headless_check.setChecked(False)
        self.headless_check.setStyleSheet("font-weight: 500;")
        s_layout.addWidget(self.headless_check)

        self.loop_check = QCheckBox("🔁 Mode Non-Stop (Berputar Terus Tanpa Henti 24 Jam)")
        self.loop_check.setChecked(False)
        self.loop_check.setStyleSheet("font-weight: 600; color: #38bdf8;")
        self.loop_check.setToolTip("Jika dicentang, setelah semua 120 proksi selesai dijalankan, bot akan otomatis mengulang ke putaran berikutnya dari awal terus-menerus.")
        s_layout.addWidget(self.loop_check)

        left_layout.addWidget(session_group)

        # 5. Jaringan Proksi
        proxy_group = QGroupBox("3. Proksi Residensial (Ganti IP dan Negara)")
        p_layout = QVBoxLayout(proxy_group)
        p_layout.setContentsMargins(14, 16, 14, 14)
        p_layout.setSpacing(8)

        total_px = len(self.proxies_data)
        self.use_proxy_check = QCheckBox(f"Gunakan Proksi Residensial ({total_px} Proksi Tersedia)")
        self.use_proxy_check.setChecked(total_px > 0)
        p_layout.addWidget(self.use_proxy_check)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItem("🎲 Rotasi Acak Otomatis (Setiap Sesi Berganti Negara)")
        for i, px in enumerate(self.proxies_data):
            country = px.get("country", "Unknown")
            host = px.get("host", "")
            port = px.get("port", "")
            self.proxy_combo.addItem(f"#{i+1}: 📍 {country} ({host}:{port})")
        p_layout.addWidget(self.proxy_combo)

        # Import & Test proxy buttons
        p_btn_layout = QHBoxLayout()
        self.import_proxy_btn = QPushButton("➕ Tambah / Import")
        self.import_proxy_btn.setObjectName("SecondaryBtn")
        self.import_proxy_btn.setToolTip("Paste daftar proksi baru dalam format geolocation:// atau host:port")
        self.import_proxy_btn.clicked.connect(self.open_proxy_import_dialog)
        p_btn_layout.addWidget(self.import_proxy_btn)

        self.test_proxy_btn = QPushButton("⚡ Tes Koneksi")
        self.test_proxy_btn.setObjectName("SecondaryBtn")
        self.test_proxy_btn.setToolTip("Tes apakah proksi Anda aktif dan bisa membuka web target")
        self.test_proxy_btn.clicked.connect(self.open_proxy_test_dialog)
        p_btn_layout.addWidget(self.test_proxy_btn)

        p_layout.addLayout(p_btn_layout)

        left_layout.addWidget(proxy_group)

        # 6. Interaksi Smartlink (Aman)
        smartlink_group = QGroupBox("4. Interaksi Smartlink (Klik Iklan Penawaran)")
        sl_layout = QVBoxLayout(smartlink_group)
        sl_layout.setContentsMargins(14, 16, 14, 14)
        sl_layout.setSpacing(6)

        init_sl = int(self.config_data.get("smartlink_click_chance", 0.70) * 100)
        self.sl_chance_label = QLabel(f"Peluang Klik: {init_sl}% (Tinggi - High eCPM Revenue)")
        self.sl_chance_label.setStyleSheet("color: #38bdf8; font-weight: bold;")
        sl_layout.addWidget(self.sl_chance_label)

        self.sl_slider = QSlider(Qt.Horizontal)
        self.sl_slider.setRange(0, 100)
        self.sl_slider.setValue(init_sl)
        self.sl_slider.valueChanged.connect(self.on_slider_changed)
        sl_layout.addWidget(self.sl_slider)

        sl_desc = QLabel("Bot akan mengklik banner smartlink secara acak, menunggu penawaran tercatat, lalu menutup tab dengan aman.")
        sl_desc.setStyleSheet("color: #64748b; font-size: 10px;")
        sl_desc.setWordWrap(True)
        sl_layout.addWidget(sl_desc)

        left_layout.addWidget(smartlink_group)
        left_layout.addStretch()

        left_scroll.setWidget(left_content)
        main_layout.addWidget(left_scroll, stretch=4)

        # ==========================================
        # RIGHT PANEL: Status Visual & Live Console
        # ==========================================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        # 1. Status Overview Card (Besar & Informatif)
        status_card = QFrame()
        status_card.setObjectName("StatusCard")
        sc_layout = QVBoxLayout(status_card)
        sc_layout.setContentsMargins(16, 14, 16, 14)
        sc_layout.setSpacing(10)

        # Row 1: Badges
        r1_layout = QHBoxLayout()
        self.status_badge = QLabel("⚪ STANDBY (SIAP)")
        self.status_badge.setObjectName("StatusBadgeIdle")
        r1_layout.addWidget(self.status_badge)

        self.session_badge = QLabel("SESI: 0 / 0")
        self.session_badge.setObjectName("SessionBadge")
        r1_layout.addWidget(self.session_badge)

        self.time_badge = QLabel("⏱️ 00:00")
        self.time_badge.setObjectName("TimeBadge")
        r1_layout.addWidget(self.time_badge)

        r1_layout.addStretch()
        sc_layout.addLayout(r1_layout)

        # Row 2: Detailed Step Description
        self.step_label = QLabel("Silakan klik 'Uji Coba Cepat' atau 'Jalankan Otomasi' untuk memulai.")
        self.step_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.step_label.setStyleSheet("color: #f8fafc;")
        sc_layout.addWidget(self.step_label)

        # Row 3: Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        sc_layout.addWidget(self.progress_bar)

        # Row 4: Metrics Info (Grid)
        metrics_grid = QGridLayout()
        metrics_grid.setContentsMargins(0, 4, 0, 0)
        metrics_grid.setSpacing(8)

        # Target Metric
        metrics_grid.addWidget(QLabel("Target Saat Ini:"), 0, 0)
        self.metric_target = QLabel("https://read.riztama.my.id")
        self.metric_target.setStyleSheet("color: #38bdf8; font-weight: bold;")
        metrics_grid.addWidget(self.metric_target, 0, 1)

        # Proxy Metric
        metrics_grid.addWidget(QLabel("Lokasi Proksi:"), 0, 2)
        self.metric_proxy = QLabel("Belum Terhubung")
        self.metric_proxy.setStyleSheet("color: #a78bfa; font-weight: bold;")
        metrics_grid.addWidget(self.metric_proxy, 0, 3)

        sc_layout.addLayout(metrics_grid)
        right_layout.addWidget(status_card)

        # 2. Main Tabbed Workspace (3 Tabs Penuh)
        self.right_tabs = QTabWidget()
        self.right_tabs.setObjectName("RightTabs")

        # ------------------------------------------------------------------
        # TAB 1: 🖥️ Monitor Worker & Flow Timeline
        # ------------------------------------------------------------------
        worker_tab = QWidget()
        wt_layout = QVBoxLayout(worker_tab)
        wt_layout.setContentsMargins(10, 10, 10, 10)
        wt_layout.setSpacing(10)

        wt_header = QHBoxLayout()
        wt_title = QLabel("🖥️ MONITOR STATUS WORKER BROWSER (REALTIME)")
        wt_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        wt_title.setStyleSheet("color: #cbd5e1; letter-spacing: 0.5px;")
        wt_header.addWidget(wt_title)
        wt_header.addStretch()

        init_c = 5
        if hasattr(self, "concurrency_combo"):
            cmap = {0: 1, 1: 2, 2: 3, 3: 5, 4: 10, 5: 15, 6: 20}
            init_c = cmap.get(self.concurrency_combo.currentIndex(), 5)

        self.worker_count_badge = QLabel(f"Browser Paralel: {init_c} Aktif")
        self.worker_count_badge.setStyleSheet("color: #38bdf8; font-weight: bold; background: #0f172a; padding: 3px 8px; border-radius: 4px; border: 1px solid #1e293b;")
        wt_header.addWidget(self.worker_count_badge)
        wt_layout.addLayout(wt_header)

        w_scroll = QScrollArea()
        w_scroll.setWidgetResizable(True)
        w_scroll.setFrameShape(QFrame.NoFrame)

        self.worker_cards_container = QWidget()
        self.worker_cards_layout = QVBoxLayout(self.worker_cards_container)
        self.worker_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.worker_cards_layout.setSpacing(10)

        max_p = self.config_data.get("max_pages_per_session", 3)
        self.worker_cards = {}
        for w_i in range(1, 21):
            card = WorkerCard(w_i, max_pages=max_p)
            self.worker_cards[w_i] = card
            self.worker_cards_layout.addWidget(card)
            card.setVisible(w_i <= init_c)

        self.worker_cards_layout.addStretch()
        w_scroll.setWidget(self.worker_cards_container)
        wt_layout.addWidget(w_scroll)
        self.right_tabs.addTab(worker_tab, "🖥️ Worker Flow & Cards")

        # ------------------------------------------------------------------
        # TAB 2: 🌐 Live Proxy Monitor (Tabel Status Proksi Realtime)
        # ------------------------------------------------------------------
        proxy_tab = QWidget()
        pt_layout = QVBoxLayout(proxy_tab)
        pt_layout.setContentsMargins(10, 10, 10, 10)
        pt_layout.setSpacing(10)

        pt_top = QHBoxLayout()
        self.proxy_stat_total = QLabel("Total: 0")
        self.proxy_stat_total.setStyleSheet("color: #38bdf8; font-weight: bold; background: #0f172a; padding: 4px 8px; border-radius: 4px; border: 1px solid #1e293b;")
        pt_top.addWidget(self.proxy_stat_total)

        self.proxy_stat_standby = QLabel("⚪ Standby: 0")
        self.proxy_stat_standby.setStyleSheet("color: #94a3b8; font-weight: bold; background: #0f172a; padding: 4px 8px; border-radius: 4px; border: 1px solid #1e293b;")
        pt_top.addWidget(self.proxy_stat_standby)

        self.proxy_stat_in_use = QLabel("🚀 Dipakai: 0")
        self.proxy_stat_in_use.setStyleSheet("color: #4ade80; font-weight: bold; background: #0f172a; padding: 4px 8px; border-radius: 4px; border: 1px solid #1e293b;")
        pt_top.addWidget(self.proxy_stat_in_use)

        self.proxy_stat_dead = QLabel("❌ Mati: 0")
        self.proxy_stat_dead.setStyleSheet("color: #f43f5e; font-weight: bold; background: #0f172a; padding: 4px 8px; border-radius: 4px; border: 1px solid #1e293b;")
        pt_top.addWidget(self.proxy_stat_dead)

        pt_top.addStretch()

        self.proxy_search_input = QLineEdit()
        self.proxy_search_input.setPlaceholderText("🔍 Cari Negara / Host:Port...")
        self.proxy_search_input.setFixedWidth(200)
        self.proxy_search_input.textChanged.connect(self.filter_proxy_table)
        pt_top.addWidget(self.proxy_search_input)

        reload_table_btn = QPushButton("🔄 Muat Ulang")
        reload_table_btn.setObjectName("SecondaryBtn")
        reload_table_btn.clicked.connect(self.reload_proxies_ui)
        pt_top.addWidget(reload_table_btn)

        pt_layout.addLayout(pt_top)

        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(7)
        self.proxy_table.setHorizontalHeaderLabels([
            "#", "Negara", "Host : Port", "Status Realtime", "Keterangan / Hasil Uji", "Worker", "Waktu Dicek"
        ])
        self.proxy_table.verticalHeader().setVisible(False)
        self.proxy_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.proxy_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.proxy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.proxy_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)

        pt_layout.addWidget(self.proxy_table)
        self.right_tabs.addTab(proxy_tab, "🌐 Live Proxy Monitor")

        # ------------------------------------------------------------------
        # TAB 3: 📋 Live Activity Console Log
        # ------------------------------------------------------------------
        console_tab = QWidget()
        ct_layout = QVBoxLayout(console_tab)
        ct_layout.setContentsMargins(10, 10, 10, 10)
        ct_layout.setSpacing(8)

        log_top_bar = QHBoxLayout()
        log_title = QLabel("📋 CATATAN AKTIVITAS BOT (TERMINAL REALTIME)")
        log_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        log_title.setStyleSheet("color: #cbd5e1; letter-spacing: 0.5px;")
        log_top_bar.addWidget(log_title)
        log_top_bar.addStretch()

        self.auto_scroll_check = QCheckBox("Scroll Otomatis")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.setStyleSheet("color: #94a3b8; font-size: 11px;")
        log_top_bar.addWidget(self.auto_scroll_check)

        clear_btn = QPushButton("Bersihkan Log")
        clear_btn.setObjectName("SecondaryBtn")
        clear_btn.clicked.connect(self.clear_logs)
        log_top_bar.addWidget(clear_btn)
        ct_layout.addLayout(log_top_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 9))
        self.log_text.setObjectName("TerminalBox")
        ct_layout.addWidget(self.log_text)

        self.right_tabs.addTab(console_tab, "📋 Live Console Log")

        right_layout.addWidget(self.right_tabs, stretch=1)

        main_layout.addWidget(right_panel, stretch=6)

    # ==========================================
    # Logic & Event Handlers
    # ==========================================
    def open_proxy_import_dialog(self):
        dlg = ProxyImportDialog(self)
        dlg.exec()

    def open_proxy_test_dialog(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(
                self,
                "Bot Sedang Berjalan",
                "Tes proksi tidak bisa dijalankan saat bot aktif.\n"
                "Menguji proksi yang sedang dipakai dapat membuat hasil tes tidak valid.\n\n"
                "Silakan hentikan bot terlebih dahulu.",
            )
            return
        dlg = ProxyTestDialog(self)
        dlg.exec()

    def reload_proxies_ui(self):
        self.proxies_data = load_proxies_data()
        total_all = len(self.proxies_data)
        total_alive = sum(1 for px in self.proxies_data if not px.get("dead", False))
        if hasattr(self, "use_proxy_check"):
            self.use_proxy_check.setText(f"Gunakan Proksi Residensial ({total_alive} Aktif / {total_all} Total)")
            self.use_proxy_check.setChecked(total_alive > 0)

        if hasattr(self, "proxy_combo"):
            self.proxy_combo.blockSignals(True)
            self.proxy_combo.clear()
            self.proxy_combo.addItem("🎲 Rotasi Acak Otomatis (Setiap Sesi Berganti Negara)")
            for i, px in enumerate(self.proxies_data):
                country = px.get("country", "Unknown")
                host = px.get("host", "")
                port = px.get("port", "")
                is_dead = px.get("dead", False)
                label = f"#{i+1}: 📍 {country} ({host}:{port})"
                if is_dead:
                    label = f"#{i+1}: ❌ {country} (MATI)"
                self.proxy_combo.addItem(label)
            self.proxy_combo.blockSignals(False)

        self.populate_proxy_table()

    def on_proxy_pruned(self, proxy_ref=None, remaining_count: int = 0):
        """
        Dipanggil ketika proksi di-flag dead (bukan dihapus) saat bot berjalan.
        Cukup reload data dan update tampilan tanpa menghapus baris dari tabel.
        """
        # 1. Update data internal proksi dari proxies.json
        self.proxies_data = load_proxies_data()
        total_alive = sum(1 for px in self.proxies_data if not px.get("dead", False))
        total_all = len(self.proxies_data)

        # 2. Update status label & checkbox di panel kiri
        if hasattr(self, "use_proxy_check"):
            self.use_proxy_check.setText(f"Gunakan Proksi Residensial ({total_alive} Aktif / {total_all} Total)")
            self.use_proxy_check.setChecked(total_alive > 0)

        # 3. Sinkronisasi tabel proksi — reload tabel untuk menampilkan flag dead
        if hasattr(self, "proxy_table"):
            # Simpan status worker yang sedang aktif memakai proksi sebelum reload tabel
            active_proxies = {}  # host:port -> (worker_label, status_text)
            for r in range(self.proxy_table.rowCount()):
                hp_item = self.proxy_table.item(r, 2)
                st_item = self.proxy_table.item(r, 3)
                w_item = self.proxy_table.item(r, 5)
                if hp_item and st_item and ("Dipakai" in st_item.text() or "Aktif" in st_item.text() or "Diuji" in st_item.text()):
                    active_proxies[hp_item.text().strip()] = (
                        w_item.text() if w_item else "-",
                        st_item.text()
                    )

            # Muat ulang tabel (proksi dead tetap tampil tapi dengan gaya merah)
            self.populate_proxy_table()

            # Pasang kembali tanda aktif/dipakai pada proksi yang sedang digunakan worker
            for r in range(self.proxy_table.rowCount()):
                hp_item = self.proxy_table.item(r, 2)
                if hp_item and hp_item.text().strip() in active_proxies:
                    w_label, st_text = active_proxies[hp_item.text().strip()]
                    st = self.proxy_table.item(r, 3)
                    if st:
                        st.setText(st_text)
                        st.setForeground(QColor("#38bdf8") if "Dipakai" in st_text else QColor("#4ade80"))
                    w = self.proxy_table.item(r, 5)
                    if w:
                        w.setText(w_label)
                        w.setForeground(QColor("#38bdf8"))

            self.update_proxy_stats_summary()

        # 4. Sinkronkan dropdown pilihan proksi (hanya proksi aktif)
        if hasattr(self, "proxy_combo"):
            self.proxy_combo.blockSignals(True)
            cur_idx = self.proxy_combo.currentIndex()
            self.proxy_combo.clear()
            self.proxy_combo.addItem("🎲 Rotasi Acak Otomatis (Setiap Sesi Berganti Negara)")
            for i, px in enumerate(self.proxies_data):
                country = px.get("country", "Unknown")
                host = px.get("host", "")
                port = px.get("port", "")
                is_dead = px.get("dead", False)
                label = f"#{i+1}: 📍 {country} ({host}:{port})"
                if is_dead:
                    label = f"#{i+1}: ❌ {country} (MATI)"
                self.proxy_combo.addItem(label)
            if 0 < cur_idx < self.proxy_combo.count():
                self.proxy_combo.setCurrentIndex(cur_idx)
            else:
                self.proxy_combo.setCurrentIndex(0)
            self.proxy_combo.blockSignals(False)

    def populate_proxy_table(self):
        if not hasattr(self, "proxy_table"):
            return
        self.proxies_data = load_proxies_data()
        self.proxy_table.setRowCount(0)
        self.proxy_table.setRowCount(len(self.proxies_data))

        for row, px in enumerate(self.proxies_data):
            c_code = px.get("country", "Global")
            host = px.get("host", "")
            port = px.get("port", "")
            user = px.get("username", "")
            is_dead = px.get("dead", False)
            hp = f"{host}:{port}"

            num_item = QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            num_item.setForeground(QColor("#f43f5e") if is_dead else QColor("#64748b"))
            num_item.setData(Qt.UserRole, user)
            num_item.setData(Qt.UserRole + 1, row + 1)

            country_item = QTableWidgetItem(f"📍 {c_code}")
            country_item.setForeground(QColor("#f43f5e") if is_dead else QColor("#f8fafc"))

            hp_item = QTableWidgetItem(hp)
            hp_item.setForeground(QColor("#f43f5e") if is_dead else QColor("#cbd5e1"))

            if is_dead:
                status_item = QTableWidgetItem("❌ Mati (sesi ini)")
                status_item.setForeground(QColor("#f43f5e"))
                desc_item = QTableWidgetItem("Dilewati sampai bot dijalankan ulang (tidak dihapus)")
                desc_item.setForeground(QColor("#f43f5e"))
            else:
                status_item = QTableWidgetItem("⚪ Standby")
                status_item.setForeground(QColor("#94a3b8"))
                desc_item = QTableWidgetItem("Siap Digunakan")
                desc_item.setForeground(QColor("#64748b"))

            worker_item = QTableWidgetItem("-")
            worker_item.setTextAlignment(Qt.AlignCenter)
            worker_item.setForeground(QColor("#64748b"))

            time_item = QTableWidgetItem("-")
            time_item.setTextAlignment(Qt.AlignCenter)
            time_item.setForeground(QColor("#64748b"))

            self.proxy_table.setItem(row, 0, num_item)
            self.proxy_table.setItem(row, 1, country_item)
            self.proxy_table.setItem(row, 2, hp_item)
            self.proxy_table.setItem(row, 3, status_item)
            self.proxy_table.setItem(row, 4, desc_item)
            self.proxy_table.setItem(row, 5, worker_item)
            self.proxy_table.setItem(row, 6, time_item)

        self.update_proxy_stats_summary()

    def update_proxy_stats_summary(self):
        if not hasattr(self, "proxy_table"):
            return
        total = self.proxy_table.rowCount()
        standby = 0
        in_use = 0
        dead = 0
        for r in range(total):
            s_item = self.proxy_table.item(r, 3)
            if s_item:
                txt = s_item.text()
                if "Dipakai" in txt or "Diuji" in txt:
                    in_use += 1
                elif "Mati" in txt:
                    dead += 1
                else:
                    standby += 1
        if hasattr(self, "proxy_stat_total"):
            self.proxy_stat_total.setText(f"Total: {total}")
            self.proxy_stat_standby.setText(f"⚪ Standby: {standby}")
            self.proxy_stat_in_use.setText(f"🚀 Dipakai: {in_use}")
            self.proxy_stat_dead.setText(f"❌ Mati: {dead}")

    def filter_proxy_table(self, query: str):
        if not hasattr(self, "proxy_table"):
            return
        query = query.strip().lower()
        for r in range(self.proxy_table.rowCount()):
            c_item = self.proxy_table.item(r, 1)
            hp_item = self.proxy_table.item(r, 2)
            c_text = c_item.text().lower() if c_item else ""
            hp_text = hp_item.text().lower() if hp_item else ""
            matches = (query in c_text) or (query in hp_text)
            self.proxy_table.setRowHidden(r, not matches)

    def on_proxy_status(self, proxy_ref, status_type: str, extra: str):
        if not hasattr(self, "proxy_table"):
            return
        row_count = self.proxy_table.rowCount()
        now_str = datetime.now().strftime("%H:%M:%S")

        matched_rows = []
        for r in range(row_count):
            item_0 = self.proxy_table.item(r, 0)
            if not item_0:
                continue
            init_id = item_0.data(Qt.UserRole + 1)
            user_id = item_0.data(Qt.UserRole)
            hp_item = self.proxy_table.item(r, 2)
            hp_text = hp_item.text().strip() if hp_item else ""

            if (proxy_ref == init_id) or (proxy_ref and proxy_ref == user_id) or (proxy_ref and proxy_ref == hp_text):
                matched_rows.append(r)
                break

        if not matched_rows:
            if isinstance(proxy_ref, int):
                r = proxy_ref - 1
                if 0 <= r < row_count:
                    matched_rows.append(r)
            elif isinstance(proxy_ref, str) and proxy_ref.isdigit():
                r = int(proxy_ref) - 1
                if 0 <= r < row_count:
                    matched_rows.append(r)

        for r in matched_rows:
            status_item = self.proxy_table.item(r, 3)
            if status_item:
                if status_type == "TESTING":
                    status_item.setText(f"🔍 Diuji ({extra})")
                    status_item.setForeground(QColor("#facc15"))
                elif status_type == "VALID":
                    status_item.setText("🟢 Aktif & Valid")
                    status_item.setForeground(QColor("#4ade80"))
                elif status_type == "IN_USE":
                    status_item.setText(f"🚀 Dipakai ({extra})")
                    status_item.setForeground(QColor("#38bdf8"))
                elif status_type == "DEAD":
                    status_item.setText("❌ Mati (sesi ini)")
                    status_item.setForeground(QColor("#f43f5e"))
                elif status_type == "COOLDOWN":
                    status_item.setText("⚠️ Gagal, belum mati")
                    status_item.setForeground(QColor("#facc15"))
                elif status_type == "STANDBY":
                    status_item.setText("⚪ Standby")
                    status_item.setForeground(QColor("#94a3b8"))

            desc_item = self.proxy_table.item(r, 4)
            if desc_item:
                if status_type == "TESTING":
                    desc_item.setText("Menguji kelayakan proksi...")
                    desc_item.setForeground(QColor("#64748b"))
                elif status_type == "VALID":
                    desc_item.setText(extra or "HTTP 200 OK")
                    desc_item.setForeground(QColor("#4ade80"))
                elif status_type == "DEAD":
                    desc_item.setText("Dilewati sampai bot dijalankan ulang (tidak dihapus)")
                    desc_item.setForeground(QColor("#f43f5e"))
                elif status_type == "COOLDOWN":
                    desc_item.setText("Belum mati, akan dicoba lagi")
                    desc_item.setForeground(QColor("#facc15"))
                elif status_type == "IN_USE":
                    desc_item.setText("Aktif digunakan oleh browser")
                    desc_item.setForeground(QColor("#38bdf8"))
                elif status_type == "STANDBY":
                    desc_item.setText("Siap Digunakan (Idle)")
                    desc_item.setForeground(QColor("#64748b"))

            if status_type == "DEAD":
                for col in (0, 1, 2):
                    it = self.proxy_table.item(r, col)
                    if it:
                        it.setForeground(QColor("#f43f5e"))

            w_item = self.proxy_table.item(r, 5)
            if w_item:
                if status_type in ("TESTING", "IN_USE"):
                    w_item.setText(extra if "Browser" in extra else f"Browser #{extra}")
                    w_item.setForeground(QColor("#38bdf8"))
                elif status_type in ("STANDBY", "DEAD", "COOLDOWN"):
                    w_item.setText("-")
                    w_item.setForeground(QColor("#64748b"))

            time_item = self.proxy_table.item(r, 6)
            if time_item:
                time_item.setText(now_str)

        self.update_proxy_stats_summary()

    def on_worker_flow(self, w_id: int, data: dict):
        if hasattr(self, "worker_cards") and w_id in self.worker_cards:
            self.worker_cards[w_id].update_flow(data)

    def on_concurrency_combo_changed(self, idx: int):
        concurrency_map = {0: 1, 1: 2, 2: 3, 3: 5, 4: 10, 5: 15, 6: 20}
        count = concurrency_map.get(idx, 5)
        if hasattr(self, "worker_cards"):
            for w_i, card in self.worker_cards.items():
                card.setVisible(w_i <= count)
        if hasattr(self, "worker_badges"):
            for w_i, badge in self.worker_badges.items():
                badge.setVisible(w_i <= count)
        if hasattr(self, "worker_count_badge"):
            self.worker_count_badge.setText(f"Browser Paralel: {count} Aktif")
        self.save_temporary_config()

    def on_pages_combo_changed(self, idx: int):
        pages_map = {0: 2, 1: 1, 2: 3, 3: 4}
        num_pages = pages_map.get(idx, 2)
        has_sl = True
        if hasattr(self, "sl_slider"):
            has_sl = self.sl_slider.value() > 0
        if hasattr(self, "worker_cards"):
            for card in self.worker_cards.values():
                card.reconfigure_flow(num_pages, has_sl)
        self.save_temporary_config()

    def on_slider_changed(self, value):
        category = "Aman / Wajar" if value <= 25 else ("Tinggi (High eCPM)" if value <= 75 else "Maksimal (Agresif)")
        self.sl_chance_label.setText(f"Peluang Klik: {value}% ({category})")
        self.save_temporary_config()

    def clear_logs(self):
        self.log_text.clear()

    def update_elapsed_time(self):
        if self.start_timestamp:
            elapsed_sec = int(time.time() - self.start_timestamp)
            mins = elapsed_sec // 60
            secs = elapsed_sec % 60
            self.time_badge.setText(f"⏱️ {mins:02d}:{secs:02d}")

        if hasattr(self, "worker_cards"):
            for card in self.worker_cards.values():
                card.tick_second()

    def on_log_received(self, timestamp: str, level: str, msg: str):
        color_map = {
            "INFO": "#94a3b8",      # Slate grey
            "SUCCESS": "#4ade80",   # Emerald green
            "POPUP": "#f472b6",     # Soft pink
            "ADS": "#fb923c",       # Orange
            "CLEAN": "#38bdf8",     # Cyan
            "SCROLL": "#a78bfa",    # Purple
            "CLICK": "#facc15",     # Yellow
            "TIMER": "#38bdf8",     # Sky blue
            "PAGE2": "#2dd4bf",     # Teal
            "WARN": "#facc15",      # Yellow
            "ERROR": "#f43f5e",     # Red
            "RAW": "#64748b"        # Dim grey
        }
        color = color_map.get(level, "#e2e8f0")

        badge_html = ""
        import re
        b_match = re.match(r"^\[B(\d+)\]\s*(.*)", msg)
        if b_match:
            b_id = int(b_match.group(1))
            msg = b_match.group(2)
            palette = WorkerCard.WORKER_PALETTES.get(b_id)
            if not palette:
                palette = WorkerCard.WORKER_PALETTES.get(((b_id - 1) % len(WorkerCard.WORKER_PALETTES)) + 1, WorkerCard.WORKER_PALETTES[1])
            fg = palette["fg"]
            bg = palette["bg"]
            badge_html = f"<span style='color: {fg}; background-color: {bg}; border: 1px solid {fg}44; padding: 1px 5px; border-radius: 4px; font-weight: bold; font-size: 10px; margin-right: 6px;'>Browser #{b_id}</span> "

        log_line = f"<div style='margin-bottom: 3px; font-family: monospace;'><span style='color: #475569;'>[{timestamp}]</span> {badge_html}<span style='color: {color};'>{msg}</span></div>"

        self.log_text.append(log_line)
        if self.auto_scroll_check.isChecked():
            self.log_text.moveCursor(QTextCursor.End)

    def on_status_received(self, short_status: str, detailed_step: str):
        self.step_label.setText(detailed_step)

        if short_status == "RUNNING" or short_status == "SURFING" or short_status == "READING":
            self.status_badge.setText("🟢 SEDANG BERJALAN")
            self.status_badge.setObjectName("StatusBadgeActive")
        elif short_status == "ADS" or short_status == "SMARTLINK":
            self.status_badge.setText("💥 INTERAKSI IKLAN")
            self.status_badge.setObjectName("StatusBadgeAds")
        elif short_status == "DWELL" or short_status == "COOLDOWN":
            self.status_badge.setText("⏳ JEDA / DWELL")
            self.status_badge.setObjectName("StatusBadgeDwell")
        elif short_status == "DONE":
            self.status_badge.setText("✅ SELESAI")
            self.status_badge.setObjectName("StatusBadgeDone")
        elif short_status == "ERROR":
            self.status_badge.setText("❌ TERJADI KENDALA")
            self.status_badge.setObjectName("StatusBadgeError")
        else:
            self.status_badge.setText("⚪ STANDBY")
            self.status_badge.setObjectName("StatusBadgeIdle")

        # Force style re-polish
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def on_session_combo_changed(self, index: int):
        self.custom_session_spin.setVisible(index == 6)
        total_px = len(self.proxies_data) if self.proxies_data else 120
        if index == 0:
            self.session_helper.setText("♾️ Mode Unlimited Aktif: Bot akan memproses 120 proksi per siklus lalu otomatis mengulang tanpa henti 24 jam.")
            self.session_helper.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
            self.loop_check.setChecked(True)
        elif index == 1:
            self.session_helper.setText(f"🎯 {total_px} Sesi: Seluruh {total_px} proksi akan dipakai masing-masing tepat 1 kali.")
            self.session_helper.setStyleSheet("color: #4ade80; font-size: 11px;")
            self.loop_check.setChecked(False)
        elif index == 2:
            self.session_helper.setText(f"🔄 {total_px * 2} Sesi: Seluruh {total_px} proksi akan dipakai masing-masing 2 kali putaran.")
            self.session_helper.setStyleSheet("color: #a78bfa; font-size: 11px;")
            self.loop_check.setChecked(False)
        elif index == 3:
            self.session_helper.setText(f"🚀 {total_px * 3} Sesi: Seluruh {total_px} proksi akan dipakai masing-masing 3 kali putaran.")
            self.session_helper.setStyleSheet("color: #f472b6; font-size: 11px;")
            self.loop_check.setChecked(False)
        elif index == 4:
            self.session_helper.setText("⚡ 60 Sesi: Setengah putaran proksi (60 pengunjung unik).")
            self.session_helper.setStyleSheet("color: #38bdf8; font-size: 11px;")
            self.loop_check.setChecked(False)
        elif index == 5:
            self.session_helper.setText("🧪 10 Sesi: Uji coba cepat untuk memastikan iklan & views tercatat.")
            self.session_helper.setStyleSheet("color: #facc15; font-size: 11px;")
            self.loop_check.setChecked(False)
        else:
            self.session_helper.setText("✏️ Kustom: Masukkan jumlah sesi bebas sesuai keinginan Anda pada kotak di samping.")
            self.session_helper.setStyleSheet("color: #cbd5e1; font-size: 11px;")
            self.loop_check.setChecked(False)

    def on_worker_activity(self, worker_id: int, status: str):
        if not hasattr(self, "worker_badges") or worker_id not in self.worker_badges:
            return
        badge = self.worker_badges[worker_id]
        if status == "NAVIGATE":
            badge.setText(f"#B{worker_id}: 🌐 Buka")
            badge.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #0284c7; color: #ffffff; border: 1px solid #38bdf8;")
        elif status == "DWELL":
            badge.setText(f"#B{worker_id}: ⌛ Dwell")
            badge.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #1e3a8a; color: #93c5fd; border: 1px solid #2563eb;")
        elif status == "READING":
            badge.setText(f"#B{worker_id}: 📖 Baca")
            badge.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #7c3aed; color: #ffffff; border: 1px solid #c084fc;")
        elif status == "ADS":
            badge.setText(f"#B{worker_id}: 💥 Iklan")
            badge.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #db2777; color: #ffffff; border: 1px solid #f472b6;")
        elif status == "IDLE":
            badge.setText(f"#B{worker_id}: ⏳ Selesai")
            badge.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #064e3b; color: #34d399; border: 1px solid #059669;")

    def reset_worker_badges(self):
        if hasattr(self, "worker_badges"):
            for w_i, badge in self.worker_badges.items():
                badge.setText(f"#B{w_i}: Siap")
                badge.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #1e293b; color: #64748b; border: 1px solid #334155;")

    def on_session_progress(self, current: int, total: int):
        self.completed_sessions_count = current
        self.total_sessions_target = total
        if getattr(self, "is_unlimited", False):
            self.session_badge.setText(f"SESI: {current} / ∞ (Unlimited)")
            self.step_label.setText(f"♾️ [Mode Non-Stop 24 Jam] Menjalankan Sesi #{current} tanpa henti...")
        else:
            self.session_badge.setText(f"SESI: {current} / {total}")
            if total > 0:
                pct = int((current / total) * 100)
                self.progress_bar.setValue(pct)

    def on_proxy_info(self, country: str, host_port: str):
        self.metric_proxy.setText(country)

    def start_bot(self):
        self.save_temporary_config()
        self.proxies_data = load_proxies_data()

        args = []
        target_raw = self.target_url_combo.currentText().strip()
        target_url = "http://localhost:3000" if "localhost" in target_raw else "https://read.riztama.my.id"
        if "localhost" in target_raw:
            args.append("--local")

        slug = self.slug_input.text().strip()
        if slug:
            args.extend(["--slug", slug])

        if self.headless_check.isChecked():
            args.append("--headless")

        # Session Mode Handling (Unlimited vs Fixed Number)
        s_idx = self.session_combo.currentIndex()
        is_unlimited = (s_idx == 0) or self.loop_check.isChecked()

        total_px = len(self.proxies_data) if self.proxies_data else 120
        if s_idx == 0:  # Unlimited Mode
            args.append("--loop")
            sessions = total_px
            args.extend(["--sessions", str(sessions)])
        elif s_idx == 1:
            sessions = total_px
            args.extend(["--sessions", str(sessions)])
        elif s_idx == 2:
            sessions = total_px * 2
            args.extend(["--sessions", str(sessions)])
        elif s_idx == 3:
            sessions = total_px * 3
            args.extend(["--sessions", str(sessions)])
        elif s_idx == 4:
            sessions = 60
            args.extend(["--sessions", "60"])
        elif s_idx == 5:
            sessions = 10
            args.extend(["--sessions", "10"])
        else:  # Custom
            sessions = self.custom_session_spin.value()
            args.extend(["--sessions", str(sessions)])

        if self.loop_check.isChecked() and "--loop" not in args:
            args.append("--loop")

        pages_map = {0: 2, 1: 1, 2: 3, 3: 4}
        selected_pages = pages_map.get(self.pages_combo.currentIndex(), 2)
        args.extend(["--pages-per-session", str(selected_pages)])

        concurrency_map = {0: 1, 1: 2, 2: 3, 3: 5, 4: 10, 5: 15, 6: 20}
        selected_c = concurrency_map.get(self.concurrency_combo.currentIndex(), 1)
        args.extend(["--concurrency", str(selected_c)])

        if self.return_home_check.isChecked():
            args.append("--return-home")

        if not self.use_proxy_check.isChecked():
            args.append("--no-proxy")
        else:
            p_idx = self.proxy_combo.currentIndex()
            if p_idx > 0:
                args.extend(["--proxy-index", str(p_idx - 1)])

        self.run_worker(args, target_url, sessions, is_unlimited=is_unlimited)

    def run_quick_test(self):
        target_raw = self.target_url_combo.currentText().strip()
        target_url = "http://localhost:3000" if "localhost" in target_raw else "https://read.riztama.my.id"

        args = ["--sessions", "1"]
        if "localhost" in target_raw:
            args.append("--local")

        slug = self.slug_input.text().strip()
        if slug:
            args.extend(["--slug", slug])

        pages_map = {0: 2, 1: 1, 2: 3, 3: 4}
        selected_pages = pages_map.get(self.pages_combo.currentIndex(), 2)
        args.extend(["--pages-per-session", str(selected_pages)])

        if self.return_home_check.isChecked():
            args.append("--return-home")

        if not self.use_proxy_check.isChecked():
            args.append("--no-proxy")
        else:
            p_idx = self.proxy_combo.currentIndex()
            if p_idx > 0:
                args.extend(["--proxy-index", str(p_idx - 1)])

        self.run_worker(args, target_url, 1, is_unlimited=False)

    def save_temporary_config(self):
        try:
            cfg = load_config_data()
            cfg["dwell_time"]["min_seconds"] = self.min_dwell_spin.value()
            cfg["dwell_time"]["max_seconds"] = self.max_dwell_spin.value()
            cfg["smartlink_click_chance"] = self.sl_slider.value() / 100.0
            pages_map = {0: 2, 1: 1, 2: 3, 3: 4}
            cfg["max_pages_per_session"] = pages_map.get(self.pages_combo.currentIndex(), 2)
            cfg["return_home_between_posts"] = self.return_home_check.isChecked()
            concurrency_map = {0: 1, 1: 2, 2: 3, 3: 5, 4: 10, 5: 15, 6: 20}
            cfg["concurrency"] = concurrency_map.get(self.concurrency_combo.currentIndex(), 1)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def run_worker(self, args, target_url, sessions, is_unlimited=False):
        self.is_unlimited = is_unlimited
        # Bersihkan status "Dipakai" yang tertinggal dari run sebelumnya
        if hasattr(self, "proxy_table"):
            self.populate_proxy_table()
        self.start_btn.setEnabled(False)
        self.quick_test_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.metric_target.setText(target_url)
        if self.is_unlimited:
            self.session_badge.setText("SESI: 1 / ∞ (Unlimited)")
            self.progress_bar.setRange(0, 0) # Indeterminate animated bar
        else:
            self.session_badge.setText(f"SESI: 1 / {sessions}")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(5)

        self.start_timestamp = time.time()
        self.elapsed_timer.start(1000)

        concurrency_map = {0: 1, 1: 2, 2: 3, 3: 5, 4: 10, 5: 15, 6: 20}
        active_c = concurrency_map.get(self.concurrency_combo.currentIndex(), 1)
        for w_i in range(1, 21):
            if w_i in self.worker_badges:
                if w_i <= active_c:
                    self.worker_badges[w_i].setVisible(True)
                    self.worker_badges[w_i].setText(f"#B{w_i}: 🚀 Mulai")
                    self.worker_badges[w_i].setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #0369a1; color: #ffffff; border: 1px solid #38bdf8;")
                else:
                    self.worker_badges[w_i].setVisible(False)
                    self.worker_badges[w_i].setText(f"#B{w_i}: Off")
                    self.worker_badges[w_i].setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 4px; border-radius: 4px; background: #0f172a; color: #475569; border: 1px solid #1e293b;")

        if hasattr(self, "worker_cards"):
            for w_i, card in self.worker_cards.items():
                card.reset_state()
                card.setVisible(w_i <= active_c)

        mode_str = "Mode Unlimited 24 Jam (Tanpa Henti)" if is_unlimited else f"Total: {sessions} Sesi"
        self.on_log_received(datetime.now().strftime("%H:%M:%S"), "INFO", "==================================================")
        self.on_log_received(datetime.now().strftime("%H:%M:%S"), "SUCCESS", f"🚀 Memulai Otomasi Bot (Target: {target_url}, {mode_str}, {active_c} Browser Paralel)")

        self.worker = BotProcessWorker(args)
        self.worker.log_signal.connect(self.on_log_received)
        self.worker.status_signal.connect(self.on_status_received)
        self.worker.session_progress_signal.connect(self.on_session_progress)
        self.worker.worker_activity_signal.connect(self.on_worker_activity)
        self.worker.worker_flow_signal.connect(self.on_worker_flow)
        self.worker.proxy_status_signal.connect(self.on_proxy_status)
        self.worker.proxy_info_signal.connect(self.on_proxy_info)
        self.worker.proxy_pruned_signal.connect(self.on_proxy_pruned)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def stop_bot(self):
        if self.worker:
            self.on_log_received(datetime.now().strftime("%H:%M:%S"), "WARN", "⏹ Menghentikan bot sesuai permintaan pengguna...")
            self.worker.stop()
            self.on_status_received("IDLE", "Bot dihentikan oleh pengguna.")
            self.reset_worker_badges()
            if hasattr(self, "worker_cards"):
                for card in self.worker_cards.values():
                    card.reset_state()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.reload_proxies_ui()

    def on_worker_finished(self):
        self.start_btn.setEnabled(True)
        self.quick_test_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.elapsed_timer.stop()
        self.reset_worker_badges()
        if hasattr(self, "worker_cards"):
            for card in self.worker_cards.values():
                card.reset_state()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.reload_proxies_ui()
        self.on_log_received(datetime.now().strftime("%H:%M:%S"), "SUCCESS", "🏁 Proses selesai. Siap untuk pengujian berikutnya.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        event.accept()

    def apply_premium_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #090d16;
            }
            QWidget {
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Inter', Roboto, sans-serif;
                font-size: 12px;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QGroupBox {
                border: 1px solid #1e293b;
                border-radius: 10px;
                margin-top: 14px;
                font-weight: bold;
                color: #cbd5e1;
                padding-top: 16px;
                background-color: #0f172a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #38bdf8;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QFrame#Card {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
            }
            QFrame#HeaderCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f172a, stop:1 #1e293b);
                border: 1px solid #334155;
                border-radius: 10px;
            }
            QFrame#StatusCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #0b1120);
                border: 1px solid #1e293b;
                border-radius: 10px;
            }
            QLabel#StatusBadgeIdle {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #334155;
            }
            QLabel#StatusBadgeActive {
                background-color: #064e3b;
                color: #34d399;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #059669;
            }
            QLabel#StatusBadgeAds {
                background-color: #701a75;
                color: #f472b6;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #c026d3;
            }
            QLabel#StatusBadgeDwell {
                background-color: #1e3a8a;
                color: #60a5fa;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #2563eb;
            }
            QLabel#StatusBadgeDone {
                background-color: #064e3b;
                color: #6ee7b7;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #10b981;
            }
            QLabel#StatusBadgeError {
                background-color: #4c0519;
                color: #fda4af;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #e11d48;
            }
            QLabel#SessionBadge, QLabel#TimeBadge {
                background-color: #1e293b;
                color: #e2e8f0;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #334155;
            }
            QProgressBar {
                background-color: #1e293b;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 4px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #162032;
                border: 1px solid #293548;
                border-radius: 6px;
                padding: 7px 10px;
                color: #f8fafc;
                selection-background-color: #3b82f6;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #38bdf8;
                background-color: #1a263d;
            }
            QComboBox::drop-down {
                border: none;
                margin-right: 6px;
            }
            QCheckBox {
                color: #cbd5e1;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #162032;
            }
            QCheckBox::indicator:checked {
                background-color: #38bdf8;
                border-color: #0284c7;
            }
            QPushButton#QuickTestBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border-radius: 8px;
                padding: 10px;
                border: none;
            }
            QPushButton#QuickTestBtn:hover {
                background: #1d4ed8;
            }
            QPushButton#StartBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border-radius: 8px;
                padding: 11px;
                border: none;
            }
            QPushButton#StartBtn:hover {
                background: #047857;
            }
            QPushButton#StartBtn:disabled, QPushButton#QuickTestBtn:disabled {
                background: #1e293b;
                color: #475569;
            }
            QPushButton#StopBtn {
                background: #e11d48;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border-radius: 8px;
                padding: 9px;
                border: none;
            }
            QPushButton#StopBtn:hover {
                background: #be123c;
            }
            QPushButton#StopBtn:disabled {
                background: #1e293b;
                color: #475569;
            }
            QPushButton#SecondaryBtn {
                background-color: #1e293b;
                color: #94a3b8;
                border-radius: 6px;
                padding: 4px 10px;
                border: 1px solid #334155;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #334155;
                color: #f8fafc;
            }
            QPushButton#PresetBtn {
                background-color: #1e293b;
                color: #cbd5e1;
                font-weight: 600;
                font-size: 11px;
                border-radius: 6px;
                padding: 6px 8px;
                border: 1px solid #334155;
            }
            QPushButton#PresetBtn:hover {
                background-color: #293548;
                color: #38bdf8;
                border-color: #38bdf8;
            }
            QTextEdit#TerminalBox {
                background-color: #030712;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px;
                color: #f3f4f6;
                line-height: 1.5;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #1e293b;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #38bdf8;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #f8fafc;
                border: 2px solid #38bdf8;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            /* Tabs */
            QTabWidget::pane {
                border: 1px solid #1e293b;
                border-radius: 10px;
                background-color: #0b1120;
                top: -1px;
            }
            QTabBar::tab {
                background: #0f172a;
                color: #94a3b8;
                padding: 10px 18px;
                margin-right: 6px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #1e293b;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #0284c7;
                color: #ffffff;
                border-color: #38bdf8;
            }
            QTabBar::tab:hover:!selected {
                background: #1e293b;
                color: #f1f5f9;
            }

            /* Proxy Table */
            QTableWidget {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 8px;
                gridline-color: #1e293b;
                color: #e2e8f0;
                font-size: 11px;
                selection-background-color: #1e3a8a;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 6px;
                border: none;
                border-bottom: 2px solid #1e293b;
                border-right: 1px solid #1e293b;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #131f37;
            }
            QTableWidget::item:selected {
                background-color: #1e3a8a;
            }
        """)


def main():
    app = QApplication(sys.argv)
    window = TrafficBotGUI()
    window.show()
    try:
        ret = app.exec()
    except Exception:
        ret = 0
    sys.exit(ret)


if __name__ == "__main__":
    main()
