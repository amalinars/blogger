#!/usr/bin/env python3
"""
YouTube Organic Search & View Suite — Dashboard GUI Modern
Dilengkapi Real-time IP Tracker, Output IP Publik, Status Ads YouTube, & Multi-Worker Monitor.
"""

import os
import sys
import json
import time
import re
import random
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QCheckBox, QSlider,
    QComboBox, QTextEdit, QGroupBox, QFrame, QGridLayout, QProgressBar,
    QTabWidget, QScrollArea, QSizePolicy, QDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QFont, QColor, QTextCursor

from automation.youtube.bot import (
    load_config, load_proxies, UniqueProxyPool, worker_loop,
    test_proxy_youtube, format_time
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
PROXIES_PATH = PROJECT_ROOT / "automation" / "proxies.json"

COUNTRY_FLAGS = {
    "united states": "🇺🇸",
    "usa": "🇺🇸",
    "us": "🇺🇸",
    "united kingdom": "🇬🇧",
    "uk": "🇬🇧",
    "great britain": "🇬🇧",
    "gb": "🇬🇧",
    "canada": "🇨🇦",
    "ca": "🇨🇦",
    "australia": "🇦🇺",
    "au": "🇦🇺",
    "france": "🇫🇷",
    "fr": "🇫🇷",
    "germany": "🇩🇪",
    "de": "🇩🇪",
    "japan": "🇯🇵",
    "jp": "🇯🇵",
    "singapore": "🇸🇬",
    "sg": "🇸🇬",
    "indonesia": "🇮🇩",
    "id": "🇮🇩",
    "netherlands": "🇳🇱",
    "nl": "🇳🇱",
}


def get_country_badge(country_name: str) -> str:
    clean = (country_name or "").strip().lower()
    for k, flag in COUNTRY_FLAGS.items():
        if k in clean:
            return f"{flag} {country_name}"
    return f"🌍 {country_name}"


class NoWheelComboBox(QComboBox):
    """Mencegah perubahan dropdown secara tidak sengaja saat mouse wheel scrolling."""
    def wheelEvent(self, event):
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """Mencegah pergeseran angka spinbox saat mouse wheel scrolling."""
    def wheelEvent(self, event):
        event.ignore()


class NoWheelSlider(QSlider):
    """Mencegah slider bergeser saat scrolling."""
    def wheelEvent(self, event):
        event.ignore()


class ProxyTesterThread(QThread):
    """Thread mandiri untuk menguji daftar proksi di latar belakang dan membaca exit IP publik."""
    proxy_result_signal = Signal(int, bool, str, int, str)  # row, is_ok, msg, lat, exit_ip
    finished_signal = Signal(int, int)  # total_ok, total_tested

    def __init__(self, proxies: List[Dict[str, Any]]):
        super().__init__()
        self.proxies = proxies
        self.is_cancelled = False

    def run(self):
        total_ok = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_idx = {
                executor.submit(test_proxy_youtube, p, 5.0, True): idx
                for idx, p in enumerate(self.proxies)
            }
            for fut in as_completed(future_to_idx):
                if self.is_cancelled:
                    break
                idx = future_to_idx[fut]
                try:
                    is_ok, msg, lat, exit_ip = fut.result()
                    if is_ok:
                        total_ok += 1
                    self.proxy_result_signal.emit(idx, is_ok, msg, lat, exit_ip)
                except Exception as e:
                    self.proxy_result_signal.emit(idx, False, str(e), 0, "")
        self.finished_signal.emit(total_ok, len(self.proxies))

    def cancel(self):
        self.is_cancelled = True


class YouTubeBotThread(QThread):
    """Thread pengendali otomasi YouTube multi-worker."""
    log_signal = Signal(str, str)  # message, color/type
    worker_event_signal = Signal(str, dict)  # event_type, data
    finished_signal = Signal()

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.stop_event = threading.Event()

    def run(self):
        concurrency = self.config.get("concurrency", 5)
        use_proxy = self.config.get("use_proxy", True)
        proxy_source = self.config.get("proxy_source", "automation/proxies.json")

        self.log_signal.emit(f"🚀 Memulai YouTube Bot Engine ({concurrency} Worker Concurrency)...", "#38bdf8")

        raw_proxies = []
        if use_proxy:
            raw_proxies = load_proxies(proxy_source)
            self.log_signal.emit(f"📦 Dimuat {len(raw_proxies)} proksi residential dari proxies.json.", "#a78bfa")
        else:
            self.log_signal.emit("⚡ Mode Direct Connection: Menjalankan bot tanpa proksi.", "#f59e0b")

        proxy_pool = UniqueProxyPool(raw_proxies)

        def event_dispatcher(event_type: str, data: dict):
            self.worker_event_signal.emit(event_type, data)
            w_id = data.get("worker_id", 1)
            tag = f"[W{w_id}]"
            if event_type == "ad_event":
                status = data.get("status", "")
                color = "#f59e0b" if "Sedang" in status else ("#10b981" if "skip" in status.lower() else "#94a3b8")
                self.log_signal.emit(f"{tag} 🎬 [ADS TRACKER] {status}", color)
            elif event_type == "video_picked":
                title = data.get("title", "")
                self.log_signal.emit(f"{tag} 🎬 [VIDEO] {title}", "#38bdf8")
            elif event_type == "proxy_assigned":
                exit_ip = data.get("exit_ip", "")
                h = data.get("host", "")
                p = data.get("port", "")
                c = data.get("country", "")
                lat = data.get("latency", 0)
                flag_c = get_country_badge(c)
                self.log_signal.emit(f"{tag} 🛡️ [IP ASSIGNED] Exit: {exit_ip} | Gateway: {h}:{p} ({flag_c}) - {lat}ms", "#10b981")
            elif event_type == "proxy_failed":
                h = data.get("host", "")
                p = data.get("port", "")
                c = data.get("country", "")
                self.log_signal.emit(f"{tag} ❌ [IP FAILED] {h}:{p} ({c}) gagal ping. Dibuang.", "#ef4444")

        try:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(
                        worker_loop,
                        w_id,
                        proxy_pool,
                        self.config,
                        self.stop_event,
                        concurrency,
                        event_dispatcher
                    )
                    for w_id in range(1, concurrency + 1)
                ]
                for f in as_completed(futures):
                    try:
                        f.result()
                    except Exception as e:
                        self.log_signal.emit(f"[-] Worker exception: {e}", "#ef4444")
        except Exception as e:
            self.log_signal.emit(f"[-] Bot engine notice: {e}", "#ef4444")
        finally:
            self.log_signal.emit("⏹ Seluruh worker YouTube telah berhenti.", "#94a3b8")
            self.finished_signal.emit()

    def stop(self):
        self.stop_event.set()


