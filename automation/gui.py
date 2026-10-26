#!/usr/bin/env python3
"""Unified modern native desktop GUI for Bot Shortlink (Adsterra & Monetag).

Built with PySide6 (Qt). Mendukung pemilahan target iklan:
1. 💎 Hanya Monetag: Memaksa web memunculkan iklan MultiTag & Direct Link Monetag.
2. ⚡ Hanya Adsterra: Memaksa web memunculkan iklan Popunder, Social Bar & Smartlink Adsterra.
3. 🔄 Keduanya (Rotasi 50:50): Web memunculkan iklan Monetag & Adsterra secara seimbang bergantian.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from automation.adsterra.flow_qa import flow_worker_thread_loop
from automation.adsterra.qa import SessionBudget, country_label, load_config
from automation.monetag.flow import monetag_worker_thread_loop
from automation.exoclick.flow import exoclick_worker_thread_loop
from core.proxy_manager import ProxyManager


STYLE = """
QMainWindow, QWidget {
    background-color: #1e2128;
    color: #d7dae0;
    font-family: "Segoe UI", "Ubuntu", "Helvetica Neue", sans-serif;
    font-size: 13px;
}
QLabel#title {
    color: #38d6d6;
    font-size: 20px;
    font-weight: 700;
}
QLabel#subtitle { color: #8b93a1; font-size: 12px; }
QLabel#metricValue { color: #ffffff; font-size: 15px; font-weight: 600; }
QLabel#passVal { color: #3ddc84; font-size: 15px; font-weight: 700; }
QLabel#warnVal { color: #ffcc33; font-size: 15px; font-weight: 700; }
QLabel#failVal { color: #ff5c5c; font-size: 15px; font-weight: 700; }
QFrame#card {
    background-color: #262b34;
    border: 1px solid #333a45;
    border-radius: 10px;
}
QPushButton {
    background-color: #2f7df6;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton:hover { background-color: #4a90ff; }
QPushButton:disabled { background-color: #3a3f48; color: #6b7280; }
QPushButton#stopBtn { background-color: #e0475b; }
QPushButton#stopBtn:hover { background-color: #f25c6e; }
QSpinBox, QLineEdit {
    background-color: #1b1f26;
    border: 1px solid #333a45;
    border-radius: 6px;
    padding: 5px 8px;
    color: #e6e9ef;
    selection-background-color: #2f7df6;
}
QSpinBox:focus, QLineEdit:focus { border: 1px solid #2f7df6; }
QComboBox {
    background-color: #1b1f26;
    border: 1px solid #333a45;
    border-radius: 6px;
    padding: 5px 8px;
    color: #e6e9ef;
    min-width: 175px;
}
QComboBox:focus { border: 1px solid #2f7df6; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #262b34;
    border: 1px solid #333a45;
    color: #d7dae0;
    selection-background-color: #2f7df6;
}
QCheckBox { color: #d7dae0; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #454d5a;
    background-color: #1b1f26;
}
QCheckBox::indicator:checked { background-color: #2f7df6; border-color: #2f7df6; }
QTableWidget {
    background-color: #262b34;
    border: none;
    border-radius: 8px;
    gridline-color: #333a45;
    alternate-background-color: #2b313b;
}
QTableWidget::item { padding: 6px 8px; border: none; }
QHeaderView::section {
    background-color: #1b1f26;
    color: #8b93a1;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #2f7df6;
    font-weight: 600;
}
QProgressBar {
    background-color: #1b1f26;
    border: none;
    border-radius: 6px;
    height: 16px;
    text-align: center;
    color: #d7dae0;
    font-weight: 600;
}
QProgressBar::chunk { background-color: #38d6d6; border-radius: 6px; }
QTabWidget::pane {
    border: 1px solid #333a45;
    background-color: #262b34;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background-color: #1b1f26;
    color: #8b93a1;
    border: 1px solid #333a45;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 22px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #262b34;
    color: #38d6d6;
    border-color: #38d6d6;
    border-bottom: 2px solid #262b34;
}
QTabBar::tab:hover:!selected {
    background-color: #222730;
    color: #d7dae0;
}
QPlainTextEdit {
    background-color: #16191f;
    color: #b8c0cc;
    border: 1px solid #333a45;
    border-radius: 8px;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
}
QStatusBar { background-color: #1a1d23; color: #8b93a1; }
"""

STATUS_COLORS = {
    "bold green": "#3ddc84",
    "green": "#3ddc84",
    "bold yellow": "#ffcc33",
    "yellow": "#ffcc33",
    "bold red": "#ff5c5c",
    "red": "#ff5c5c",
    "cyan": "#38d6d6",
    "bold cyan": "#38d6d6",
    "magenta": "#c77dff",
    "dim": "#6b7280",
    "white": "#d7dae0",
    "blue": "#5aa9ff",
}


class EventBridge(QObject):
    event = Signal(str, dict)
    finished = Signal()


class RunController(QObject):
    """Mengelola thread worker, rotasi proxy, dan budget untuk Adsterra atau Monetag."""

    def __init__(self, bridge: EventBridge):
        super().__init__()
        self.bridge = bridge
        self.stop_event = threading.Event()
        self.threads: List[threading.Thread] = []
        self.budget: Optional[SessionBudget] = None
        self.proxy_manager: Optional[ProxyManager] = None
        self.dynamic_proxy_mode = False
        self._orchestration: Optional[threading.Thread] = None
        self._opened: set = set()
        self.running = False
        self.started_at = time.time()

    def emit(self, etype: str, data: Dict[str, Any]) -> None:
        self.bridge.event.emit(etype, data)

    def start(self, config: Dict[str, Any]) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.started_at = time.time()
        self.threads = []
        self._opened = set()
        self._orchestration = threading.Thread(
            target=self._run, args=(config,), daemon=True, name="AdControllerOrchestrator"
        )
        self._orchestration.start()

    def _run(self, config: Dict[str, Any]) -> None:
        hard_max = int(config.get("max_sessions_per_run", 10))
        self.dynamic_proxy_mode = bool(config.get("dynamic_proxy_mode", False))
        network_choice = str(config.get("target_network", "both")).lower()

        self.proxy_manager = ProxyManager()
        self.proxy_manager.reset_usage_to_idle()
        self.proxy_manager.reset_cursor(0)
        self.budget = SessionBudget(hard_max, 1)

        num_workers = int(config.get("concurrency", 3))
        stats = self.proxy_manager.get_stats()
        mode_lbl = "Tanpa Batas (∞)" if self.budget.unlimited else str(hard_max)

        network_label = {
            "monetag": "💎 Hanya Monetag",
            "adsterra": "⚡ Hanya Adsterra",
            "exoclick": "🎯 Hanya ExoClick",
            "all": "🔄 Semua Jaringan (Rotasi 3 Network)",
            "both": "🔄 Keduanya (Rotasi 50:50)",
        }.get(network_choice, "🔄 Semua Jaringan")

        self.emit("log_message", {
            "message": (
                f"Menyiapkan {num_workers} browser [{network_label}]. Mode: {mode_lbl}. "
                f"Stok IP aktif: {stats.get('alive', 0)}."
            ),
            "style": "cyan",
        })

        if stats.get("total", 0) == 0:
            self.emit("log_message", {
                "message": "Tidak ada IP (proxy) di pool. Tambahkan proxy dulu.",
                "style": "red",
            })
            self.running = False
            self.bridge.finished.emit()
            return

        pool_lock = threading.Lock()

        def _reset_pool() -> None:
            with pool_lock:
                self.proxy_manager.reset_usage_to_idle()
                self.proxy_manager.reset_cursor(0)
                # Reset hit target (kembali 0/2) agar mode unlimited berputar looping tanpa henti
                target = network_choice if network_choice in ("monetag", "adsterra", "exoclick") else None
                reset_hits = self.proxy_manager.reset_target_usage(target)
                self.budget.reset_proxy_counts()
                self.emit("log_message", {
                    "message": f"♻️ Mode Tanpa Batas: Pool proxy direset kembali ke 0/2 ({reset_hits} IP) untuk rotasi tanpa henti.",
                    "style": "cyan",
                })

        for wid in range(1, num_workers + 1):
            if self.stop_event.is_set():
                break

            # Tentukan worker loop: monetag, adsterra, exoclick, atau rotasi seimbang
            if network_choice == "monetag":
                worker_fn = monetag_worker_thread_loop
                worker_tag = "Monetag"
                target_label = "💎 Monetag"
                target_style = "magenta"
            elif network_choice == "adsterra":
                worker_fn = flow_worker_thread_loop
                worker_tag = "Adsterra"
                target_label = "⚡ Adsterra"
                target_style = "bold yellow"
            elif network_choice == "exoclick":
                worker_fn = exoclick_worker_thread_loop
                worker_tag = "ExoClick"
                target_label = "🎯 ExoClick"
                target_style = "bold cyan"
            else:
                r_idx = wid % 3
                if r_idx == 1:
                    worker_fn = monetag_worker_thread_loop
                    worker_tag = "Monetag"
                    target_label = "💎 Monetag"
                    target_style = "magenta"
                elif r_idx == 2:
                    worker_fn = flow_worker_thread_loop
                    worker_tag = "Adsterra"
                    target_label = "⚡ Adsterra"
                    target_style = "bold yellow"
                else:
                    worker_fn = exoclick_worker_thread_loop
                    worker_tag = "ExoClick"
                    target_label = "🎯 ExoClick"
                    target_style = "bold cyan"

            self.emit("worker_init", {
                "worker_id": wid,
                "target_network": target_label,
                "target_network_style": target_style,
            })

            thread = threading.Thread(
                target=worker_fn,
                args=(
                    wid, config, self.proxy_manager, self.budget,
                    self._worker_event, self.stop_event,
                ),
                kwargs={"reset_pool_callback": _reset_pool if self.budget.unlimited else None},
                daemon=True,
                name=f"{worker_tag}-Worker-{wid}",
            )
            thread.start()
            self.threads.append(thread)

            if wid < num_workers:
                time.sleep(1.8)

        while not self.stop_event.is_set():
            if all(not t.is_alive() for t in self.threads):
                break
            if self.budget and self.budget.is_exhausted():
                break
            time.sleep(0.5)

        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=10.0)

        self.running = False
        self.bridge.finished.emit()

    def _worker_event(self, etype: str, data: Dict[str, Any]) -> None:
        wid = data.get("worker_id")
        if wid is not None and etype in (
            "proxy_assigned", "session_started", "ad_check", "scroll", "geo_report"
        ):
            self._opened.add(wid)
        self.bridge.event.emit(etype, data)

    def stop(self) -> None:
        self.stop_event.set()


class Dashboard(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bot Shortlink — Controller Dasbor Adsterra & Monetag")
        self.resize(1240, 810)
        self.workers_state: Dict[int, Dict[str, Any]] = {}
        self.concurrency = 3
        self._controller_lock = threading.Lock()

        self.bridge = EventBridge()
        self.bridge.event.connect(self._on_event)
        self.bridge.finished.connect(self._on_run_finished)
        self.controller: Optional[RunController] = None
        self._shared_pm = ProxyManager()

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _card(self, title: str = "") -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("subtitle")
            layout.addWidget(lbl)
        return frame, layout

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(14)

        # Header row
        header = QHBoxLayout()
        title_block = QVBoxLayout()
        t = QLabel("Bot Shortlink & Ad Controller (Adsterra, Monetag & ExoClick)")
        t.setObjectName("title")
        self.target_label = QLabel("alamat: —")
        self.target_label.setObjectName("subtitle")
        title_block.addWidget(t)
        title_block.addWidget(self.target_label)
        header.addLayout(title_block)
        header.addStretch(1)

        right_block = QVBoxLayout()
        right_block.setAlignment(Qt.AlignRight)
        self.uptime_label = QLabel("00:00:00")
        self.uptime_label.setObjectName("metricValue")
        self.uptime_label.setAlignment(Qt.AlignRight)
        self.proxy_pool_label = QLabel("Proxy: memuat...")
        self.proxy_pool_label.setObjectName("subtitle")
        self.proxy_pool_label.setAlignment(Qt.AlignRight)
        right_block.addWidget(self.uptime_label)
        right_block.addWidget(self.proxy_pool_label)
        header.addLayout(right_block)
        root.addLayout(header)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0 / 0 kunjungan")
        root.addWidget(self.progress)

        # Control Card
        ctrl_card, ctrl_layout = self._card("PENGATURAN TARGET IKLAN & POLA BROWSER")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        # Row 0: Network Choice, Flow Mode, Browser Count, Headless, Start / Stop
        grid.addWidget(QLabel("Iklan Web yang Muncul"), 0, 0)
        self.ad_network_combo = QComboBox()
        self.ad_network_combo.addItems([
            "💎 Hanya Monetag (MultiTag & Direct Link)",
            "⚡ Hanya Adsterra (Popunder & Smartlink)",
            "🎯 Hanya ExoClick (Popunder, Push, Banner, Native)",
            "🔄 Semua Jaringan (Rotasi 3 Network)",
        ])
        self.ad_network_combo.setToolTip(
            "Pilih jaringan iklan yang akan dimunculkan di website:\n"
            "💎 Hanya Monetag: Website dipaksa HANYA memunculkan iklan Monetag.\n"
            "⚡ Hanya Adsterra: Website dipaksa HANYA memunculkan iklan Adsterra.\n"
            "🎯 Hanya ExoClick: Website dipaksa HANYA memunculkan iklan ExoClick.\n"
            "🔄 Semua Jaringan: Web bergantian memunculkan Monetag, Adsterra & ExoClick."
        )
        self.ad_network_combo.currentIndexChanged.connect(self._on_settings_changed)
        grid.addWidget(self.ad_network_combo, 0, 1)

        grid.addWidget(QLabel("Alur Kerja Bot"), 0, 2)
        self.flow_mode_combo = QComboBox()
        self.flow_mode_combo.addItems([
            "⚡ Fast Ads Dwell (Cepat & Langsung Dwell Iklan ~15s)",
            "🔗 Shortlink 3-Langkah (Countdown Timer ~70s)",
        ])
        self.flow_mode_combo.setToolTip(
            "⚡ Fast Ads Dwell: Membuka artikel langsung, dwell banner/popunder/smartlink tanpa tunggu step.\n"
            "🔗 Shortlink: Mengikuti 3 langkah verifikasi gate shortlink."
        )
        self.flow_mode_combo.currentIndexChanged.connect(self._on_settings_changed)
        grid.addWidget(self.flow_mode_combo, 0, 3)

        grid.addWidget(QLabel("Jumlah Browser"), 0, 4)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 30)
        init_cfg = load_config()
        self.workers_spin.setValue(int(init_cfg.get("concurrency", 3)))
        self.workers_spin.setToolTip("Berapa browser dibuka bersamaan. Tiap browser memakai proxy residensial sendiri.")
        grid.addWidget(self.workers_spin, 0, 5)

        self.start_btn = QPushButton("▶  Mulai")
        self.start_btn.clicked.connect(self._start_run)
        self.stop_btn = QPushButton("■  Berhenti")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_run)
        grid.addWidget(self.start_btn, 0, 6, 2, 1)
        grid.addWidget(self.stop_btn, 0, 7, 2, 1)

        # Row 1: Visit Mode, Cooldown, Custom Sessions, Headless Checkbox
        grid.addWidget(QLabel("Mode Kunjungan"), 1, 0)
        self.visit_mode_combo = QComboBox()
        self.visit_mode_combo.addItems([
            "Sesuai Jumlah Proxy (Dinamis)",
            "Tanpa Batas",
            "Custom",
        ])
        self.visit_mode_combo.currentIndexChanged.connect(self._on_visit_mode_changed)
        grid.addWidget(self.visit_mode_combo, 1, 1)

        grid.addWidget(QLabel("Jeda Cooldown IP"), 1, 2)
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 24)
        self.cooldown_spin.setValue(6)
        self.cooldown_spin.setSuffix(" Jam")
        grid.addWidget(self.cooldown_spin, 1, 3)

        self.sessions_spin = QSpinBox()
        self.sessions_spin.setRange(1, 9999)
        self.sessions_spin.setValue(10)
        self.sessions_spin.setVisible(False)
        grid.addWidget(self.sessions_spin, 1, 4)

        self.headless_check = QCheckBox("Headless (Sembunyikan browser)")
        self.headless_check.setChecked(bool(init_cfg.get("headless", False)))
        grid.addWidget(self.headless_check, 1, 5)

        # Row 2: Target URL, Direct Link Ratio & Max Uses per Day
        grid.addWidget(QLabel("URL Target"), 2, 0)
        self.target_url_input = QLineEdit()
        self.target_url_input.setText(str(init_cfg.get("target_url") or "https://article.riztama.my.id/"))
        self.target_url_input.textChanged.connect(self._on_url_input_changed)
        grid.addWidget(self.target_url_input, 2, 1)

        grid.addWidget(QLabel("Rasio Direct Link"), 2, 2)
        self.direct_chance_spin = QSpinBox()
        self.direct_chance_spin.setRange(10, 100)
        self.direct_chance_spin.setValue(50)
        self.direct_chance_spin.setSingleStep(5)
        self.direct_chance_spin.setSuffix(" % (Aman)")
        self.direct_chance_spin.setToolTip(
            "Persentase sesi yang membuka Direct Link Monetag / Smartlink Adsterra.\n"
            "Disarankan 40% - 60% agar CTR tampak alami dan aman bagi akun ad network."
        )
        grid.addWidget(self.direct_chance_spin, 2, 3)

        grid.addWidget(QLabel("Maks IP/Hari"), 2, 4)
        self.max_uses_spin = QSpinBox()
        self.max_uses_spin.setRange(1, 5)
        self.max_uses_spin.setValue(2)
        grid.addWidget(self.max_uses_spin, 2, 5)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(5, 0)
        ctrl_layout.addLayout(grid)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("subtitle")
        self.hint_label.setWordWrap(True)
        ctrl_layout.addWidget(self.hint_label)
        root.addWidget(ctrl_card)

        # Tabs Container
        self.tabs = QTabWidget()

        # ── TAB 1: DASHBOARD & STEPPER FLOW ──
        tab_dashboard = QWidget()
        dash_layout = QVBoxLayout(tab_dashboard)
        dash_layout.setContentsMargins(6, 8, 6, 6)
        dash_layout.setSpacing(10)

        # Worker table card
        table_card, table_layout = self._card("DAFTAR BROWSER & PEMANTAU STEPPER FLOW REALTIME")

        # Stepper Pipeline Guide Banner
        pipeline_frame = QFrame()
        pipeline_frame.setStyleSheet("background-color: #1b1f26; border-radius: 6px; padding: 4px 8px;")
        self.pipeline_box = QHBoxLayout(pipeline_frame)
        self.pipeline_box.setContentsMargins(6, 4, 6, 4)
        self.pipeline_box.setSpacing(8)
        self._update_pipeline_banner()
        table_layout.addWidget(pipeline_frame)

        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels([
            "No", "Target Iklan", "Negara", "IP Proxy", "Pemakaian IP", "Tahap Flow", "Aktivitas Terkini",
            "IP Keluar", "Bot?", "WebRTC", "Iklan", "Skor", "Status", "Selesai"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)

        column_widths = (
            (0, 42), (1, 105), (2, 95), (3, 130), (4, 115), (5, 140), (6, 230),
            (7, 125), (8, 60), (9, 65), (10, 55), (11, 50), (12, 85), (13, 60)
        )
        for col, width in column_widths:
            self.table.setColumnWidth(col, width)
        self.table.setMinimumHeight(240)
        table_layout.addWidget(self.table)
        dash_layout.addWidget(table_card, stretch=1)

        # Summary row
        sum_card, sum_layout = self._card()
        row = QHBoxLayout()
        row.setSpacing(28)
        self.pass_lbl = QLabel("Lolos  0"); self.pass_lbl.setObjectName("passVal")
        self.warn_lbl = QLabel("Waspada  0"); self.warn_lbl.setObjectName("warnVal")
        self.fail_lbl = QLabel("Gagal  0"); self.fail_lbl.setObjectName("failVal")
        self.total_lbl = QLabel("Total  0"); self.total_lbl.setObjectName("metricValue")
        for w in (self.total_lbl, self.pass_lbl, self.warn_lbl, self.fail_lbl):
            row.addWidget(w)
        row.addStretch(1)
        sum_layout.addLayout(row)
        dash_layout.addWidget(sum_card)
        self.tabs.addTab(tab_dashboard, "⚡ Dashboard & Stepper Flow")

        # ── TAB 2: POOL & STATUS PEMAKAIAN PROXY ──
        tab_proxy = QWidget()
        proxy_layout = QVBoxLayout(tab_proxy)
        proxy_layout.setContentsMargins(6, 8, 6, 6)
        proxy_layout.setSpacing(10)

        # Proxy Filter & Action Card
        pt_header_card, pt_header_layout = self._card("STATUS & KONTROL PEMAKAIAN PROXY (ADSTERRA & MONETAG)")
        pt_row = QHBoxLayout()
        pt_row.setSpacing(12)

        self.pt_summary_lbl = QLabel("Memuat ringkasan status proxy...")
        self.pt_summary_lbl.setStyleSheet("color: #38d6d6; font-weight: 600; font-size: 13px;")
        pt_row.addWidget(self.pt_summary_lbl)
        pt_row.addStretch(1)

        pt_row.addWidget(QLabel("Cari IP / Negara:"))
        self.proxy_search_input = QLineEdit()
        self.proxy_search_input.setPlaceholderText("Filter IP/Negara...")
        self.proxy_search_input.setFixedWidth(140)
        self.proxy_search_input.textChanged.connect(lambda _: self._refresh_proxy_tab_data(force=True))
        pt_row.addWidget(self.proxy_search_input)

        pt_row.addWidget(QLabel("Filter:"))
        self.proxy_filter_combo = QComboBox()
        self.proxy_filter_combo.addItems([
            "Semua Proxy",
            "🔵 Sedang Dipakai Worker",
            "🟡 Hit > 0 (Telah Digunakan)",
            "🟢 Fresh (0 Hit Belum Digunakan)",
            "⏳ Sedang Cooldown",
        ])
        self.proxy_filter_combo.currentIndexChanged.connect(lambda _: self._refresh_proxy_tab_data(force=True))
        pt_row.addWidget(self.proxy_filter_combo)

        self.btn_refresh_proxy = QPushButton("🔄 Segarkan")
        self.btn_refresh_proxy.clicked.connect(lambda: self._refresh_proxy_tab_data(force=True))
        pt_row.addWidget(self.btn_refresh_proxy)

        self.btn_reset_proxy_hits = QPushButton("♻️ Reset Semua Hit (0/2)")
        self.btn_reset_proxy_hits.setStyleSheet("background-color: #7952b3;")
        self.btn_reset_proxy_hits.setToolTip("Mereset pemakaian Adsterra, Monetag, dan ExoClick menjadi 0/2 untuk seluruh proxy.")
        self.btn_reset_proxy_hits.clicked.connect(self._on_manual_reset_hits)
        pt_row.addWidget(self.btn_reset_proxy_hits)
        pt_header_layout.addLayout(pt_row)
        proxy_layout.addWidget(pt_header_card)

        # Proxy Table Card
        proxy_table_card, proxy_table_layout = self._card()
        self.proxy_table = QTableWidget(0, 10)
        self.proxy_table.setHorizontalHeaderLabels([
            "No", "IP Proxy", "Negara", "Status Jaringan",
            "Hit Adsterra", "Hit Monetag", "Hit ExoClick", "Sedang Dipakai Worker", "Terakhir Digunakan", "Latency"
        ])
        self.proxy_table.setAlternatingRowColors(True)
        self.proxy_table.verticalHeader().setVisible(False)
        self.proxy_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.proxy_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.proxy_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.proxy_table.horizontalHeader().setStretchLastSection(True)

        pt_column_widths = (
            (0, 45), (1, 130), (2, 95), (3, 110),
            (4, 110), (5, 110), (6, 110), (7, 160), (8, 120), (9, 70)
        )
        for col, width in pt_column_widths:
            self.proxy_table.setColumnWidth(col, width)
        self.proxy_table.setMinimumHeight(240)
        proxy_table_layout.addWidget(self.proxy_table)
        proxy_layout.addWidget(proxy_table_card, stretch=1)

        self.tabs.addTab(tab_proxy, "🌐 Pool & Status Pemakaian Proxy")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        root.addWidget(self.tabs, stretch=1)

        # Log card (tetap di paling bawah)
        log_card, log_layout = self._card("LOG AKTIVITAS")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(130)
        log_layout.addWidget(self.log)
        root.addWidget(log_card)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Siap — pilih iklan target lalu tekan Mulai.")
        self._append_log("Aplikasi siap. Controller Adsterra, Monetag & ExoClick aktif.", "cyan")

    def _on_url_input_changed(self, text: str) -> None:
        self.target_label.setText(f"alamat: {text.strip() or '-'}")

    def _on_settings_changed(self) -> None:
        self._update_pipeline_banner()
        net_idx = self.ad_network_combo.currentIndex()
        net_names = ["Hanya Monetag", "Hanya Adsterra", "Hanya ExoClick", "Semua Jaringan (Rotasi 3 Network)"]
        self._append_log(f"Iklan target diatur: {net_names[net_idx]}", "cyan")

    def _update_pipeline_banner(self) -> None:
        if not hasattr(self, "pipeline_box"):
            return
        while self.pipeline_box.count():
            item = self.pipeline_box.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        net_idx = self.ad_network_combo.currentIndex() if hasattr(self, "ad_network_combo") else 0
        flow_idx = self.flow_mode_combo.currentIndex() if hasattr(self, "flow_mode_combo") else 0

        if net_idx == 0:  # Monetag
            steps_info = [
                ("1. 🛡️ Audit IP", "#38d6d6"),
                ("➔", "#6b7280"),
                ("2. 🌐 MultiTag Web", "#38d6d6"),
                ("➔", "#6b7280"),
                ("3. 📜 Natural Wander", "#5aa9ff"),
                ("➔", "#6b7280"),
                ("4. 📑 Dwell Popunder", "#c77dff"),
                ("➔", "#6b7280"),
                ("5. 🔗 Dwell Direct Link", "#ffcc33"),
                ("➔", "#6b7280"),
                ("6. ✅ Selesai", "#3ddc84"),
            ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText(
                    "💎 Target Monetag: Web otomatis memuat iklan MultiTag & Direct Link Monetag saja (bebas popunder Adsterra)."
                )
        elif net_idx == 1:  # Adsterra
            if flow_idx == 0:
                steps_info = [
                    ("1. 🛡️ Audit IP", "#38d6d6"),
                    ("➔", "#6b7280"),
                    ("2. 🌐 Buka Artikel", "#38d6d6"),
                    ("➔", "#6b7280"),
                    ("3. 📜 Baca Artikel", "#5aa9ff"),
                    ("➔", "#6b7280"),
                    ("4. 🎨 Dwell Iklan", "#ffcc33"),
                    ("➔", "#6b7280"),
                    ("5. 📑 Popunder / 🔗 Smartlink", "#c77dff"),
                    ("➔", "#6b7280"),
                    ("6. ✅ Selesai", "#3ddc84"),
                ]
            else:
                steps_info = [
                    ("1. 🛡️ Audit IP", "#38d6d6"),
                    ("➔", "#6b7280"),
                    ("2. 🌐 Buka Web", "#38d6d6"),
                    ("➔", "#6b7280"),
                    ("3. 1️⃣ Step 1", "#ffcc33"),
                    ("➔", "#6b7280"),
                    ("4. 2️⃣ Step 2", "#ffcc33"),
                    ("➔", "#6b7280"),
                    ("5. 3️⃣ Step 3", "#ffcc33"),
                    ("➔", "#6b7280"),
                    ("6. 📜 Jelajah Web", "#5aa9ff"),
                    ("➔", "#6b7280"),
                    ("7. 📑 Popunder / 🔗 Smartlink", "#c77dff"),
                    ("➔", "#6b7280"),
                    ("8. ✅ Selesai", "#3ddc84"),
                ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText(
                    "⚡ Target Adsterra: Web otomatis memuat Popunder, Social Bar & Smartlink Adsterra."
                )
        elif net_idx == 2:  # ExoClick
            steps_info = [
                ("1. 🛡️ Audit IP", "#38d6d6"),
                ("➔", "#6b7280"),
                ("2. 🌐 Buka Web", "#38d6d6"),
                ("➔", "#6b7280"),
                ("3. 💬 In-Page Push", "#ffcc33"),
                ("➔", "#6b7280"),
                ("4. 🖼️ Native Banner", "#c77dff"),
                ("➔", "#6b7280"),
                ("5. 📑 Dwell Popunder", "#ff5c5c"),
                ("➔", "#6b7280"),
                ("6. ✅ Selesai", "#3ddc84"),
            ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText(
                    "🎯 Target ExoClick: Web otomatis memuat Popunder, In-Page Push, Native Banner, & Display Banner ExoClick."
                )
        else:  # Semua Jaringan
            steps_info = [
                ("1. 🛡️ Audit IP", "#38d6d6"),
                ("➔", "#6b7280"),
                ("2. 🌐 Web Target (3 Net)", "#38d6d6"),
                ("➔", "#6b7280"),
                ("3. 📜 Interaksi Natural", "#5aa9ff"),
                ("➔", "#6b7280"),
                ("4. 📑 Dwell Popunder / Banner", "#c77dff"),
                ("➔", "#6b7280"),
                ("5. 🔗 Dwell Smartlink / Direct", "#ffcc33"),
                ("➔", "#6b7280"),
                ("6. ✅ Selesai", "#3ddc84"),
            ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText(
                    "🔄 Target Semua Jaringan: Browser bergantian memunculkan Monetag, Adsterra, & ExoClick secara otomatis."
                )

        for text, color in steps_info:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: {'700' if text != '➔' else '400'};")
            self.pipeline_box.addWidget(lbl)
        self.pipeline_box.addStretch(1)

    def _on_visit_mode_changed(self, idx: int) -> None:
        self.sessions_spin.setVisible(idx == 2)

    def _build_config(self) -> Dict[str, Any]:
        cfg = load_config()
        net_idx = self.ad_network_combo.currentIndex()
        flow_idx = self.flow_mode_combo.currentIndex()

        # Tentukan target network: 'monetag' | 'adsterra' | 'exoclick' | 'all'
        if net_idx == 0:
            target_net = "monetag"
        elif net_idx == 1:
            target_net = "adsterra"
        elif net_idx == 2:
            target_net = "exoclick"
        else:
            target_net = "all"

        cfg["target_network"] = target_net
        cfg["target_name"] = target_net if target_net in ("monetag", "adsterra", "exoclick") else "adsterra"
        cfg["traffic_mode"] = "direct_article" if flow_idx == 0 else "shortlink"
        cfg["direct_link_url"] = "https://uplcm.com/4/12124796"

        # Injeksi parameter URL ?ad_network=... agar website langsung memunculkan iklan yang dipilih!
        raw_url = self.target_url_input.text().strip() or "https://article.riztama.my.id/"
        parsed = urlparse(raw_url)
        qs = parse_qs(parsed.query)
        qs["ad_network"] = [target_net]
        new_query = urlencode(qs, doseq=True)
        final_target_url = urlunparse(parsed._replace(query=new_query))

        cfg["target_url"] = final_target_url
        cfg["concurrency"] = int(self.workers_spin.value())
        cfg["max_uses_per_day"] = int(self.max_uses_spin.value())
        cfg["proxy_cooldown_hours"] = float(self.cooldown_spin.value())
        cfg["direct_link_chance"] = float(self.direct_chance_spin.value()) / 100.0

        mode = self.visit_mode_combo.currentIndex()
        if mode == 0:
            pm = ProxyManager()
            stats = pm.get_stats()
            alive = stats.get("alive", 0) + stats.get("unknown", 0)
            cfg["max_sessions_per_run"] = max(1, alive)
            cfg["dynamic_proxy_mode"] = True
        elif mode == 1:
            cfg["max_sessions_per_run"] = 0
            cfg["dynamic_proxy_mode"] = False
        else:
            cfg["max_sessions_per_run"] = int(self.sessions_spin.value())
            cfg["dynamic_proxy_mode"] = False

        cfg["headless"] = bool(self.headless_check.isChecked())
        self.concurrency = cfg["concurrency"]
        self.target_label.setText(f"alamat: {final_target_url}")
        self._reset_state(cfg["concurrency"])
        return cfg

    def _reset_state(self, concurrency: int) -> None:
        self.workers_state = {}
        net_idx = self.ad_network_combo.currentIndex() if hasattr(self, "ad_network_combo") else 0
        for wid in range(1, concurrency + 1):
            if net_idx == 0:
                t_net, t_style = "💎 Monetag", "magenta"
            elif net_idx == 1:
                t_net, t_style = "⚡ Adsterra", "bold yellow"
            elif net_idx == 2:
                t_net, t_style = "🎯 ExoClick", "bold cyan"
            else:
                r_idx = wid % 3
                if r_idx == 1:
                    t_net, t_style = "💎 Monetag", "magenta"
                elif r_idx == 2:
                    t_net, t_style = "⚡ Adsterra", "bold yellow"
                else:
                    t_net, t_style = "🎯 ExoClick", "bold cyan"
            self.workers_state[wid] = {
                "target_net": t_net,
                "target_net_style": t_style,
                "proxy_ip": "—",
                "country": "—",
                "target_usage": "Hit 1/2 (Baru)",
                "target_usage_style": "dim",
                "stepper": "⚪ Menunggu",
                "stepper_style": "dim",
                "activity": "Menunggu giliran...",
                "activity_style": "dim",
                "out_ip": "—",
                "bot": "—", "bot_style": "dim",
                "webrtc": "—", "webrtc_style": "dim",
                "ads": "—", "ads_style": "dim",
                "vscore": "—", "vscore_style": "dim",
                "status": "Siap", "status_style": "dim",
                "sessions_done": 0,
            }
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.log.setPlainText("")
        self._append_log(f"Menyiapkan {concurrency} browser...", "cyan")
        self._refresh_table()
        self._refresh_proxy_tab_data(force=True)

    def _start_run(self) -> None:
        with self._controller_lock:
            if self.controller and self.controller.running:
                return
            cfg = self._build_config()
            self.controller = RunController(self.bridge)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self._set_controls_enabled(False)
            self.statusBar().showMessage("Sedang jalan...")
            self.controller.start(cfg)

    def _stop_run(self) -> None:
        if self.controller:
            self.controller.stop()
        self.statusBar().showMessage("Menghentikan...")
        self._append_log("Dihentikan — menunggu sesi yang sedang jalan selesai.", "red")

    def _on_run_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_controls_enabled(True)
        self.statusBar().showMessage("Selesai.")
        self._append_log("Semua sesi selesai.", "green")
        self._refresh_proxy_tab_data(force=True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in (
            self.ad_network_combo,
            self.flow_mode_combo,
            self.target_url_input,
            self.workers_spin,
            self.visit_mode_combo,
            self.sessions_spin,
            self.max_uses_spin,
            self.cooldown_spin,
            self.headless_check,
            self.direct_chance_spin,
        ):
            w.setEnabled(enabled)

    def _on_event(self, etype: str, data: Dict[str, Any]) -> None:
        wid = data.get("worker_id", 0)
        w = self.workers_state.get(wid)
        if etype == "log_message":
            self._append_log(data.get("message", ""), data.get("style", "white"))
            return
        if w is None:
            return

        if etype == "worker_init":
            t_net = data.get("target_network")
            if t_net:
                w["target_net"] = t_net
                w["target_net_style"] = data.get("target_network_style", "magenta" if "Monetag" in t_net else "bold yellow")
            self._refresh_table()
            return

        elif etype == "stepper_update":
            stage = data.get("stage", "")
            status = data.get("status", "")
            if stage:
                w["stepper"] = stage
                low = stage.lower()
                if "selesai" in low or "lolos" in low:
                    w["stepper_style"] = "bold green"
                elif "gagal" in low:
                    w["stepper_style"] = "bold red"
                elif "popunder" in low or "smartlink" in low or "direct link" in low:
                    w["stepper_style"] = "magenta"
                elif "multitag" in low or "wander" in low or "step" in low or "langkah" in low:
                    w["stepper_style"] = "bold yellow"
                elif "audit" in low:
                    w["stepper_style"] = "cyan"
                else:
                    w["stepper_style"] = "bold cyan"
            if status:
                w["activity"] = status
                w["activity_style"] = "white"

        elif etype == "status_update":
            status = data.get("status", "")
            w["activity"] = status
            low = status.lower()
            if "gagal" in low or "error" in low or "fail" in low:
                w["activity_style"] = "bold red"
            elif any(k in low for k in ("buka", "scroll", "klik", "loading", "flow", "dwell")):
                w["activity_style"] = "bold yellow"
            else:
                w["activity_style"] = "white"

        elif etype == "proxy_assigned":
            w["proxy_ip"] = data.get("ip", "—")
            w["country"] = country_label(data.get("country"))
            t_usage = data.get("target_usage")
            if t_usage:
                w["target_usage"] = t_usage
                hit_count = data.get("hit_count", 1)
                w["target_usage_style"] = "bold green" if hit_count <= 1 else "bold yellow"
            t_net = data.get("target_network")
            if t_net:
                w["target_net"] = t_net
                if "Monetag" in t_net:
                    w["target_net_style"] = "magenta"
                elif "ExoClick" in t_net:
                    w["target_net_style"] = "bold cyan"
                else:
                    w["target_net_style"] = "bold yellow"
            w["stepper"] = "🛡️ Alokasi IP"
            w["stepper_style"] = "cyan"
            w["activity"] = f"IP terpilih: {w['proxy_ip']}"
            w["activity_style"] = "cyan"
            if hasattr(self, "tabs") and self.tabs.currentIndex() == 1:
                self._refresh_proxy_tab_data()

        elif etype == "verifier_report":
            detected_country = country_label(data.get("detected_country"))
            if detected_country and detected_country != "Unknown":
                w["country"] = detected_country
            w["out_ip"] = data.get("detected_ip") or w["proxy_ip"]
            w["bot"] = "Bot!" if data.get("bot_detected") else "Aman"
            w["bot_style"] = "bold red" if data.get("bot_detected") else "bold green"
            w["webrtc"] = "Bocor" if data.get("webrtc_leak") else "Aman"
            w["webrtc_style"] = "bold red" if data.get("webrtc_leak") else "bold green"
            w["ads"] = "Blokir" if (data.get("adblock_detected") or not data.get("ads_allowed", True)) else "OK"
            w["ads_style"] = "bold red" if w["ads"] == "Blokir" else "bold green"
            score = data.get("score", 0)
            w["vscore"] = str(score)
            w["vscore_style"] = "bold green" if score >= 80 else ("bold yellow" if score >= 60 else "bold red")
            w["activity"] = f"Audit skor: {score}/100"

        elif etype == "session_started":
            w["stepper"] = "🌐 Buka Web"
            w["stepper_style"] = "bold yellow"
            w["activity"] = "Membuka halaman target..."

        elif etype == "session_completed":
            raw = data.get("status", "FAIL")
            label = {"PASS": "LOLOS", "WARN": "WASPADA", "FAIL": "GAGAL"}.get(raw, raw)
            w["status"] = label
            w["status_style"] = {
                "PASS": "bold green", "WARN": "bold yellow", "FAIL": "bold red"
            }.get(raw, "white")
            w["stepper"] = f"✅ {label}" if raw == "PASS" else f"❌ {label}"
            w["stepper_style"] = w["status_style"]
            w["activity"] = f"Selesai dengan status {label}"
            w["activity_style"] = "dim"
            w["sessions_done"] = w.get("sessions_done", 0) + 1

            # Catat statistik sesi lokal dan broadcast ke Supabase Realtime
            try:
                from core.telemetry_reporter import get_telemetry_reporter
                rep = get_telemetry_reporter()
                rep.record_session_result(
                    target=w.get("target_net", "auto"),
                    passed=(raw == "PASS"),
                    score=int(w.get("vscore") or 0),
                    bot_detected=(w.get("bot") == "Bot!"),
                    proxy_ip=w.get("proxy_ip", "—"),
                    country=w.get("country", "—"),
                )
            except Exception:
                pass

            if hasattr(self, "tabs") and self.tabs.currentIndex() == 1:
                self._refresh_proxy_tab_data()

        self._refresh_table()

    def _refresh_table(self) -> None:
        ids = sorted(self.workers_state.keys())
        if self.table.rowCount() != len(ids):
            self.table.setRowCount(len(ids))
        center_cols = (0, 1, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13)
        for r, wid in enumerate(ids):
            w = self.workers_state[wid]
            cells = [
                f"W{wid}",
                w.get("target_net", "—"),
                w.get("country", "—"),
                w.get("proxy_ip", "—"),
                w.get("target_usage", "Hit 1/2"),
                w.get("stepper", "⚪ Menunggu"),
                w.get("activity", "—"),
                w.get("out_ip", "—"),
                w.get("bot", "—"),
                w.get("webrtc", "—"),
                w.get("ads", "—"),
                w.get("vscore", "—"),
                w.get("status", "Siap"),
                str(w.get("sessions_done", 0)),
            ]
            color_keys = {
                1: w.get("target_net_style", "white"),
                4: w.get("target_usage_style", "dim"),
                5: w.get("stepper_style", "white"),
                6: w.get("activity_style", "dim"),
                8: w.get("bot_style", "dim"),
                9: w.get("webrtc_style", "dim"),
                10: w.get("ads_style", "dim"),
                11: w.get("vscore_style", "dim"),
                12: w.get("status_style", "dim"),
            }
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(
                    Qt.AlignVCenter | (Qt.AlignCenter if c in center_cols else Qt.AlignLeft)
                )
                if c in color_keys:
                    item.setForeground(QColor(STATUS_COLORS.get(color_keys[c], "#d7dae0")))
                self.table.setItem(r, c, item)

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 1:
            self._refresh_proxy_tab_data(force=True)

    def _on_manual_reset_hits(self) -> None:
        reset_count = self._shared_pm.reset_target_usage(None)
        self._shared_pm.reset_usage_to_idle()
        self._append_log(f"♻️ Seluruh hit proxy ({reset_count} IP) berhasil direset kembali ke 0/2.", "cyan")
        self._refresh_proxy_tab_data(force=True)

    def _refresh_proxy_tab_data(self, force: bool = False) -> None:
        if not hasattr(self, "proxy_table"):
            return
        if not force and hasattr(self, "tabs") and self.tabs.currentIndex() != 1:
            return

        now_ts = time.time()
        last_refresh = getattr(self, "_last_proxy_tab_refresh", 0.0)
        if not force and (now_ts - last_refresh) < 2.5:
            return
        self._last_proxy_tab_refresh = now_ts

        proxies = self._shared_pm.get_proxies()
        total_p = len(proxies)
        active_worker_ips: Dict[str, str] = {}
        for wid, w in self.workers_state.items():
            pip = w.get("proxy_ip")
            if pip and pip != "—":
                active_worker_ips[pip] = f"Worker {wid} ({w.get('target_net', '—')})"

        search_q = self.proxy_search_input.text().strip().lower() if hasattr(self, "proxy_search_input") else ""
        f_idx = self.proxy_filter_combo.currentIndex() if hasattr(self, "proxy_filter_combo") else 0

        filtered: List[Dict[str, Any]] = []
        fresh_count = 0
        used_count = 0
        in_use_count = 0
        cooldown_count = 0

        for p in proxies:
            ip = p.get("ip_detected") or p.get("host", "?")
            c_name = country_label(p.get("country"))
            health = p.get("health", "ALIVE")
            is_active = (ip in active_worker_ips) or (p.get("usage") == "IN_USE")

            tu = p.get("target_usage") or {}
            ad_hit = (tu.get("adsterra") or {}).get("count", 0)
            mn_hit = (tu.get("monetag") or {}).get("count", 0)
            exo_hit = (tu.get("exoclick") or {}).get("count", 0)

            if is_active:
                in_use_count += 1
            if health == "COOLDOWN":
                cooldown_count += 1
            if ad_hit == 0 and mn_hit == 0 and exo_hit == 0:
                fresh_count += 1
            if ad_hit > 0 or mn_hit > 0 or exo_hit > 0:
                used_count += 1

            if search_q and (search_q not in ip.lower() and search_q not in c_name.lower()):
                continue

            if f_idx == 1 and not is_active:
                continue
            elif f_idx == 2 and (ad_hit == 0 and mn_hit == 0 and exo_hit == 0):
                continue
            elif f_idx == 3 and (ad_hit > 0 or mn_hit > 0 or exo_hit > 0):
                continue
            elif f_idx == 4 and health != "COOLDOWN":
                continue

            filtered.append(p)

        if hasattr(self, "pt_summary_lbl"):
            self.pt_summary_lbl.setText(
                f"Total: {total_p} IP | 🟢 Fresh (0 Hit): {fresh_count} | 🟡 Terpakai: {used_count} | 🔵 Aktif: {in_use_count} | ⏳ Cooldown: {cooldown_count}"
            )

        display_list = filtered[:350]
        if self.proxy_table.rowCount() != len(display_list):
            self.proxy_table.setRowCount(len(display_list))
        center_cols = (0, 2, 3, 4, 5, 6, 7, 8, 9)

        for r, p in enumerate(display_list):
            ip = p.get("ip_detected") or p.get("host", "?")
            c_name = country_label(p.get("country"))
            health = p.get("health", "ALIVE")
            is_active = ip in active_worker_ips

            tu = p.get("target_usage") or {}
            ad_data = tu.get("adsterra") or {}
            ad_hit = ad_data.get("count", 0)
            mn_data = tu.get("monetag") or {}
            mn_hit = mn_data.get("count", 0)
            exo_data = tu.get("exoclick") or {}
            exo_hit = exo_data.get("count", 0)

            ad_str = f"{ad_hit}/2 (Fresh)" if ad_hit == 0 else (f"{ad_hit}/2 (Hit 1)" if ad_hit == 1 else f"{ad_hit}/2 (Limit)")
            mn_str = f"{mn_hit}/2 (Fresh)" if mn_hit == 0 else (f"{mn_hit}/2 (Hit 1)" if mn_hit == 1 else f"{mn_hit}/2 (Limit)")
            exo_str = f"{exo_hit}/2 (Fresh)" if exo_hit == 0 else (f"{exo_hit}/2 (Hit 1)" if exo_hit == 1 else f"{exo_hit}/2 (Limit)")

            if is_active:
                status_str = "🔵 IN USE"
                status_color = "#38d6d6"
            elif health == "ALIVE":
                status_str = "🟢 ALIVE"
                status_color = "#3ddc84"
            elif health == "COOLDOWN":
                status_str = "🟡 COOLDOWN"
                status_color = "#ffcc33"
            else:
                status_str = "🔴 DEAD"
                status_color = "#ff5c5c"

            w_str = active_worker_ips.get(ip, "- (Idle)")
            w_color = "#38d6d6" if is_active else "#6b7280"

            l_ad = ad_data.get("last_used") or 0
            l_mn = mn_data.get("last_used") or 0
            l_exo = exo_data.get("last_used") or 0
            latest = max(l_ad, l_mn, l_exo)
            if latest > 0:
                last_used_str = time.strftime("%H:%M:%S", time.localtime(latest))
            else:
                last_used_str = "Baru"

            lat = p.get("latency_ms", 0)
            lat_str = f"{lat:.0f} ms" if lat else "—"

            row_cells = [
                str(r + 1),
                ip,
                c_name,
                status_str,
                ad_str,
                mn_str,
                exo_str,
                w_str,
                last_used_str,
                lat_str,
            ]
            row_colors = {
                3: status_color,
                4: "#3ddc84" if ad_hit == 0 else ("#ffcc33" if ad_hit == 1 else "#ff5c5c"),
                5: "#3ddc84" if mn_hit == 0 else ("#ffcc33" if mn_hit == 1 else "#ff5c5c"),
                6: "#3ddc84" if exo_hit == 0 else ("#ffcc33" if exo_hit == 1 else "#ff5c5c"),
                7: w_color,
                8: "#d7dae0" if latest > 0 else "#6b7280",
            }
            for c, val in enumerate(row_cells):
                item = self.proxy_table.item(r, c)
                if not item:
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignCenter if c in center_cols else Qt.AlignLeft))
                    self.proxy_table.setItem(r, c, item)
                else:
                    if item.text() != val:
                        item.setText(val)
                if c in row_colors:
                    item.setForeground(QColor(row_colors[c]))

    def _append_log(self, message: str, style: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        color = STATUS_COLORS.get(style, "#b8c0cc")
        html = f'<span style="color:#6b7280">[{ts}]</span> <span style="color:{color}">{_esc(message)}</span>'
        self.log.appendHtml(html)

    def _tick(self) -> None:
        try:
            net_idx = self.ad_network_combo.currentIndex() if hasattr(self, "ad_network_combo") else 0
            if net_idx == 0:
                target_name = "monetag"
                net_tag = "MONETAG"
            elif net_idx == 1:
                target_name = "adsterra"
                net_tag = "ADSTERRA"
            elif net_idx == 2:
                target_name = "exoclick"
                net_tag = "EXOCLICK"
            else:
                target_name = "adsterra"
                net_tag = "ROTASI 3 NET"

            stats = self._shared_pm.get_stats()
            max_u = int(self.max_uses_spin.value()) if hasattr(self, "max_uses_spin") else 2
            cd_h = float(self.cooldown_spin.value()) if hasattr(self, "cooldown_spin") else 6.0
            t_stats = self._shared_pm.get_target_stats(
                target=target_name,
                max_uses_per_day=max_u,
                cooldown_seconds=cd_h * 3600,
            )
            total_p = stats.get("total", 0)
            alive_p = stats.get("alive", 0)
            in_use_p = stats.get("in_use", 0)
            fresh_p = t_stats.get("fresh", 0)
            ready_s2 = t_stats.get("ready_secondary", 0)
            cooldown_p = t_stats.get("in_cooldown", 0)
            self.proxy_pool_label.setText(
                f"[{net_tag}] ALIVE: {alive_p} ({in_use_p} aktif) | Fresh: {fresh_p} | Siap (Hit 2): {ready_s2} | Cooldown: {cooldown_p} | Total: {total_p}"
            )
        except Exception:
            pass

        ctrl = self.controller
        if ctrl and ctrl.running:
            secs = int(time.time() - ctrl.started_at)
            self.uptime_label.setText(f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}")
            if ctrl.budget:
                if getattr(ctrl, "dynamic_proxy_mode", False):
                    try:
                        stats = self._shared_pm.get_stats()
                        current_pool_size = stats.get("total", 0)
                        if current_pool_size > ctrl.budget.max_sessions:
                            ctrl.budget.set_max_sessions(current_pool_size)
                    except Exception:
                        pass

                snap = ctrl.budget.snapshot()
                completed = snap["completed"]
                if snap.get("unlimited"):
                    self.progress.setMaximum(0)
                    self.progress.setValue(0)
                    self.progress.setFormat(f"{completed} kunjungan ∞")
                elif getattr(ctrl, "dynamic_proxy_mode", False):
                    mx = snap["max_sessions"] or 1
                    self.progress.setMaximum(mx)
                    self.progress.setValue(completed)
                    self.progress.setFormat(f"{completed} / {mx} kunjungan (dinamis realtime)")
                else:
                    mx = snap["max_sessions"] or 1
                    self.progress.setMaximum(mx)
                    self.progress.setValue(completed)
                    self.progress.setFormat(f"{completed} / {mx} kunjungan")
                self.total_lbl.setText(f"Total  {completed}")
                self.pass_lbl.setText(f"Lolos  {snap['passed']}")
                self.warn_lbl.setText(f"Waspada  {snap['warned']}")
                self.fail_lbl.setText(f"Gagal  {snap['failed']}")

        # Auto refresh Proxy Tab jika sedang aktif dibuka
        if hasattr(self, "tabs") and self.tabs.currentIndex() == 1:
            try:
                self._refresh_proxy_tab_data()
            except Exception:
                pass

        # Broadcast Telemetry ke Supabase Realtime (Pure WebSocket, 0 DB storage)
        try:
            from core.telemetry_reporter import get_telemetry_reporter
            from run_bot import get_country_flag
            reporter = get_telemetry_reporter()
            w_list = [w for w in self.workers_state.values()]
            running = bool(ctrl and ctrl.running)
            uptime_s = int(time.time() - ctrl.started_at) if (ctrl and ctrl.running) else 0

            # Build full transparent proxies list
            all_p = self._shared_pm.get_proxies()
            act_ips = {w.get("proxy_ip"): f"Worker #{wid} ({w.get('target_net', '—')})" for wid, w in self.workers_state.items() if w.get("proxy_ip") and w.get("proxy_ip") != "—"}
            p_list = []
            for p in all_p[:80]:
                ip = p.get("ip_detected") or p.get("host", "?")
                c_name = country_label(p.get("country"))
                c_flag = get_country_flag(c_name)
                is_active = (ip in act_ips) or (p.get("usage") == "IN_USE")
                tu = p.get("target_usage") or {}
                ad_hit = (tu.get("adsterra") or {}).get("count", 0)
                mn_hit = (tu.get("monetag") or {}).get("count", 0)
                exo_hit = (tu.get("exoclick") or {}).get("count", 0)
                last_u = max(
                    (tu.get("adsterra") or {}).get("last_used", 0) or 0,
                    (tu.get("monetag") or {}).get("last_used", 0) or 0,
                    (tu.get("exoclick") or {}).get("last_used", 0) or 0,
                )
                p_list.append({
                    "ip": ip,
                    "port": p.get("port", 0),
                    "country": c_name,
                    "country_flag": c_flag,
                    "health": p.get("health", "ALIVE"),
                    "is_active": is_active,
                    "used_by": act_ips.get(ip, None),
                    "adsterra_hit": ad_hit,
                    "monetag_hit": mn_hit,
                    "exoclick_hit": exo_hit,
                    "last_used": last_u,
                    "latency_ms": p.get("latency_ms", 0),
                })

            reporter.broadcast_state(
                target_network=net_tag if "net_tag" in locals() else "HYBRID",
                running=running,
                uptime_seconds=uptime_s,
                workers=w_list,
                proxy_summary={
                    "total": total_p if "total_p" in locals() else 0,
                    "alive": alive_p if "alive_p" in locals() else 0,
                    "in_use": in_use_p if "in_use_p" in locals() else 0,
                    "fresh": fresh_p if "fresh_p" in locals() else 0,
                },
                proxies=p_list,
            )
        except Exception:
            pass


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def launch_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1e2128"))
    palette.setColor(QPalette.Base, QColor("#1b1f26"))
    palette.setColor(QPalette.Text, QColor("#d7dae0"))
    palette.setColor(QPalette.Button, QColor("#262b34"))
    palette.setColor(QPalette.ButtonText, QColor("#d7dae0"))
    palette.setColor(QPalette.Highlight, QColor("#2f7df6"))
    app.setPalette(palette)

    win = Dashboard()
    win.show()
    try:
        return app.exec()
    except KeyboardInterrupt:
        ctrl = getattr(win, "controller", None)
        if ctrl is not None and ctrl.running:
            ctrl.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(launch_gui())
