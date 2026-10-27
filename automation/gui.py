#!/usr/bin/env python3
"""Unified modern native desktop GUI for Bot Shortlink (Monetag & ExoClick).

Built with PySide6 (Qt). Mendukung pemilahan target iklan:
1. 💎 Hanya Monetag: Memaksa web memunculkan iklan MultiTag & Direct Link Monetag.
2. 🎯 Hanya ExoClick: Memaksa web memunculkan iklan Popunder, Push, Banner & Native ExoClick.
3. 🔄 Rotasi (50:50): Web memunculkan iklan Monetag & ExoClick secara seimbang bergantian.
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

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
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

from automation.engine import load_config
from automation.session import SessionBudget, country_label
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
    """Mengelola thread worker, rotasi proxy, dan budget untuk Monetag atau ExoClick."""

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
        m_workers = int(config.get("monetag_workers", 0))
        exo_workers = int(config.get("exoclick_workers", 0))
        num_workers = m_workers + exo_workers

        self.proxy_manager = ProxyManager()
        self.proxy_manager.reset_usage_to_idle()
        self.proxy_manager.reset_cursor(0)
        self.budget = SessionBudget(hard_max, 1)

        stats = self.proxy_manager.get_stats()
        is_unlimited = getattr(self.budget, "unlimited", False)
        mode_lbl = "Tanpa Batas (∞)" if is_unlimited else str(hard_max)

        self.emit("log_message", {
            "message": (
                f"Menyiapkan {num_workers} browser ({m_workers} Monetag + {exo_workers} ExoClick). Mode: {mode_lbl}. "
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

        if num_workers == 0:
            self.emit("log_message", {
                "message": "Tidak ada worker yang diaktifkan (Monetag: 0, ExoClick: 0).",
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
                # Reset hit target untuk kedua network agar mode unlimited berputar looping tanpa henti
                reset_hits = self.proxy_manager.reset_target_usage(None)
                self.budget.reset_proxy_counts()
                self.emit("log_message", {
                    "message": f"♻️ Mode Tanpa Batas: Pool proxy direset kembali ke 0/2 ({reset_hits} IP) untuk rotasi tanpa henti.",
                    "style": "cyan",
                })

        wid = 1
        # 1. Spawn Monetag Workers
        for _ in range(m_workers):
            if self.stop_event.is_set():
                break
            w_cfg = dict(config)
            w_cfg["target_url"] = config.get("monetag_target_url")
            w_cfg["target_network"] = "monetag"
            w_cfg["target_name"] = "monetag"

            self.emit("worker_init", {
                "worker_id": wid,
                "target_network": "💎 Monetag",
                "target_network_style": "magenta",
            })

            thread = threading.Thread(
                target=monetag_worker_thread_loop,
                args=(
                    wid, w_cfg, self.proxy_manager, self.budget,
                    self._worker_event, self.stop_event,
                ),
                kwargs={"reset_pool_callback": _reset_pool if getattr(self.budget, "unlimited", False) else None},
                daemon=True,
                name=f"Monetag-Worker-{wid}",
            )
            thread.start()
            self.threads.append(thread)
            wid += 1
            if wid <= num_workers:
                time.sleep(1.8)

        # 2. Spawn ExoClick Workers
        for _ in range(exo_workers):
            if self.stop_event.is_set():
                break
            w_cfg = dict(config)
            w_cfg["target_url"] = config.get("exoclick_target_url")
            w_cfg["target_network"] = "exoclick"
            w_cfg["target_name"] = "exoclick"

            self.emit("worker_init", {
                "worker_id": wid,
                "target_network": "🎯 ExoClick",
                "target_network_style": "bold cyan",
            })

            thread = threading.Thread(
                target=exoclick_worker_thread_loop,
                args=(
                    wid, w_cfg, self.proxy_manager, self.budget,
                    self._worker_event, self.stop_event,
                ),
                kwargs={"reset_pool_callback": _reset_pool if getattr(self.budget, "unlimited", False) else None},
                daemon=True,
                name=f"ExoClick-Worker-{wid}",
            )
            thread.start()
            self.threads.append(thread)
            wid += 1
            if wid <= num_workers:
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


class HarvesterThread(QThread):
    """Worker background thread untuk GoLogin Proxy Grabber di dalam GUI."""

    log_signal = Signal(str, str)         # (message, style)
    progress_signal = Signal(int, int)    # (added, target)
    finished_signal = Signal(int)         # (total_added)

    def __init__(
        self,
        target_proxies: int = 100,
        concurrency: int = 2,
        rounds: int = 2,
        headless: bool = True,
        direct: bool = False,
        skip_verifier: bool = False,
    ):
        super().__init__()
        self.target_proxies = target_proxies
        self.concurrency = concurrency
        self.rounds = rounds
        self.headless = headless
        self.direct = direct
        self.skip_verifier = skip_verifier
        self.stop_event = threading.Event()

    def run(self) -> None:
        from automation.gologin_grabber import run_gologin_harvest_job

        def _log(msg: str, style: str = "white") -> None:
            self.log_signal.emit(msg, style)

        def _prog(added: int, target: int) -> None:
            self.progress_signal.emit(added, target)

        try:
            total = run_gologin_harvest_job(
                target_proxies=self.target_proxies,
                concurrency=self.concurrency,
                rounds=self.rounds,
                headless=self.headless,
                direct=self.direct,
                skip_verifier=self.skip_verifier,
                stop_event=self.stop_event,
                on_log=_log,
                on_progress=_prog,
            )
            self.finished_signal.emit(total)
        except Exception as e:
            self.log_signal.emit(f"⚠️ Terjadi error pada runner Harvester: {e}", "red")
            self.finished_signal.emit(0)

    def stop(self) -> None:
        self.stop_event.set()


class Dashboard(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bot Shortlink — Controller Dasbor Monetag & ExoClick")
        self.resize(1260, 830)
        self.workers_state: Dict[int, Dict[str, Any]] = {}
        self.concurrency = 5
        self._controller_lock = threading.Lock()

        self.bridge = EventBridge()
        self.bridge.event.connect(self._on_event)
        self.bridge.finished.connect(self._on_run_finished)
        self.controller: Optional[RunController] = None
        self.harvester_thread: Optional[HarvesterThread] = None
        self._shared_pm = ProxyManager()

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def closeEvent(self, event) -> None:
        if self.controller and self.controller.running:
            self.controller.stop()
        if self.harvester_thread and self.harvester_thread.isRunning():
            self.harvester_thread.stop()
            self.harvester_thread.wait(2000)
        super().closeEvent(event)

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
        root.setSpacing(12)

        # Header row
        header = QHBoxLayout()
        title_block = QVBoxLayout()
        t = QLabel("Bot Shortlink & Ad Controller (Monetag & ExoClick)")
        t.setObjectName("title")
        self.target_label = QLabel("Monetag: https://article.riztama.my.id/m/  |  ExoClick: https://article.riztama.my.id/v/")
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

        # Control Card: Dedicated Monetag & ExoClick Settings
        ctrl_card, ctrl_layout = self._card("PENGATURAN TARGET IKLAN & POLA BROWSER (MONETAG & EXOCLICK)")
        ctrl_layout.setSpacing(8)

        # Split Panels: Monetag (Left) and ExoClick (Right)
        panels_row = QHBoxLayout()
        panels_row.setSpacing(12)

        # ── 1. SUB-CARD MONETAG ──
        m_frame = QFrame()
        m_frame.setObjectName("card")
        m_frame.setStyleSheet("background-color: #21252d; border: 1px solid #4a2f68; border-radius: 8px;")
        m_box = QVBoxLayout(m_frame)
        m_box.setContentsMargins(10, 8, 10, 8)
        m_box.setSpacing(6)

        m_title = QLabel("💎 Pengaturan Monetag (MultiTag & Direct Link)")
        m_title.setStyleSheet("color: #c77dff; font-weight: 700; font-size: 13px;")
        m_box.addWidget(m_title)

        m_grid = QGridLayout()
        m_grid.setHorizontalSpacing(8)
        m_grid.setVerticalSpacing(6)

        m_grid.addWidget(QLabel("Browser / Worker:"), 0, 0)
        self.monetag_workers_spin = QSpinBox()
        self.monetag_workers_spin.setRange(0, 20)
        self.monetag_workers_spin.setValue(2)
        self.monetag_workers_spin.setToolTip("Jumlah browser khusus Monetag (0 = nonaktifkan Monetag).")
        self.monetag_workers_spin.valueChanged.connect(self._update_worker_summary)
        m_grid.addWidget(self.monetag_workers_spin, 0, 1)

        m_grid.addWidget(QLabel("Rasio Direct Link:"), 0, 2)
        self.direct_chance_spin = QSpinBox()
        self.direct_chance_spin.setRange(10, 100)
        self.direct_chance_spin.setValue(50)
        self.direct_chance_spin.setSingleStep(5)
        self.direct_chance_spin.setSuffix(" % (Aman)")
        self.direct_chance_spin.setToolTip("Persentase sesi Monetag yang membuka Direct Link (disarankan 40%-60%).")
        m_grid.addWidget(self.direct_chance_spin, 0, 3)

        m_grid.addWidget(QLabel("URL Target Monetag:"), 1, 0)
        self.monetag_url_input = QLineEdit()
        self.monetag_url_input.setText("https://article.riztama.my.id/m/")
        self.monetag_url_input.setToolTip("Halaman website target yang memuat script MultiTag Monetag.")
        self.monetag_url_input.textChanged.connect(self._update_worker_summary)
        m_grid.addWidget(self.monetag_url_input, 1, 1, 1, 3)

        m_box.addLayout(m_grid)
        panels_row.addWidget(m_frame, 1)

        # ── 2. SUB-CARD EXOCLICK ──
        e_frame = QFrame()
        e_frame.setObjectName("card")
        e_frame.setStyleSheet("background-color: #21252d; border: 1px solid #1a4f6e; border-radius: 8px;")
        e_box = QVBoxLayout(e_frame)
        e_box.setContentsMargins(10, 8, 10, 8)
        e_box.setSpacing(6)

        e_title = QLabel("🎯 Pengaturan ExoClick (Popunder, Push, Banner, Native)")
        e_title.setStyleSheet("color: #38d6d6; font-weight: 700; font-size: 13px;")
        e_box.addWidget(e_title)

        e_grid = QGridLayout()
        e_grid.setHorizontalSpacing(8)
        e_grid.setVerticalSpacing(6)

        e_grid.addWidget(QLabel("Browser / Worker:"), 0, 0)
        self.exoclick_workers_spin = QSpinBox()
        self.exoclick_workers_spin.setRange(0, 20)
        self.exoclick_workers_spin.setValue(3)
        self.exoclick_workers_spin.setToolTip("Jumlah browser khusus ExoClick (0 = nonaktifkan ExoClick).")
        self.exoclick_workers_spin.valueChanged.connect(self._update_worker_summary)
        e_grid.addWidget(self.exoclick_workers_spin, 0, 1)

        e_grid.addWidget(QLabel("Alur Kerja Bot:"), 0, 2)
        self.flow_mode_combo = QComboBox()
        self.flow_mode_combo.addItems([
            "🔗 Shortlink 3-Langkah (~70s)",
            "⚡ Fast Ads Dwell (~15s)",
        ])
        self.flow_mode_combo.setToolTip("Pilih alur kerja penjelajahan halaman artikel & verifikasi gateway shortlink.")
        self.flow_mode_combo.currentIndexChanged.connect(self._update_worker_summary)
        e_grid.addWidget(self.flow_mode_combo, 0, 3)

        e_grid.addWidget(QLabel("URL Target ExoClick:"), 1, 0)
        self.exoclick_url_input = QLineEdit()
        self.exoclick_url_input.setText("https://article.riztama.my.id/v/")
        self.exoclick_url_input.setToolTip("Halaman website target yang memuat script iklan ExoClick.")
        self.exoclick_url_input.textChanged.connect(self._update_worker_summary)
        e_grid.addWidget(self.exoclick_url_input, 1, 1, 1, 3)

        e_box.addLayout(e_grid)
        panels_row.addWidget(e_frame, 1)

        ctrl_layout.addLayout(panels_row)

        # ── 3. COMMON CONTROLS & EXECUTION ROW ──
        comm_row = QHBoxLayout()
        comm_row.setSpacing(10)

        comm_row.addWidget(QLabel("Mode Kunjungan:"))
        self.visit_mode_combo = QComboBox()
        self.visit_mode_combo.addItems([
            "Sesuai Jumlah Proxy (Dinamis)",
            "Tanpa Batas",
            "Custom",
        ])
        self.visit_mode_combo.currentIndexChanged.connect(self._on_visit_mode_changed)
        comm_row.addWidget(self.visit_mode_combo)

        self.sessions_spin = QSpinBox()
        self.sessions_spin.setRange(1, 9999)
        self.sessions_spin.setValue(10)
        self.sessions_spin.setVisible(False)
        comm_row.addWidget(self.sessions_spin)

        comm_row.addWidget(QLabel("Jeda Cooldown:"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 24)
        self.cooldown_spin.setValue(6)
        self.cooldown_spin.setSuffix(" Jam")
        comm_row.addWidget(self.cooldown_spin)

        comm_row.addWidget(QLabel("Maks IP/Hari:"))
        self.max_uses_spin = QSpinBox()
        self.max_uses_spin.setRange(1, 5)
        self.max_uses_spin.setValue(2)
        comm_row.addWidget(self.max_uses_spin)

        init_cfg = load_config()
        self.headless_check = QCheckBox("Headless")
        self.headless_check.setChecked(bool(init_cfg.get("headless", False)))
        comm_row.addWidget(self.headless_check)

        self.worker_summary_label = QLabel("👥 Total: 5 Browser (2 Monetag + 3 ExoClick)")
        self.worker_summary_label.setStyleSheet("color: #38d6d6; font-weight: 700; font-size: 13px;")
        comm_row.addWidget(self.worker_summary_label)

        comm_row.addStretch(1)

        self.start_btn = QPushButton("▶  Mulai")
        self.start_btn.clicked.connect(self._start_run)
        self.stop_btn = QPushButton("■  Berhenti")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_run)
        comm_row.addWidget(self.start_btn)
        comm_row.addWidget(self.stop_btn)

        ctrl_layout.addLayout(comm_row)

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
        pt_header_card, pt_header_layout = self._card("STATUS & KONTROL PEMAKAIAN PROXY (MONETAG & EXOCLICK)")
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
        self.btn_reset_proxy_hits.setToolTip("Mereset pemakaian Monetag dan ExoClick menjadi 0/2 untuk seluruh proxy.")
        self.btn_reset_proxy_hits.clicked.connect(self._on_manual_reset_hits)
        pt_row.addWidget(self.btn_reset_proxy_hits)
        pt_header_layout.addLayout(pt_row)
        proxy_layout.addWidget(pt_header_card)

        # Proxy Table Card
        proxy_table_card, proxy_table_layout = self._card()
        self.proxy_table = QTableWidget(0, 9)
        self.proxy_table.setHorizontalHeaderLabels([
            "No", "IP Proxy", "Negara", "Status Jaringan",
            "Hit Monetag", "Hit ExoClick", "Sedang Dipakai Worker", "Terakhir Digunakan", "Latency"
        ])
        self.proxy_table.setAlternatingRowColors(True)
        self.proxy_table.verticalHeader().setVisible(False)
        self.proxy_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.proxy_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.proxy_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.proxy_table.horizontalHeader().setStretchLastSection(True)

        pt_column_widths = (
            (0, 45), (1, 140), (2, 100), (3, 120),
            (4, 120), (5, 120), (6, 170), (7, 130), (8, 80)
        )
        for col, width in pt_column_widths:
            self.proxy_table.setColumnWidth(col, width)
        self.proxy_table.setMinimumHeight(240)
        proxy_table_layout.addWidget(self.proxy_table)
        proxy_layout.addWidget(proxy_table_card, stretch=1)

        self.tabs.addTab(tab_proxy, "🌐 Pool & Status Pemakaian Proxy")

        # ── TAB 3: GOLOGIN PROXY HARVESTER ──
        tab_harvester = self._build_harvester_tab()
        self.tabs.addTab(tab_harvester, "🌾 GoLogin Proxy Harvester")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, stretch=1)

        # Log card (tetap di paling bawah untuk bot main runner)
        log_card, log_layout = self._card("LOG AKTIVITAS BOT")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(130)
        log_layout.addWidget(self.log)
        root.addWidget(log_card)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Siap — atur worker Monetag & ExoClick lalu tekan Mulai.")
        self._append_log("Aplikasi siap. Controller Monetag & ExoClick aktif.", "cyan")

    def _build_harvester_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(10)

        # Control Card
        ctrl_card, ctrl_layout = self._card("KONTROL HARVESTER GOLOGIN (AUTO-GRAB PROXY RESIDENSIAL)")
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Target Proxy Baru:"), 0, 0)
        self.harv_target_spin = QSpinBox()
        self.harv_target_spin.setRange(5, 3000)
        self.harv_target_spin.setValue(100)
        self.harv_target_spin.setSingleStep(25)
        self.harv_target_spin.setSuffix(" IP")
        self.harv_target_spin.setToolTip("Target jumlah proxy baru yang ingin dikumpulkan sebelum otomatis berhenti.")
        grid.addWidget(self.harv_target_spin, 0, 1)

        grid.addWidget(QLabel("Browser Concurrency:"), 0, 2)
        self.harv_concurrency_spin = QSpinBox()
        self.harv_concurrency_spin.setRange(1, 10)
        self.harv_concurrency_spin.setValue(2)
        self.harv_concurrency_spin.setToolTip("Jumlah browser yang aktif bersamaan saat membuat akun GoLogin dan panen proxy.")
        grid.addWidget(self.harv_concurrency_spin, 0, 3)

        grid.addWidget(QLabel("Rounds per Akun:"), 0, 4)
        self.harv_rounds_spin = QSpinBox()
        self.harv_rounds_spin.setRange(1, 10)
        self.harv_rounds_spin.setValue(2)
        self.harv_rounds_spin.setToolTip("Jumlah putaran grabbing per akun trial GoLogin (1 putaran = ~5 proxy, 2 putaran = ~10 proxy).")
        grid.addWidget(self.harv_rounds_spin, 0, 5)

        # Checkboxes row
        chk_layout = QHBoxLayout()
        chk_layout.setSpacing(16)
        self.harv_headless_check = QCheckBox("Mode Headless (Sembunyikan browser)")
        self.harv_headless_check.setChecked(True)
        chk_layout.addWidget(self.harv_headless_check)

        self.harv_direct_check = QCheckBox("Paksa Direct IP (Internet Lokal tanpa proxy pool)")
        self.harv_direct_check.setChecked(False)
        self.harv_direct_check.setToolTip("Centang jika ingin langsung panen menggunakan IP internet kamu tanpa meminjam proxy dari pool.")
        chk_layout.addWidget(self.harv_direct_check)

        self.harv_skip_verifier_check = QCheckBox("Lewati Preflight Audit (Skip Verifier)")
        self.harv_skip_verifier_check.setChecked(False)
        self.harv_skip_verifier_check.setToolTip("Lewati pengecekan IP awal.")
        chk_layout.addWidget(self.harv_skip_verifier_check)
        chk_layout.addStretch(1)

        grid.addLayout(chk_layout, 1, 0, 1, 6)
        top_row.addLayout(grid, stretch=1)

        # Right: Buttons & Status badge
        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)
        self.harv_start_btn = QPushButton("🌾  Mulai Panen Proxy")
        self.harv_start_btn.clicked.connect(self._start_harvester)
        self.harv_stop_btn = QPushButton("■  Berhenti Panen")
        self.harv_stop_btn.setObjectName("stopBtn")
        self.harv_stop_btn.setEnabled(False)
        self.harv_stop_btn.clicked.connect(self._stop_harvester)

        self.harv_status_badge = QLabel("STATUS: IDLE")
        self.harv_status_badge.setAlignment(Qt.AlignCenter)
        self.harv_status_badge.setStyleSheet("color: #8b93a1; font-weight: 700; font-size: 12px; background: #1b1f26; border-radius: 4px; padding: 4px;")

        btn_box.addWidget(self.harv_start_btn)
        btn_box.addWidget(self.harv_stop_btn)
        btn_box.addWidget(self.harv_status_badge)
        top_row.addLayout(btn_box)

        ctrl_layout.addLayout(top_row)
        layout.addWidget(ctrl_card)

        # Progress & Stats Card
        prog_card, prog_layout = self._card("PROGRES & STATISTIK PANEN")
        self.harv_progress = QProgressBar()
        self.harv_progress.setRange(0, 100)
        self.harv_progress.setValue(0)
        self.harv_progress.setFormat("0 / 100 proxy baru (0%)")
        prog_layout.addWidget(self.harv_progress)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(24)
        self.harv_stat_added = QLabel("Baru Didapat: 0")
        self.harv_stat_added.setStyleSheet("color: #3ddc84; font-weight: 700; font-size: 14px;")
        self.harv_stat_pool = QLabel("Total di Pool: —")
        self.harv_stat_pool.setStyleSheet("color: #38d6d6; font-weight: 700; font-size: 14px;")
        self.harv_stat_status = QLabel("Status: Siap memanen proxy")
        self.harv_stat_status.setStyleSheet("color: #d7dae0; font-size: 13px;")

        stat_row.addWidget(self.harv_stat_added)
        stat_row.addWidget(self.harv_stat_pool)
        stat_row.addWidget(self.harv_stat_status)
        stat_row.addStretch(1)
        prog_layout.addLayout(stat_row)
        layout.addWidget(prog_card)

        # Live Log Card
        log_card, log_layout = self._card("LOG TERMINAL HARVESTER REALTIME")
        log_bar = QHBoxLayout()
        log_bar.addWidget(QLabel("Output Log Eksekusi GoLogin Grabber:"))
        log_bar.addStretch(1)
        btn_clear_log = QPushButton("🗑️ Bersihkan Log")
        btn_clear_log.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        btn_clear_log.clicked.connect(lambda: self.harv_log.setPlainText(""))
        log_bar.addWidget(btn_clear_log)
        log_layout.addLayout(log_bar)

        self.harv_log = QPlainTextEdit()
        self.harv_log.setReadOnly(True)
        self.harv_log.setMaximumBlockCount(500)
        self.harv_log.setMinimumHeight(180)
        log_layout.addWidget(self.harv_log)
        layout.addWidget(log_card, stretch=1)

        return tab

    def _start_harvester(self) -> None:
        if self.harvester_thread and self.harvester_thread.isRunning():
            return

        target = int(self.harv_target_spin.value())
        concurrency = int(self.harv_concurrency_spin.value())
        rounds = int(self.harv_rounds_spin.value())
        headless = bool(self.harv_headless_check.isChecked())
        direct = bool(self.harv_direct_check.isChecked())
        skip_verifier = bool(self.harv_skip_verifier_check.isChecked())

        self.harv_start_btn.setEnabled(False)
        self.harv_stop_btn.setEnabled(True)
        self.harv_status_badge.setText("🌾 SEDANG MEMANEN...")
        self.harv_status_badge.setStyleSheet("color: #38d6d6; font-weight: 700; font-size: 12px; background: #1b1f26; border-radius: 4px; padding: 4px;")
        self.harv_progress.setRange(0, target)
        self.harv_progress.setValue(0)
        self.harv_progress.setFormat(f"0 / {target} proxy baru (0%)")
        self.harv_stat_added.setText("Baru Didapat: 0")
        self.harv_stat_status.setText("Status: Memulai worker grabber...")

        self.harvester_thread = HarvesterThread(
            target_proxies=target,
            concurrency=concurrency,
            rounds=rounds,
            headless=headless,
            direct=direct,
            skip_verifier=skip_verifier,
        )
        self.harvester_thread.log_signal.connect(self._on_harvester_log)
        self.harvester_thread.progress_signal.connect(self._on_harvester_progress)
        self.harvester_thread.finished_signal.connect(self._on_harvester_finished)
        self.harvester_thread.start()

    def _stop_harvester(self) -> None:
        if self.harvester_thread and self.harvester_thread.isRunning():
            self.harvester_thread.stop()
            self.harv_status_badge.setText("⏳ MENGHENTIKAN...")
            self.harv_status_badge.setStyleSheet("color: #ffcc33; font-weight: 700; font-size: 12px; background: #1b1f26; border-radius: 4px; padding: 4px;")
            self.harv_stat_status.setText("Status: Menghentikan worker...")
            self.harv_stop_btn.setEnabled(False)

    def _on_harvester_log(self, message: str, style: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        color = STATUS_COLORS.get(style, "#b8c0cc")
        html = f'<span style="color:#6b7280">[{ts}]</span> <span style="color:{color}">{_esc(message)}</span>'
        self.harv_log.appendHtml(html)

    def _on_harvester_progress(self, added: int, target: int) -> None:
        pct = int((added / target) * 100) if target > 0 else 0
        self.harv_progress.setValue(min(added, target))
        self.harv_progress.setFormat(f"{added} / {target} proxy baru ({pct}%)")
        self.harv_stat_added.setText(f"Baru Didapat: {added}")
        stats = self._shared_pm.get_stats()
        self.harv_stat_pool.setText(f"Total di Pool: {stats.get('total', 0)} IP")
        self._refresh_proxy_tab_data(force=True)

    def _on_harvester_finished(self, total_added: int) -> None:
        self.harv_start_btn.setEnabled(True)
        self.harv_stop_btn.setEnabled(False)
        self.harv_status_badge.setText("✅ SELESAI")
        self.harv_status_badge.setStyleSheet("color: #3ddc84; font-weight: 700; font-size: 12px; background: #1b1f26; border-radius: 4px; padding: 4px;")
        self.harv_stat_status.setText(f"Selesai! Berhasil panen +{total_added} proxy baru.")
        stats = self._shared_pm.get_stats()
        self.harv_stat_pool.setText(f"Total di Pool: {stats.get('total', 0)} IP")
        self._refresh_proxy_tab_data(force=True)
        self._append_log(f"🌾 Harvester selesai: +{total_added} proxy baru telah ditambahkan ke pool.", "bold green")

    def _update_worker_summary(self) -> None:
        m = self.monetag_workers_spin.value() if hasattr(self, "monetag_workers_spin") else 0
        e = self.exoclick_workers_spin.value() if hasattr(self, "exoclick_workers_spin") else 0
        total = m + e
        if hasattr(self, "worker_summary_label"):
            self.worker_summary_label.setText(f"👥 Total: {total} Browser ({m} Monetag + {e} ExoClick)")
        if hasattr(self, "target_label"):
            m_url = self.monetag_url_input.text().strip() if hasattr(self, "monetag_url_input") else ""
            e_url = self.exoclick_url_input.text().strip() if hasattr(self, "exoclick_url_input") else ""
            self.target_label.setText(f"Monetag: {m_url or '—'}  |  ExoClick: {e_url or '—'}")
        self._update_pipeline_banner()

    def _update_pipeline_banner(self) -> None:
        if not hasattr(self, "pipeline_box"):
            return
        while self.pipeline_box.count():
            item = self.pipeline_box.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        m_w = self.monetag_workers_spin.value() if hasattr(self, "monetag_workers_spin") else 0
        exo_w = self.exoclick_workers_spin.value() if hasattr(self, "exoclick_workers_spin") else 0

        if m_w > 0 and exo_w > 0:
            steps_info = [
                ("💎 Monetag:", "#c77dff"),
                ("1. Audit IP", "#38d6d6"), ("➔", "#6b7280"),
                ("2. MultiTag", "#38d6d6"), ("➔", "#6b7280"),
                ("3. Natural Wander", "#5aa9ff"), ("➔", "#6b7280"),
                ("4. Popunder", "#c77dff"), ("➔", "#6b7280"),
                ("5. Direct Link", "#ffcc33"), ("➔", "#6b7280"),
                ("✅ Selesai", "#3ddc84"),
                ("  |  ", "#454d5a"),
                ("🎯 ExoClick:", "#38d6d6"),
                ("1. Audit IP", "#38d6d6"), ("➔", "#6b7280"),
                ("2. Buka Web", "#38d6d6"), ("➔", "#6b7280"),
                ("3. In-Page Push", "#ffcc33"), ("➔", "#6b7280"),
                ("4. Native Banner", "#c77dff"), ("➔", "#6b7280"),
                ("5. Dwell Popunder", "#ff5c5c"), ("➔", "#6b7280"),
                ("✅ Selesai", "#3ddc84"),
            ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText(
                    f"💎 Monetag ({m_w} browser) membuka MultiTag & Direct Link. 🎯 ExoClick ({exo_w} browser) membuka Popunder, Push, Native, & Display Banner."
                )
        elif m_w > 0:
            steps_info = [
                ("💎 Monetag Flow:", "#c77dff"),
                ("1. 🛡️ Audit IP", "#38d6d6"), ("➔", "#6b7280"),
                ("2. 🌐 MultiTag Web", "#38d6d6"), ("➔", "#6b7280"),
                ("3. 📜 Natural Wander", "#5aa9ff"), ("➔", "#6b7280"),
                ("4. 📑 Dwell Popunder", "#c77dff"), ("➔", "#6b7280"),
                ("5. 🔗 Dwell Direct Link", "#ffcc33"), ("➔", "#6b7280"),
                ("6. ✅ Selesai", "#3ddc84"),
            ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText("💎 Target Monetag Aktif: Seluruh browser menjalankan flow Monetag.")
        else:
            steps_info = [
                ("🎯 ExoClick Flow:", "#38d6d6"),
                ("1. 🛡️ Audit IP", "#38d6d6"), ("➔", "#6b7280"),
                ("2. 🌐 Buka Web", "#38d6d6"), ("➔", "#6b7280"),
                ("3. 💬 In-Page Push", "#ffcc33"), ("➔", "#6b7280"),
                ("4. 🖼️ Native Banner", "#c77dff"), ("➔", "#6b7280"),
                ("5. 📑 Dwell Popunder", "#ff5c5c"), ("➔", "#6b7280"),
                ("6. ✅ Selesai", "#3ddc84"),
            ]
            if hasattr(self, "hint_label"):
                self.hint_label.setText("🎯 Target ExoClick Aktif: Seluruh browser menjalankan flow ExoClick.")

        for text, color in steps_info:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: {'700' if text not in ('➔', '  |  ') else '400'};")
            self.pipeline_box.addWidget(lbl)
        self.pipeline_box.addStretch(1)

    def _on_visit_mode_changed(self, idx: int) -> None:
        self.sessions_spin.setVisible(idx == 2)

    def _build_config(self) -> Dict[str, Any]:
        cfg = load_config()
        m_workers = int(self.monetag_workers_spin.value())
        exo_workers = int(self.exoclick_workers_spin.value())
        total_workers = m_workers + exo_workers

        cfg["monetag_workers"] = m_workers
        cfg["exoclick_workers"] = exo_workers
        cfg["concurrency"] = total_workers

        m_raw = self.monetag_url_input.text().strip() or "https://article.riztama.my.id/m/"
        exo_raw = self.exoclick_url_input.text().strip() or "https://article.riztama.my.id/v/"

        cfg["monetag_target_url"] = m_raw
        cfg["exoclick_target_url"] = exo_raw
        cfg["direct_link_url"] = "https://uplcm.com/4/12124796"
        cfg["direct_link_chance"] = float(self.direct_chance_spin.value()) / 100.0

        flow_idx = self.flow_mode_combo.currentIndex()
        cfg["traffic_mode"] = "direct_article" if flow_idx == 1 else "shortlink"

        cfg["max_uses_per_day"] = int(self.max_uses_spin.value())
        cfg["proxy_cooldown_hours"] = float(self.cooldown_spin.value())
        cfg["headless"] = bool(self.headless_check.isChecked())

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

        self.concurrency = total_workers
        self._reset_state(m_workers, exo_workers)
        return cfg

    def _reset_state(self, m_workers: int, exo_workers: int) -> None:
        self.workers_state = {}
        total = m_workers + exo_workers
        wid = 1
        for _ in range(m_workers):
            self.workers_state[wid] = {
                "target_net": "💎 Monetag",
                "target_net_style": "magenta",
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
            wid += 1

        for _ in range(exo_workers):
            self.workers_state[wid] = {
                "target_net": "🎯 ExoClick",
                "target_net_style": "bold cyan",
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
            wid += 1

        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.log.setPlainText("")
        self._append_log(f"Menyiapkan {total} browser ({m_workers} Monetag + {exo_workers} ExoClick)...", "cyan")
        self._refresh_table()
        self._refresh_proxy_tab_data(force=True)

    def _start_run(self) -> None:
        m_workers = int(self.monetag_workers_spin.value())
        exo_workers = int(self.exoclick_workers_spin.value())
        if m_workers + exo_workers <= 0:
            self._append_log("⚠️ Tentukan minimal 1 browser (Monetag atau ExoClick)!", "bold yellow")
            self.statusBar().showMessage("Peringatan: Tentukan minimal 1 browser aktif.")
            return

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
            self.monetag_workers_spin,
            self.monetag_url_input,
            self.direct_chance_spin,
            self.exoclick_workers_spin,
            self.exoclick_url_input,
            self.flow_mode_combo,
            self.visit_mode_combo,
            self.sessions_spin,
            self.max_uses_spin,
            self.cooldown_spin,
            self.headless_check,
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
            mn_hit = (tu.get("monetag") or {}).get("count", 0)
            exo_hit = (tu.get("exoclick") or {}).get("count", 0)

            if is_active:
                in_use_count += 1
            if health == "COOLDOWN":
                cooldown_count += 1
            if mn_hit == 0 and exo_hit == 0:
                fresh_count += 1
            if mn_hit > 0 or exo_hit > 0:
                used_count += 1

            if search_q and (search_q not in ip.lower() and search_q not in c_name.lower()):
                continue

            if f_idx == 1 and not is_active:
                continue
            elif f_idx == 2 and (mn_hit == 0 and exo_hit == 0):
                continue
            elif f_idx == 3 and (mn_hit > 0 or exo_hit > 0):
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
        center_cols = (0, 2, 3, 4, 5, 6, 7, 8)

        for r, p in enumerate(display_list):
            ip = p.get("ip_detected") or p.get("host", "?")
            c_name = country_label(p.get("country"))
            health = p.get("health", "ALIVE")
            is_active = ip in active_worker_ips

            tu = p.get("target_usage") or {}
            mn_data = tu.get("monetag") or {}
            mn_hit = mn_data.get("count", 0)
            exo_data = tu.get("exoclick") or {}
            exo_hit = exo_data.get("count", 0)

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

            l_mn = mn_data.get("last_used") or 0
            l_exo = exo_data.get("last_used") or 0
            latest = max(l_mn, l_exo)
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
                mn_str,
                exo_str,
                w_str,
                last_used_str,
                lat_str,
            ]
            row_colors = {
                3: status_color,
                4: "#3ddc84" if mn_hit == 0 else ("#ffcc33" if mn_hit == 1 else "#ff5c5c"),
                5: "#3ddc84" if exo_hit == 0 else ("#ffcc33" if exo_hit == 1 else "#ff5c5c"),
                6: w_color,
                7: "#d7dae0" if latest > 0 else "#6b7280",
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
            m_w = self.monetag_workers_spin.value() if hasattr(self, "monetag_workers_spin") else 0
            exo_w = self.exoclick_workers_spin.value() if hasattr(self, "exoclick_workers_spin") else 0
            if m_w > 0 and exo_w > 0:
                target_name = "monetag"
                net_tag = f"M({m_w})+E({exo_w})"
            elif m_w > 0:
                target_name = "monetag"
                net_tag = "MONETAG"
            else:
                target_name = "exoclick"
                net_tag = "EXOCLICK"

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
                mn_hit = (tu.get("monetag") or {}).get("count", 0)
                exo_hit = (tu.get("exoclick") or {}).get("count", 0)
                last_u = max(
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