class WorkerCardWidget(QFrame):
    """Kartu status real-time per worker: IP Tracker, Progres Tonton, & Status Ads."""
    def __init__(self, worker_id: int):
        super().__init__()
        self.worker_id = worker_id
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 12px;
                padding: 10px;
            }
            QFrame:hover {
                border-color: #374151;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header: Worker ID + Status Badge
        h_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"Worker #{worker_id}")
        self.title_lbl.setStyleSheet("font-weight: bold; color: #f3f4f6; font-size: 13px;")

        self.status_pill = QLabel("IDLE")
        self.status_pill.setStyleSheet("""
            background-color: #1f2937;
            color: #94a3b8;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 6px;
        """)
        h_layout.addWidget(self.title_lbl)
        h_layout.addStretch()
        h_layout.addWidget(self.status_pill)
        layout.addLayout(h_layout)

        # IP Tracker Info Box (Menampilkan Real Output IP Publik & Bendera Negara)
        self.ip_box = QFrame()
        self.ip_box.setStyleSheet("background-color: #0b0f19; border: 1px dashed #374151; border-radius: 8px; padding: 6px;")
        ip_layout = QVBoxLayout(self.ip_box)
        ip_layout.setContentsMargins(8, 6, 8, 6)
        ip_layout.setSpacing(3)

        self.ip_lbl = QLabel("🛡️ IP Publik: Menunggu tugas...")
        self.ip_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #38bdf8; font-weight: bold;")
        
        self.geo_lbl = QLabel("🌍 Lokasi: - | Gateway: -")
        self.geo_lbl.setStyleSheet("font-size: 10px; color: #9ca3af;")

        self.lat_lbl = QLabel("⚡ Latency Ping: -")
        self.lat_lbl.setStyleSheet("font-size: 10px; color: #10b981; font-weight: 600;")

        ip_layout.addWidget(self.ip_lbl)
        ip_layout.addWidget(self.geo_lbl)
        ip_layout.addWidget(self.lat_lbl)
        layout.addWidget(self.ip_box)

        # Video Target Title
        self.video_lbl = QLabel("🎬 Video: Menunggu pencarian channel...")
        self.video_lbl.setStyleSheet("color: #e5e7eb; font-size: 11px;")
        self.video_lbl.setWordWrap(True)
        layout.addWidget(self.video_lbl)

        # Progress Bar & Time Text
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1f2937;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #ef4444;
                border-radius: 4px;
            }
        """)
        self.time_lbl = QLabel("⏱️ 00:00 / 00:00 (0%)")
        self.time_lbl.setStyleSheet("font-family: monospace; font-size: 10px; color: #9ca3af;")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.time_lbl)

        # Ads Tracker Status Pill
        self.ads_pill = QLabel("🎬 Ads: Belum terdeteksi")
        self.ads_pill.setStyleSheet("""
            background-color: rgba(31, 41, 55, 0.7);
            color: #9ca3af;
            font-size: 10px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid #374151;
        """)
        layout.addWidget(self.ads_pill)

    def set_status(self, text: str, color: str = "#94a3b8", bg: str = "#1f2937"):
        self.status_pill.setText(text.upper())
        self.status_pill.setStyleSheet(f"background-color: {bg}; color: {color}; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 6px;")

    def set_proxy(self, host: str, port: str, country: str, latency: int = 0, exit_ip: str = ""):
        flag_c = get_country_badge(country)
        disp_ip = exit_ip if exit_ip else f"{host}:{port}"
        self.ip_lbl.setText(f"🛡️ IP Publik: {disp_ip}")
        self.ip_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #10b981; font-weight: bold;")
        self.geo_lbl.setText(f"{flag_c} • Gateway: {host}:{port}")
        self.lat_lbl.setText(f"⚡ Latency Ping: {latency}ms (🟢 Responsif)")

    def set_testing_proxy(self, host: str, port: str, country: str):
        flag_c = get_country_badge(country)
        self.ip_lbl.setText(f"🛡️ Menguji: {host}:{port}")
        self.ip_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #f59e0b; font-weight: bold;")
        self.geo_lbl.setText(f"{flag_c} • Sedang verifikasi...")
        self.lat_lbl.setText("⚡ Menghubungi server YouTube...")

    def set_video(self, title: str):
        disp_title = (title[:45] + "...") if len(title) > 45 else title
        self.video_lbl.setText(f"🎬 {disp_title}")

    def update_progress(self, percent: float, current_str: str, target_str: str):
        self.progress_bar.setValue(int(percent))
        self.time_lbl.setText(f"⏱️ {current_str} / {target_str} ({int(percent)}%)")

    def set_ad_status(self, status: str, action: str = "clean"):
        self.ads_pill.setText(f"🎬 {status}")
        if action == "skipped":
            self.ads_pill.setStyleSheet("background-color: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 10px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
        elif action == "playing":
            self.ads_pill.setStyleSheet("background-color: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4); font-size: 10px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
        else:
            self.ads_pill.setStyleSheet("background-color: rgba(31, 41, 55, 0.7); color: #94a3b8; border: 1px solid #374151; font-size: 10px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")


class YouTubeSuiteWindow(QMainWindow):
    """Jendela Utama Dashboard YouTube Automation Suite."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Organic Retention & Ad Viewer Suite — Fast Dashboard")
        self.resize(1200, 860)
        self.setMinimumSize(980, 700)

        self.bot_thread: Optional[YouTubeBotThread] = None
        self.proxy_tester_thread: Optional[ProxyTesterThread] = None
        self.worker_cards: Dict[int, WorkerCardWidget] = {}

        # Counter stats
        self.stat_views_completed = 0
        self.stat_ads_skipped = 0

        self.init_ui()
        self.load_saved_config()
        self.load_proxy_table()

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b0f19;
                color: #f3f4f6;
            }
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                color: #f3f4f6;
            }
            QTabWidget::pane {
                border: 1px solid #1f2937;
                background-color: #0f172a;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #111827;
                color: #94a3b8;
                padding: 10px 20px;
                font-weight: 600;
                font-size: 12px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0f172a;
                color: #ef4444;
                border-bottom: 2px solid #ef4444;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 12px;
                color: #f8fafc;
                font-size: 12px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #ef4444;
            }
            QPushButton {
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 12px;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(14)

        # Header Bar
        header = QHBoxLayout()
        logo_icon = QLabel("🎬")
        logo_icon.setStyleSheet("font-size: 26px;")
        header.addWidget(logo_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        h_title = QLabel("YouTube Organic Retention & Ad Viewer Suite")
        h_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        h_sub = QLabel("1 Video 1 Proxy Residential • 144p Ultra-Lite • Real-Time Ads & Exit IP Tracker")
        h_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_box.addWidget(h_title)
        title_box.addWidget(h_sub)
        header.addLayout(title_box)
        header.addStretch()

        # Top KPI Badges
        self.kpi_views = self._create_kpi_badge("Views Berhasil", "0", "#10b981")
        self.kpi_ads = self._create_kpi_badge("Iklan Terdeteksi", "0", "#f59e0b")
        self.kpi_proxies = self._create_kpi_badge("Proksi Tersedia", "0", "#38bdf8")
        header.addWidget(self.kpi_views)
        header.addWidget(self.kpi_ads)
        header.addWidget(self.kpi_proxies)

        main_layout.addLayout(header)

        # Tabs Widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        # Tab 1: Monitor & Pengaturan
        self.tab_monitor = QWidget()
        self.init_monitor_tab()
        self.tabs.addTab(self.tab_monitor, "📊 Monitor Worker & Pengaturan")

        # Tab 2: IP Tracker & Penguji Proksi
        self.tab_proxies = QWidget()
        self.init_proxy_tab()
        self.tabs.addTab(self.tab_proxies, "🛡️ IP Tracker & Proksi")

        # Tab 3: Konsol Terminal Real-Time
        self.tab_logs = QWidget()
        self.init_logs_tab()
        self.tabs.addTab(self.tab_logs, "💻 Terminal Log")

        # Footer Action Bar
        action_bar = QHBoxLayout()
        self.start_btn = QPushButton("▶ Mulai Bot YouTube")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #dc2626);
                color: white;
                font-size: 14px;
                padding: 12px 28px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f87171, stop:1 #ef4444);
            }
            QPushButton:disabled {
                background: #374151;
                color: #9ca3af;
            }
        """)
        self.start_btn.clicked.connect(self.start_bot)

        self.stop_btn = QPushButton("⏹ Hentikan Bot")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #f8fafc;
                font-size: 14px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #6b7280;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_bot)

        action_bar.addWidget(self.start_btn)
        action_bar.addWidget(self.stop_btn)
        action_bar.addStretch()

        self.status_footer_lbl = QLabel("Status: Bot Siap Dijalankan")
        self.status_footer_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        action_bar.addWidget(self.status_footer_lbl)

        main_layout.addLayout(action_bar)

    def _create_kpi_badge(self, label: str, val: str, color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 8px;
                padding: 4px 12px;
            }
        """)
        l = QVBoxLayout(frame)
        l.setContentsMargins(4, 4, 4, 4)
        l.setSpacing(0)
        lbl = QLabel(label.upper())
        lbl.setStyleSheet("font-size: 9px; color: #94a3b8; font-weight: bold;")
        num = QLabel(val)
        num.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")
        l.addWidget(lbl)
        l.addWidget(num)
        frame.val_label = num
        return frame

    def init_monitor_tab(self):
        layout = QHBoxLayout(self.tab_monitor)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(16)

        # Left Column: Configuration Settings
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFixedWidth(360)
        config_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        cfg_widget = QWidget()
        cfg_layout = QVBoxLayout(cfg_widget)
        cfg_layout.setContentsMargins(0, 0, 8, 0)
        cfg_layout.setSpacing(12)

        # Group 1: Target YouTube
        g1 = QGroupBox("Target Penelusuran Organik")
        g1.setStyleSheet("QGroupBox { font-weight: bold; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; margin-top: 10px; padding-top: 12px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }")
        g1_l = QVBoxLayout(g1)
        g1_l.setSpacing(8)

        g1_l.addWidget(QLabel("Kata Kunci Pencarian (Search):"))
        self.search_input = QLineEdit("horrornologi")
        g1_l.addWidget(self.search_input)

        g1_l.addWidget(QLabel("Target Channel (Handle / Nama):"))
        self.channel_input = QLineEdit("horrornologi")
        g1_l.addWidget(self.channel_input)
        cfg_layout.addWidget(g1)

        # Group 2: Performa & Concurrency
        g2 = QGroupBox("Performa & Batch Concurrency")
        g2.setStyleSheet("QGroupBox { font-weight: bold; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; margin-top: 10px; padding-top: 12px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }")
        g2_l = QVBoxLayout(g2)
        g2_l.setSpacing(8)

        g2_l.addWidget(QLabel("Jumlah Worker Bersamaan:"))
        self.concurrency_spin = NoWheelSpinBox()
        self.concurrency_spin.setRange(1, 10)
        self.concurrency_spin.setValue(5)
        self.concurrency_spin.valueChanged.connect(self.rebuild_worker_cards)
        g2_l.addWidget(self.concurrency_spin)

        self.headless_cb = QCheckBox("Mode Headless (Jalan di latar belakang)")
        self.headless_cb.setStyleSheet("color: #38bdf8; font-weight: bold;")
        g2_l.addWidget(self.headless_cb)

        self.proxy_cb = QCheckBox("Gunakan Proksi (1 Video 1 IP Unik)")
        self.proxy_cb.setChecked(True)
        self.proxy_cb.setStyleSheet("color: #10b981; font-weight: bold;")
        g2_l.addWidget(self.proxy_cb)

        g2_l.addWidget(QLabel("Kualitas Resolusi Pemutaran:"))
        self.quality_combo = NoWheelComboBox()
        self.quality_combo.addItems(["144p (Sangat Hemat Kuota & Ringan)", "240p", "Auto"])
        g2_l.addWidget(self.quality_combo)
        cfg_layout.addWidget(g2)

        # Group 3: Durasi & Retensi Nonton
        g3 = QGroupBox("Durasi Nonton & Retensi")
        g3.setStyleSheet("QGroupBox { font-weight: bold; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; margin-top: 10px; padding-top: 12px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }")
        g3_l = QVBoxLayout(g3)
        g3_l.setSpacing(8)

        self.auto_retention_cb = QCheckBox("Otomatis Ikuti Panjang Asli Video (85%–98%)")
        self.auto_retention_cb.setChecked(True)
        g3_l.addWidget(self.auto_retention_cb)

        fallback_l = QHBoxLayout()
        fallback_l.addWidget(QLabel("Min (dtk):"))
        self.min_sec_spin = NoWheelSpinBox()
        self.min_sec_spin.setRange(30, 1800)
        self.min_sec_spin.setValue(90)
        fallback_l.addWidget(self.min_sec_spin)

        fallback_l.addWidget(QLabel("Maks (dtk):"))
        self.max_sec_spin = NoWheelSpinBox()
        self.max_sec_spin.setRange(45, 3600)
        self.max_sec_spin.setValue(240)
        fallback_l.addWidget(self.max_sec_spin)
        g3_l.addLayout(fallback_l)
        cfg_layout.addWidget(g3)

        cfg_layout.addStretch()
        config_scroll.setWidget(cfg_widget)
        layout.addWidget(config_scroll)

        # Right Column: Live Worker Cards Grid
        right_panel = QVBoxLayout()
        cards_header = QHBoxLayout()
        c_title = QLabel("Status Real-Time Batch Worker")
        c_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        cards_header.addWidget(c_title)
        cards_header.addStretch()
        right_panel.addLayout(cards_header)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setStyleSheet("QScrollArea { border: 1px solid #1f2937; border-radius: 8px; background-color: #0b0f19; }")

        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(12, 12, 12, 12)
        self.cards_grid.setSpacing(12)
        self.cards_scroll.setWidget(self.cards_container)
        right_panel.addWidget(self.cards_scroll)

        layout.addLayout(right_panel, stretch=1)
        self.rebuild_worker_cards()

    def rebuild_worker_cards(self):
        # Clear existing cards
        for i in reversed(range(self.cards_grid.count())):
            w = self.cards_grid.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.worker_cards.clear()

        concurrency = max(1, self.concurrency_spin.value())
        cols = 2 if concurrency > 1 else 1

        for w_id in range(1, concurrency + 1):
            card = WorkerCardWidget(w_id)
            self.worker_cards[w_id] = card
            row = (w_id - 1) // cols
            col = (w_id - 1) % cols
            self.cards_grid.addWidget(card, row, col)

    def init_proxy_tab(self):
        layout = QVBoxLayout(self.tab_proxies)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Top Bar in Proxy Tab
        top_bar = QHBoxLayout()
        self.test_proxies_btn = QPushButton("🔍 Uji Semua Proksi ke YouTube")
        self.test_proxies_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.test_proxies_btn.clicked.connect(self.test_all_proxies)

        self.reload_proxies_btn = QPushButton("🔄 Muat Ulang File")
        self.reload_proxies_btn.setStyleSheet("background-color: #334155;")
        self.reload_proxies_btn.clicked.connect(self.load_proxy_table)

        top_bar.addWidget(self.test_proxies_btn)
        top_bar.addWidget(self.reload_proxies_btn)
        top_bar.addStretch()

        self.proxy_status_lbl = QLabel("Total: 0 proksi terdaftar")
        self.proxy_status_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        top_bar.addWidget(self.proxy_status_lbl)
        layout.addLayout(top_bar)

        # Proxy Table: Lengkap dengan Exit IP Publik & Status Penggunaan Worker
        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(7)
        self.proxy_table.setHorizontalHeaderLabels([
            "No", "Host : Port Gateway", "Exit IP Publik", "Negara", "Status YouTube", "Latency", "Dipakai Oleh"
        ])
        self.proxy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.proxy_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.proxy_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.proxy_table.setStyleSheet("""
            QTableWidget {
                background-color: #0b0f19;
                border: 1px solid #1f2937;
                gridline-color: #1e293b;
                color: #f1f5f9;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #111827;
                color: #94a3b8;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #1f2937;
            }
        """)
        layout.addWidget(self.proxy_table)

    def init_logs_tab(self):
        layout = QVBoxLayout(self.tab_logs)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Tools
        tb = QHBoxLayout()
        self.autoscroll_cb = QCheckBox("Auto-Scroll ke bawah")
        self.autoscroll_cb.setChecked(True)
        clear_btn = QPushButton("Bersihkan Log")
        clear_btn.setStyleSheet("background-color: #334155; padding: 6px 14px;")
        clear_btn.clicked.connect(self.clear_logs)

        tb.addWidget(self.autoscroll_cb)
        tb.addStretch()
        tb.addWidget(clear_btn)
        layout.addLayout(tb)

        # Log Output
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #050811;
                border: 1px solid #1f2937;
                border-radius: 8px;
                color: #e2e8f0;
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
                font-size: 11px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.log_text)

    def append_log(self, text: str, color: str = "#e2e8f0"):
        timestamp = time.strftime("%H:%M:%S")
        html_msg = f"<span style='color: #64748b;'>[{timestamp}]</span> <span style='color: {color};'>{text}</span>"
        self.log_text.append(html_msg)
        if self.autoscroll_cb.isChecked():
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)

    def clear_logs(self):
        self.log_text.clear()

    def load_saved_config(self):
        cfg = load_config()
        self.search_input.setText(cfg.get("search_keyword", "horrornologi"))
        self.channel_input.setText(cfg.get("target_channel", "horrornologi"))
        self.concurrency_spin.setValue(cfg.get("concurrency", 5))
        self.headless_cb.setChecked(cfg.get("headless", False))
        w_dur = cfg.get("watch_duration", {})
        self.min_sec_spin.setValue(w_dur.get("min_seconds", 90))
        self.max_sec_spin.setValue(w_dur.get("max_seconds", 240))

    def load_proxy_table(self):
        proxies = load_proxies(str(PROXIES_PATH))
        self.proxy_table.setRowCount(len(proxies))
        self.kpi_proxies.val_label.setText(str(len(proxies)))
        self.proxy_status_lbl.setText(f"Total: {len(proxies)} proksi aktif")

        for idx, p in enumerate(proxies):
            host = p.get("host", "")
            port = p.get("port", "")
            geo = p.get("country", "Global")
            flag_c = get_country_badge(geo)
            exit_ip = p.get("exit_ip", "-")

            item_no = QTableWidgetItem(str(idx + 1))
            item_host = QTableWidgetItem(f"{host}:{port}")
            item_exit = QTableWidgetItem(exit_ip)
            item_exit.setForeground(QColor("#38bdf8"))
            item_geo = QTableWidgetItem(flag_c)
            item_status = QTableWidgetItem("Belum Diuji")
            item_status.setForeground(QColor("#94a3b8"))
            item_lat = QTableWidgetItem("-")
            item_worker = QTableWidgetItem("-")
            item_worker.setForeground(QColor("#94a3b8"))

            self.proxy_table.setItem(idx, 0, item_no)
            self.proxy_table.setItem(idx, 1, item_host)
            self.proxy_table.setItem(idx, 2, item_exit)
            self.proxy_table.setItem(idx, 3, item_geo)
            self.proxy_table.setItem(idx, 4, item_status)
            self.proxy_table.setItem(idx, 5, item_lat)
            self.proxy_table.setItem(idx, 6, item_worker)

    def test_all_proxies(self):
        proxies = load_proxies(str(PROXIES_PATH))
        if not proxies:
            QMessageBox.warning(self, "Peringatan", "File proxies.json kosong atau tidak ditemukan.")
            return

        self.test_proxies_btn.setEnabled(False)
        self.test_proxies_btn.setText("⏳ Menguji Proksi & Membaca Exit IP...")
        self.append_log(f"🔎 Memulai pengujian {len(proxies)} proksi ke server YouTube...", "#38bdf8")

        self.proxy_tester_thread = ProxyTesterThread(proxies)
        self.proxy_tester_thread.proxy_result_signal.connect(self.on_proxy_test_result)
        self.proxy_tester_thread.finished_signal.connect(self.on_proxy_test_finished)
        self.proxy_tester_thread.start()

    def on_proxy_test_result(self, row: int, is_ok: bool, msg: str, lat: int, exit_ip: str):
        if row < self.proxy_table.rowCount():
            item_status = QTableWidgetItem("🟢 Lolos (200 OK)" if is_ok else f"🔴 Gagal ({msg[:25]})")
            item_status.setForeground(QColor("#10b981" if is_ok else "#ef4444"))
            item_lat = QTableWidgetItem(f"{lat} ms" if is_ok else "-")

            if exit_ip:
                item_exit = QTableWidgetItem(exit_ip)
                item_exit.setForeground(QColor("#10b981"))
                item_exit.setFont(QFont("Monospace", 9, QFont.Bold))
                self.proxy_table.setItem(row, 2, item_exit)

            self.proxy_table.setItem(row, 4, item_status)
            self.proxy_table.setItem(row, 5, item_lat)

    def on_proxy_test_finished(self, total_ok: int, total_tested: int):
        self.test_proxies_btn.setEnabled(True)
        self.test_proxies_btn.setText("🔍 Uji Semua Proksi ke YouTube")
        self.append_log(f"✅ Pengujian selesai: {total_ok}/{total_tested} proksi responsif terhadap YouTube.", "#10b981")
        self.kpi_proxies.val_label.setText(str(total_ok))
        QMessageBox.information(self, "Hasil Uji Proksi", f"Pengujian selesai!\n{total_ok} dari {total_tested} proksi berfungsi lancar.")

    def start_bot(self):
        concurrency = self.concurrency_spin.value()
        # Pastikan jumlah kartu monitor worker ter-generate lengkap
        self.rebuild_worker_cards()

        cfg = {
            "search_keyword": self.search_input.text().strip() or "horrornologi",
            "target_channel": self.channel_input.text().strip() or "horrornologi",
            "concurrency": concurrency,
            "headless": self.headless_cb.isChecked(),
            "use_proxy": self.proxy_cb.isChecked(),
            "proxy_source": str(PROXIES_PATH),
            "watch_duration": {
                "min_seconds": self.min_sec_spin.value(),
                "max_seconds": self.max_sec_spin.value()
            },
            "resolution": "144p"
        }

        # Simpan config ke disk
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_footer_lbl.setText("Status: Bot YouTube Sedang Berjalan (Multi-Worker)")
        self.status_footer_lbl.setStyleSheet("color: #10b981; font-weight: bold;")

        self.bot_thread = YouTubeBotThread(cfg)
        self.bot_thread.log_signal.connect(self.append_log)
        self.bot_thread.worker_event_signal.connect(self.on_worker_event)
        self.bot_thread.finished_signal.connect(self.on_bot_finished)
        self.bot_thread.start()

    def stop_bot(self):
        if self.bot_thread:
            self.stop_btn.setEnabled(False)
            self.status_footer_lbl.setText("Status: Menghentikan seluruh worker...")
            self.append_log("🛑 Permintaan berhenti diterima, menunggu worker menyelesaikan sesi terakhir...", "#f59e0b")
            self.bot_thread.stop()

    def on_bot_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_footer_lbl.setText("Status: Bot Berhenti")
        self.status_footer_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")

    def on_worker_event(self, event_type: str, data: dict):
        w_id = data.get("worker_id", 1)
        p_idx = data.get("proxy_idx", -1)

        # Pastikan card ada (jika belum ada, buat dinamis)
        card = self.worker_cards.get(w_id)
        if not card:
            card = WorkerCardWidget(w_id)
            self.worker_cards[w_id] = card
            row = (w_id - 1) // 2
            col = (w_id - 1) % 2
            self.cards_grid.addWidget(card, row, col)

        if event_type == "status_update":
            status = data.get("status", "")
            card.set_status(status, color="#38bdf8", bg="#1e293b")

        elif event_type == "proxy_testing":
            host = data.get("host", "")
            port = data.get("port", "")
            country = data.get("country", "")
            card.set_testing_proxy(host, port, country)
            card.set_status("Menguji Proksi", color="#f59e0b", bg="#78350f")

            # Update status di tabel proksi secara real-time!
            if 0 <= p_idx < self.proxy_table.rowCount():
                it_st = QTableWidgetItem(f"🟡 Menguji (Worker #{w_id})...")
                it_st.setForeground(QColor("#f59e0b"))
                self.proxy_table.setItem(p_idx, 4, it_st)
                it_w = QTableWidgetItem(f"Worker #{w_id} (Testing)")
                it_w.setForeground(QColor("#f59e0b"))
                self.proxy_table.setItem(p_idx, 6, it_w)

        elif event_type == "proxy_assigned":
            host = data.get("host", "")
            port = data.get("port", "")
            country = data.get("country", "")
            lat = data.get("latency", 0)
            exit_ip = data.get("exit_ip", "")

            # Update kartu worker: Exit IP Publik & Bendera Negara
            card.set_proxy(host, port, country, lat, exit_ip=exit_ip)
            card.set_status("Proksi Aktif", color="#10b981", bg="#064e3b")

            # Update baris di tabel proksi: Lolos dan Dipakai Worker
            if 0 <= p_idx < self.proxy_table.rowCount():
                if exit_ip:
                    it_exit = QTableWidgetItem(exit_ip)
                    it_exit.setForeground(QColor("#10b981"))
                    it_exit.setFont(QFont("Monospace", 9, QFont.Bold))
                    self.proxy_table.setItem(p_idx, 2, it_exit)

                it_st = QTableWidgetItem("🟢 Lolos (200 OK)")
                it_st.setForeground(QColor("#10b981"))
                self.proxy_table.setItem(p_idx, 4, it_st)

                it_lat = QTableWidgetItem(f"{lat} ms")
                self.proxy_table.setItem(p_idx, 5, it_lat)

                it_w = QTableWidgetItem(f"Worker #{w_id} ⚡ (Aktif)")
                it_w.setForeground(QColor("#10b981"))
                it_w.setFont(QFont("sans-serif", 9, QFont.Bold))
                self.proxy_table.setItem(p_idx, 6, it_w)

        elif event_type == "proxy_failed":
            if 0 <= p_idx < self.proxy_table.rowCount():
                it_st = QTableWidgetItem("🔴 Gagal / Timeout")
                it_st.setForeground(QColor("#ef4444"))
                self.proxy_table.setItem(p_idx, 4, it_st)
                it_w = QTableWidgetItem("Dibuang (Mati)")
                it_w.setForeground(QColor("#64748b"))
                self.proxy_table.setItem(p_idx, 6, it_w)

        elif event_type == "video_picked":
            title = data.get("title", "")
            card.set_video(title)
            card.set_status("Menonton", color="#f87171", bg="#450a0a")

        elif event_type == "playback_progress":
            pct = data.get("percent", 0.0)
            cur_s = data.get("formatted_current", "00:00")
            tgt_s = data.get("formatted_target", "00:00")
            card.update_progress(pct, cur_s, tgt_s)

        elif event_type == "ad_event":
            status = data.get("status", "")
            action = data.get("action", "clean")
            card.set_ad_status(status, action)
            if action == "skipped":
                self.stat_ads_skipped += 1
                self.kpi_ads.val_label.setText(str(self.stat_ads_skipped))

        elif event_type == "session_finished":
            success = data.get("success", False)
            if success:
                self.stat_views_completed += 1
                self.kpi_views.val_label.setText(str(self.stat_views_completed))
                card.set_status("Selesai (View Valid)", color="#10b981", bg="#064e3b")
            else:
                card.set_status("Selesai", color="#94a3b8", bg="#1f2937")

            if 0 <= p_idx < self.proxy_table.rowCount():
                it_w = QTableWidgetItem(f"Worker #{w_id} (✅ Selesai)")
                it_w.setForeground(QColor("#94a3b8"))
                self.proxy_table.setItem(p_idx, 6, it_w)

    def closeEvent(self, event):
        if self.bot_thread and self.bot_thread.isRunning():
            self.bot_thread.stop()
            self.bot_thread.wait(2000)
        if self.proxy_tester_thread and self.proxy_tester_thread.isRunning():
            self.proxy_tester_thread.cancel()
            self.proxy_tester_thread.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = YouTubeSuiteWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
