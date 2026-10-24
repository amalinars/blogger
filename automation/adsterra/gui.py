#!/usr/bin/env python3
"""Modern native desktop GUI for the Adsterra shortlink flow QA dashboard.

Built with PySide6 (Qt). Runs the sticky-proxy gate-flow workers (with an
independent browser + proxy verifier) and renders a live graphical dashboard
with start/stop controls. Worker threads communicate with the GUI thread only
through a Qt signal bridge, so widget updates always happen on the main thread.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from automation.adsterra.flow_qa import flow_worker_thread_loop
from automation.adsterra.qa import (
    SessionBudget,
    country_label,
    load_config,
)
from automation.adsterra.report import utc_now_iso, write_run_summary
from core.proxy_manager import ProxyManager


# ── Dark modern theme stylesheet ─────────────────────────────────────────────
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
QFrame#cardTitle { border: none; }
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
    """Marshals events from worker/orchestration threads onto the GUI thread."""

    event = Signal(str, dict)
    finished = Signal()


class RunController(QObject):
    """Owns the worker threads, budget, and proxy rotation for one run."""

    def __init__(self, bridge: EventBridge):
        super().__init__()
        self.bridge = bridge
        self.stop_event = threading.Event()
        self.threads: List[threading.Thread] = []
        self.sticky: Dict[int, Dict[str, Any]] = {}
        self.budget: Optional[SessionBudget] = None
        self.proxy_manager: Optional[ProxyManager] = None
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
        self.sticky = {}
        self._opened = set()
        self._orchestration = threading.Thread(
            target=self._run, args=(config,), daemon=True, name="AdsterraOrchestrator"
        )
        self._orchestration.start()

    def _run(self, config: Dict[str, Any]) -> None:
        hard_max = int(config["max_sessions_per_run"])
        # Per-proxy cap = 1 → never reuse the same IP within a run (rotation).
        self.proxy_manager = ProxyManager()
        self.proxy_manager.reset_usage_to_idle()
        self.proxy_manager.reset_cursor(0)
        self.budget = SessionBudget(hard_max, 1)

        num_workers = int(config["concurrency"])
        stats = self.proxy_manager.get_stats()
        self.emit("log_message", {
            "message": (
                f"Menyiapkan {num_workers} browser. Setiap kunjungan pakai IP baru "
                f"(rotasi). Stok IP aktif: {stats.get('alive', 0)}."
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

        # ── Rolling staggered startup: launch worker N+1 once worker N has
        #    secured an IP / opened its browser (avoids a launch spike). ──
        for wid in range(1, num_workers + 1):
            if self.stop_event.is_set():
                break
            thread = threading.Thread(
                target=flow_worker_thread_loop,
                args=(
                    wid, config, self.proxy_manager, self.budget,
                    self._worker_event, self.stop_event,
                ),
                daemon=True,
                name=f"AdsterraQA-Worker-{wid}",
            )
            thread.start()
            self.threads.append(thread)

            if wid < num_workers:
                self.emit("log_message", {
                    "message": f"Menyiapkan browser {wid + 1}...", "style": "dim"
                })
                deadline = time.time() + 60
                while time.time() < deadline and not self.stop_event.is_set():
                    if wid in self._opened:
                        break
                    if not thread.is_alive():
                        break
                    time.sleep(0.5)

        # ── Wait until all workers finish or budget exhausted ──
        while not self.stop_event.is_set():
            if all(not t.is_alive() for t in self.threads):
                break
            if self.budget and self.budget.is_exhausted():
                break
            time.sleep(0.5)

        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=15.0)

        self.running = False
        self.bridge.finished.emit()

    def _worker_event(self, etype: str, data: Dict[str, Any]) -> None:
        # Called from worker threads. Record browser-open readiness for the
        # staggered startup gate, then forward through the thread-safe bridge.
        wid = data.get("worker_id")
        if wid is not None and etype in (
            "proxy_assigned", "session_started", "ad_check", "scroll", "geo_report"
        ):
            self._opened.add(wid)
        self.bridge.event.emit(etype, data)

    def stop(self) -> None:
        self.stop_event.set()


# ── Main window ──────────────────────────────────────────────────────────────
class Dashboard(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bot Shortlink — Dasbor")
        self.resize(980, 680)
        self.workers_state: Dict[int, Dict[str, Any]] = {}
        self.concurrency = 3
        self._controller_lock = threading.Lock()

        self.bridge = EventBridge()
        self.bridge.event.connect(self._on_event)
        self.bridge.finished.connect(self._on_run_finished)
        self.controller: Optional[RunController] = None

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    # ── UI construction ──
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
        t = QLabel("Bot Shortlink")
        t.setObjectName("title")
        self.target_label = QLabel("alamat: —")
        self.target_label.setObjectName("subtitle")
        title_block.addWidget(t)
        title_block.addWidget(self.target_label)
        header.addLayout(title_block)
        header.addStretch(1)

        self.uptime_label = QLabel("00:00:00")
        self.uptime_label.setObjectName("metricValue")
        header.addWidget(self.uptime_label, alignment=Qt.AlignRight)
        root.addLayout(header)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0 / 0 kunjungan")
        root.addWidget(self.progress)

        # Control card
        ctrl_card, ctrl_layout = self._card("PENGATURAN")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        
        grid.addWidget(QLabel("Jumlah Browser"), 0, 0)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 8)
        self.workers_spin.setValue(3)
        self.workers_spin.setToolTip(
            "Berapa browser dibuka bersamaan. Tiap browser memakai IP (proxy) sendiri."
        )
        grid.addWidget(self.workers_spin, 0, 1)
        
        grid.addWidget(QLabel("Total Kunjungan"), 0, 2)
        self.sessions_spin = QSpinBox()
        self.sessions_spin.setRange(1, 50)
        self.sessions_spin.setValue(8)
        self.sessions_spin.setToolTip(
            "Jumlah maksimal halaman dibuka dalam satu kali jalan. Setelah tercapai, bot berhenti."
        )
        grid.addWidget(self.sessions_spin, 0, 3)
        
        self.headless_check = QCheckBox("Sembunyikan jendela browser")
        self.headless_check.setChecked(False)
        self.headless_check.setToolTip(
            "Biarkan tidak dicentang agar browser benar-benar terlihat. Mode "
            "tersembunyi (headless) lebih mudah difilter Adsterra sehingga "
            "impresi sering tidak dihitung."
        )
        grid.addWidget(self.headless_check, 1, 0, 1, 2)
        
        self.start_btn = QPushButton("\u25b6  Mulai")
        self.start_btn.clicked.connect(self._start_run)
        self.stop_btn = QPushButton("\u25a0  Berhenti")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_run)
        grid.addWidget(self.start_btn, 0, 4, 2, 1)
        grid.addWidget(self.stop_btn, 0, 5, 2, 1)
        
        grid.setColumnStretch(3, 1)
        ctrl_layout.addLayout(grid)
        hint = QLabel(
            "Setiap kunjungan memakai IP (proxy) baru — IP tidak pernah dipakai ulang. "
            "Jalan berhenti saat Total Kunjungan tercapai atau semua IP sudah terpakai. "
            "Tabel menampilkan negara, IP keluar, dan apakah browser ketahuan sebagai bot."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        ctrl_layout.addWidget(hint)
        root.addWidget(ctrl_card)

        # Worker table card
        table_card, table_layout = self._card(
            "DAFTAR BROWSER  (tiap baris = 1 browser; IP berganti tiap kunjungan + hasil cek otomatis)"
        )
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(
            ["No", "Negara", "IP Proxy", "IP Keluar", "Zona Waktu", "Locale", "Bot?", "WebRTC", "Iklan", "Nilai", "Status", "Selesai"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        for col, width in ((0, 42), (1, 90), (2, 130), (3, 130), (4, 130), (5, 90), (6, 65), (7, 70), (8, 60), (9, 55), (10, 150)):
            self.table.setColumnWidth(col, width)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(240)
        table_layout.addWidget(self.table)
        root.addWidget(table_card, stretch=1)

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
        root.addWidget(sum_card)

        # Log card
        log_card, log_layout = self._card("LOG AKTIVITAS")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(140)
        log_layout.addWidget(self.log)
        root.addWidget(log_card)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Siap — atur jumlah lalu tekan Mulai.")

        self._append_log("Aplikasi siap. Setiap kunjungan pakai IP baru (rotasi).", "cyan")

    # ── Run control ──
    def _build_config(self) -> Dict[str, Any]:
        cfg = load_config()
        cfg["concurrency"] = int(self.workers_spin.value())
        cfg["max_sessions_per_run"] = int(self.sessions_spin.value())
        cfg["headless"] = bool(self.headless_check.isChecked())
        self.concurrency = cfg["concurrency"]
        self.target_label.setText(f"alamat: {cfg.get('target_url', '-')}")
        self._reset_state(cfg["concurrency"])
        return cfg

    def _reset_state(self, concurrency: int) -> None:
        self.workers_state = {}
        for wid in range(1, concurrency + 1):
            self.workers_state[wid] = {
                "proxy_ip": "—", "out_ip": "—", "country": "—",
                "tz": "—", "tz_style": "dim",
                "locale": "—", "locale_style": "dim",
                "bot": "—", "bot_style": "dim",
                "webrtc": "—", "webrtc_style": "dim",
                "ads": "—", "ads_style": "dim",
                "vscore": "—", "vscore_style": "dim",
                "status": "Menunggu", "status_style": "dim",
                "sessions_done": 0,
            }
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.log.setPlainText("")
        self._append_log(f"Menyiapkan {concurrency} browser...", "cyan")
        self._refresh_table()

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
        self._append_log("Dihentikan — menunggu kunjungan yang sedang jalan selesai.", "red")

    def _on_run_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_controls_enabled(True)
        self.statusBar().showMessage("Selesai.")
        self._append_log("Semua selesai.", "green")

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in (self.workers_spin, self.sessions_spin, self.headless_check):
            w.setEnabled(enabled)

    # ── Event handling (GUI thread) ──
    def _on_event(self, etype: str, data: Dict[str, Any]) -> None:
        wid = data.get("worker_id", 0)
        w = self.workers_state.get(wid)
        if etype == "log_message":
            self._append_log(data.get("message", ""), data.get("style", "white"))
            return
        if w is None:
            return
        if etype == "status_update":
            status = data.get("status", "")
            w["status"] = status
            low = status.lower()
            if "gagal" in low or "error" in low or "fail" in low:
                w["status_style"] = "bold red"
            elif "jeda" in low or "cooldown" in low:
                w["status_style"] = "cyan"
            elif "cek" in low or "verifier" in low:
                w["status_style"] = "magenta"
            elif any(k in low for k in ("buka", "scroll", "klik", "inspeksi", "mencoba", "loading", "inspect", "flow")):
                w["status_style"] = "bold yellow"
            else:
                w["status_style"] = "cyan"
        elif etype == "proxy_assigned":
            w["proxy_ip"] = data.get("ip", "—")
            w["country"] = country_label(data.get("country"))
            tz_hint = data.get("timezone")
            locale_hint = data.get("locale")
            if tz_hint:
                w["tz"] = tz_hint
                w["tz_style"] = "dim"
            if locale_hint:
                w["locale"] = locale_hint
                w["locale_style"] = "dim"
            w["status"] = f"IP: {w['proxy_ip']}"
            w["status_style"] = "cyan"
        elif etype == "geo_report":
            tz_actual = str(data.get("actual_timezone") or "\u2014")
            tz_matched = data.get("timezone_matched")
            exp_tz = str(data.get("expected_timezone") or "?")
            if tz_matched is True:
                w["tz"] = f"{tz_actual} \u2713"
                w["tz_style"] = "bold green"
            elif tz_matched is False:
                w["tz"] = f"{tz_actual} \u2717"
                w["tz_style"] = "bold red"
                self._append_log(
                    f"[W{wid}] Zona waktu tidak cocok: browser='{tz_actual}'  seharusnya='{exp_tz}'",
                    "yellow",
                )
            else:
                w["tz"] = tz_actual
                w["tz_style"] = "yellow"
            loc_actual = str(data.get("actual_locale") or "\u2014")
            loc_matched = data.get("locale_matched")
            exp_loc = str(data.get("expected_locale") or "?")
            if loc_matched is True:
                w["locale"] = f"{loc_actual} \u2713"
                w["locale_style"] = "bold green"
            elif loc_matched is False:
                w["locale"] = f"{loc_actual} \u2717"
                w["locale_style"] = "bold yellow"
                self._append_log(
                    f"[W{wid}] Locale tidak cocok: browser='{loc_actual}'  seharusnya='{exp_loc}'",
                    "yellow",
                )
            else:
                w["locale"] = loc_actual
                w["locale_style"] = "dim"
        elif etype == "verifier_report":
            detected_country = country_label(data.get("detected_country"))
            if detected_country and detected_country != "Unknown":
                w["country"] = detected_country
            w["out_ip"] = data.get("detected_ip") or w["proxy_ip"]
            if data.get("bot_detected"):
                w["bot"] = "Bot!"
                w["bot_style"] = "bold red"
            else:
                w["bot"] = "Aman"
                w["bot_style"] = "bold green"
            if data.get("webrtc_leak"):
                w["webrtc"] = "Bocor"
                w["webrtc_style"] = "bold red"
            else:
                w["webrtc"] = "Aman"
                w["webrtc_style"] = "bold green"
            if data.get("adblock_detected") or not data.get("ads_allowed", True):
                w["ads"] = "Blokir"
                w["ads_style"] = "bold red"
            else:
                w["ads"] = "OK"
                w["ads_style"] = "bold green"
            score = data.get("score", 0)
            w["vscore"] = str(score)
            w["vscore_style"] = (
                "bold green" if data.get("is_safe") and score >= 80
                else ("bold yellow" if score >= 60 else "bold red")
            )
        elif etype == "session_started":
            w["status"] = "Membuka halaman…"
            w["status_style"] = "bold yellow"
        elif etype == "session_completed":
            raw = data.get("status", "FAIL")
            label = {"PASS": "LOLOS", "WARN": "WASPADA", "FAIL": "GAGAL"}.get(raw, raw)
            w["status"] = f"Selesai: {label}"
            w["status_style"] = {
                "PASS": "bold green", "WARN": "bold yellow", "FAIL": "bold red"
            }.get(raw, "white")
            w["sessions_done"] = w.get("sessions_done", 0) + 1
        self._refresh_table()

    def _refresh_table(self) -> None:
        ids = sorted(self.workers_state.keys())
        if self.table.rowCount() != len(ids):
            self.table.setRowCount(len(ids))
        center_cols = (0, 4, 5, 6, 7, 8, 9, 11)
        for r, wid in enumerate(ids):
            w = self.workers_state[wid]
            cells = [
                str(wid), w["country"], w["proxy_ip"], w["out_ip"],
                w["tz"], w["locale"],
                w["bot"], w["webrtc"], w["ads"], w["vscore"],
                w["status"], str(w["sessions_done"]),
            ]
            color_keys = {
                4: w["tz_style"], 5: w["locale_style"],
                6: w["bot_style"], 7: w["webrtc_style"], 8: w["ads_style"],
                9: w["vscore_style"], 10: w["status_style"],
            }
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(
                    Qt.AlignVCenter | (Qt.AlignCenter if c in center_cols else Qt.AlignLeft)
                )
                if c in color_keys:
                    item.setForeground(QColor(STATUS_COLORS.get(color_keys[c], "#d7dae0")))
                self.table.setItem(r, c, item)

    def _append_log(self, message: str, style: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        color = STATUS_COLORS.get(style, "#b8c0cc")
        html = f'<span style="color:#6b7280">[{ts}]</span> <span style="color:{color}">{_esc(message)}</span>'
        self.log.appendHtml(html)

    # ── Periodic tick: uptime + budget ──
    def _tick(self) -> None:
        ctrl = self.controller
        if ctrl and ctrl.running:
            secs = int(time.time() - ctrl.started_at)
            self.uptime_label.setText(f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}")
            if ctrl.budget:
                snap = ctrl.budget.snapshot()
                mx = snap["max_sessions"] or 1
                self.progress.setMaximum(mx)
                self.progress.setValue(snap["completed"])
                self.progress.setFormat(f"{snap['completed']} / {mx} kunjungan")
                self.total_lbl.setText(f"Total  {snap['completed']}")
                self.pass_lbl.setText(f"Lolos  {snap['passed']}")
                self.warn_lbl.setText(f"Waspada  {snap['warned']}")
                self.fail_lbl.setText(f"Gagal  {snap['failed']}")


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def launch_adsterra_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette as a robust base under the stylesheet.
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
        # Ctrl+C in the terminal: ask any running worker to stop, then exit
        # quietly instead of printing a raw traceback.
        ctrl = getattr(win, "controller", None)
        if ctrl is not None and ctrl.running:
            ctrl.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(launch_adsterra_gui())
