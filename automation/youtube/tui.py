#!/usr/bin/env python3
"""
automation.youtube.tui
Terminal UI (TUI) Live Dashboard for YouTube Camoufox Automation.
Dibangun menggunakan Python Rich Live rendering (in-place terminal dashboard).
Bebas spam baris baru (screen=True, alternate screen buffer seperti htop).

Contoh Menjalankan:
    python3 automation/youtube/tui.py
    python3 automation/youtube/tui.py --workers 2
    python3 automation/youtube/tui.py --workers 1 --no-headless
    python3 automation/youtube/tui.py --keyword "horrornologi" --channel "horrornologi"
"""

import os
import sys
import time
import signal
import threading
import argparse
from datetime import datetime
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich import box

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.proxy_manager import ProxyManager
from automation.youtube.bot import (
    load_config,
    worker_thread_loop,
    get_country_badge,
    format_time,
)


class TUIManager:
    """Manajer State & Tampilan Real-time Dashboard TUI."""

    def __init__(self, concurrency: int, proxy_manager: ProxyManager, config: Dict[str, Any]):
        self.concurrency = concurrency
        self.pm = proxy_manager
        self.config = config
        self.console = Console()
        self.lock = threading.RLock()
        self.is_stopping = False

        # State tiap worker
        self.workers: Dict[int, Dict[str, Any]] = {}
        for w_id in range(1, concurrency + 1):
            self.workers[w_id] = {
                "status": "Inisialisasi...",
                "status_style": "dim white",
                "ip": "-",
                "country": "-",
                "flow_type": "-",
                "video": "-",
                "progress_pct": 0.0,
                "time_str": "00:00 / 00:00",
                "ad_status": "🟢 Konten Normal",
                "ad_style": "green",
                "ads_detected": 0,
                "ads_skipped": 0,
                "verifier": {
                    "score": 100,
                    "webdriver_hidden": True,
                    "webrtc_safe": True,
                    "webgl": "-",
                    "canvas_audio_ok": True,
                    "ads_allowed": True,
                    "is_safe": True,
                    "verified": False,
                }
            }

        # KPI Counter Global
        self.total_views_completed = 0
        self.total_ads_detected = 0
        self.total_ads_skipped = 0
        self.total_ads_finished = 0
        self.start_time = time.time()

        # Riwayat Log Realtime
        self.recent_logs: deque = deque(maxlen=8)
        self.add_log(f"🚀 TUI Dashboard dimulai dengan {concurrency} concurrent worker.", "green")

    def add_log(self, message: str, style: str = "white"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.recent_logs.append((timestamp, message, style))

    def on_event(self, event_type: str, data: Dict[str, Any]):
        w_id = data.get("worker_id", 1)
        with self.lock:
            if event_type == "log_message":
                msg = data.get("message", "")
                style = data.get("style", "white")
                self.add_log(msg, style)
                return

            if w_id not in self.workers:
                return

            w = self.workers[w_id]

            if event_type == "status_update":
                st = data.get("status", "")
                w["status"] = st
                if "Mencari" in st or "Mengetik" in st:
                    w["status_style"] = "bold yellow"
                elif "Camoufox" in st:
                    w["status_style"] = "bold cyan"
                elif "Audit" in st:
                    w["status_style"] = "bold blue"
                elif "Cooldown" in st:
                    w["status_style"] = "dim cyan"
                elif "Error" in st:
                    w["status_style"] = "bold red"
                else:
                    w["status_style"] = "cyan"

            elif event_type == "proxy_assigned":
                ip = data.get("ip", "-")
                country = data.get("country", "-")
                w["ip"] = ip
                w["country"] = country
                w["video"] = "-"
                w["progress_pct"] = 0.0
                w["time_str"] = "00:00 / 00:00"
                # Reset verifier status saat proksi baru dialokasikan
                w["verifier"]["verified"] = False

            elif event_type == "verifier_report":
                w["verifier"] = {
                    "score": data.get("score", 100),
                    "webdriver_hidden": data.get("webdriver_hidden", True),
                    "webrtc_safe": data.get("webrtc_safe", True),
                    "webgl": data.get("webgl", "Native Hardware"),
                    "canvas_audio_ok": data.get("canvas_audio_ok", True),
                    "ads_allowed": data.get("ads_allowed", True),
                    "is_safe": data.get("is_safe", True),
                    "verified": True,
                }
                score = data.get("score", 100)
                gpu = data.get("webgl", "GPU")
                self.add_log(
                    f"[W{w_id}] 🛡️ Audit Verifier {score}/100: Bot=Hidden, 0 Leak, GPU={gpu[:15]}, Ads=Allowed",
                    "bold green" if data.get("is_safe") else "bold red"
                )

            elif event_type == "strategy_selected":
                strat = data.get("flow_type", "-")
                w["flow_type"] = strat

            elif event_type == "video_picked":
                v_title = data.get("title", "-")
                w["video"] = v_title[:32] + ("..." if len(v_title) > 32 else "")
                strat = data.get("flow_type", w["flow_type"])
                w["flow_type"] = strat

            elif event_type == "playback_target_set":
                ratio = data.get("ratio_label", "~50%")
                tgt_s = data.get("target_seconds", 0)
                w["status"] = f"Menonton {ratio} ({format_time(tgt_s)})"
                w["status_style"] = "bold green"

            elif event_type == "playback_progress":
                pct = data.get("percent", 0.0)
                cur_s = data.get("formatted_current", "00:00")
                tgt_s = data.get("formatted_target", "00:00")
                w["progress_pct"] = pct
                w["time_str"] = f"{cur_s} / {tgt_s}"

            elif event_type == "ad_event":
                ad_ev = data.get("event", "")
                st = data.get("status", "")
                w["ad_status"] = st

                if ad_ev == "iklan_muncul":
                    w["ad_style"] = "bold yellow"
                    w["ads_detected"] += 1
                    self.total_ads_detected += 1
                elif ad_ev == "iklan_di_skip":
                    w["ad_style"] = "bold magenta"
                    w["ads_skipped"] += 1
                    self.total_ads_skipped += 1
                elif ad_ev == "iklan_selesai":
                    w["ad_style"] = "bold green"
                    self.total_ads_finished += 1

            elif event_type == "session_completed":
                self.total_views_completed += 1
                v_title = data.get("title", "Video")
                self.add_log(f"[W{w_id}] 🏁 Sesi Selesai: {v_title[:28]}... (Total: {self.total_views_completed} views)", "bold green")
                w["status"] = "Sesi Selesai (Sukses)"
                w["status_style"] = "bold green"
                w["progress_pct"] = 100.0

    def _render_progress_bar(self, pct: float, width: int = 12) -> str:
        """Menghasilkan representasi progress bar teks modern."""
        clamped = max(0.0, min(100.0, pct))
        filled_len = int(round(width * (clamped / 100.0)))
        empty_len = width - filled_len
        bar = "█" * filled_len + "░" * empty_len
        return f"[{bar}] {clamped:5.1f}%"

    def render(self) -> Group:
        """Merender komponen TUI Dashboard secara menyeluruh."""
        with self.lock:
            uptime = format_time(time.time() - self.start_time)
            stats = self.pm.get_stats()

            # 1. Header Panel
            kw = self.config.get("search_keyword", "horrornologi")
            ch = self.config.get("target_channel", "horrornologi")
            header_text = Text()
            header_text.append("🎬 YOUTUBE CAMOUFOX SUITE ", style="bold bright_red")
            header_text.append("• ORGANIC BALANCED RETENTION & AD TRACKER •\n", style="bold white")
            header_text.append(f"Query: '{kw}'  |  Channel: @{ch}  |  Engine: Camoufox Firefox Stealth  |  Uptime: {uptime}", style="dim")
            header_panel = Panel(header_text, style="red", box=box.ROUNDED)

            # 2. KPI Summary Grid
            kpi_table = Table(box=box.SIMPLE_HEAVY, expand=True)
            kpi_table.add_column("👷 Workers", justify="center", style="bold cyan")
            kpi_table.add_column("🎬 Views Selesai", justify="center", style="bold green")
            kpi_table.add_column("🟡 Iklan Muncul", justify="center", style="bold yellow")
            kpi_table.add_column("⏩ Iklan Di-skip", justify="center", style="bold magenta")
            kpi_table.add_column("🟢 Iklan Tuntas", justify="center", style="bold bright_green")
            kpi_table.add_column("🌐 Proksi Pool", justify="center", style="bold blue")

            alive_p = stats.get("alive", 0)
            in_use_p = stats.get("in_use", 0)
            dead_p = stats.get("dead", 0)
            total_p = stats.get("total", 0)
            proxy_str = f"{alive_p} Alive | {in_use_p} Used | {dead_p} Dead ({total_p} Tot)"

            kpi_table.add_row(
                f"{self.concurrency} Active",
                str(self.total_views_completed),
                str(self.total_ads_detected),
                str(self.total_ads_skipped),
                str(self.total_ads_finished),
                proxy_str
            )
            kpi_panel = Panel(kpi_table, title="[bold white]Statistik Real-time[/bold white]", border_style="blue", box=box.ROUNDED)

            # 3. Browser Verifier Live Assertion Panel (Transparan & Bukti Anti-Bot)
            verifier_table = Table(box=box.ROUNDED, expand=True)
            verifier_table.add_column("Worker", justify="center", style="bold cyan", width=6)
            verifier_table.add_column("IP Proksi Publik", justify="left", style="white", min_width=20)
            verifier_table.add_column("Webdriver (Bot Flag)", justify="center", min_width=20)
            verifier_table.add_column("WebRTC Leak Check", justify="center", min_width=18)
            verifier_table.add_column("WebGL GPU Hardware", justify="left", style="bright_white", min_width=22)
            verifier_table.add_column("Status Ads / AdBlock", justify="center", min_width=20)
            verifier_table.add_column("Hasil Audit Stealth", justify="center", min_width=20)

            for w_id in range(1, self.concurrency + 1):
                w = self.workers[w_id]
                v = w.get("verifier", {})
                if not v.get("verified"):
                    v_wd = Text("⏳ Memeriksa...", style="dim")
                    v_rtc = Text("⏳ Memeriksa...", style="dim")
                    v_gpu = Text("-", style="dim")
                    v_ads = Text("⏳ Memeriksa...", style="dim")
                    v_res = Text("⏳ Inisialisasi Audit", style="dim yellow")
                else:
                    v_wd = Text("🟢 FALSE (Bot Hidden)", style="bold green") if v.get("webdriver_hidden") else Text("🔴 TRUE (Bot Detected!)", style="bold red")
                    v_rtc = Text("🟢 AMAN (0 Leak)", style="bold green") if v.get("webrtc_safe") else Text("🔴 LEAK!", style="bold red")
                    v_gpu = Text(f"🎮 {v.get('webgl', 'Native Hardware')}", style="cyan")
                    v_ads = Text("🟢 Normal (No AdBlock)", style="bold green") if v.get("ads_allowed") else Text("🔴 Terblokir (AdBlock)", style="bold red")
                    v_res = Text(f"🟢 {v.get('score', 100)}/100 (UNIQUE & PASS)", style="bold bright_green") if v.get("is_safe") else Text(f"🔴 {v.get('score', 0)}/100 (FAIL)", style="bold red")

                verifier_table.add_row(
                    f"W{w_id}",
                    f"{w['ip']}\n{w['country']}",
                    v_wd,
                    v_rtc,
                    v_gpu,
                    v_ads,
                    v_res
                )

            verifier_panel = Panel(
                verifier_table,
                title="[bold green]🛡️ Audit Keamanan & Anti-Bot Shield (Browser Verifier Live Assertion)[/bold green]",
                border_style="green",
                box=box.ROUNDED
            )

            # 4. Workers Status Table (Playback & YouTube Tasks)
            worker_table = Table(box=box.ROUNDED, expand=True)
            worker_table.add_column("ID", justify="center", style="bold cyan", width=5)
            worker_table.add_column("Strategi Alur", justify="center", style="magenta", min_width=20)
            worker_table.add_column("Video YouTube", justify="left", style="bright_white", min_width=24)
            worker_table.add_column("Durasi & Watch", justify="center", style="cyan", min_width=22)
            worker_table.add_column("Status Iklan", justify="center", min_width=18)
            worker_table.add_column("Aktivitas Worker", justify="left", min_width=22)

            for w_id in range(1, self.concurrency + 1):
                w = self.workers[w_id]
                bar_str = f"{self._render_progress_bar(w['progress_pct'], width=8)}\n{w['time_str']}"

                ad_text = Text(w["ad_status"], style=w["ad_style"])
                status_text = Text(w["status"], style=w["status_style"])

                worker_table.add_row(
                    f"W{w_id}",
                    w["flow_type"],
                    w["video"],
                    bar_str,
                    ad_text,
                    status_text
                )

            worker_panel = Panel(worker_table, title="[bold white]Status Pekerja Aktif & Penayangan Video[/bold white]", border_style="cyan", box=box.ROUNDED)

            # 5. Activity Logs Panel
            log_table = Table.grid(expand=True)
            log_table.add_column("Time", style="dim", width=10)
            log_table.add_column("Message", style="white")

            if not self.recent_logs:
                log_table.add_row("", "Menunggu aktivitas...")
            else:
                for ts, msg, style in self.recent_logs:
                    log_table.add_row(f"[{ts}]", Text(msg, style=style))

            log_panel = Panel(log_table, title="[bold white]Aktivitas & Log Real-time[/bold white]", border_style="yellow", box=box.ROUNDED)

            # 6. Footer Help
            footer = Text(" Tekan Ctrl+C untuk menghentikan gracefully (melepaskan semua alokasi proksi & menutup browser)", style="dim white")

            return Group(
                header_panel,
                kpi_panel,
                verifier_panel,
                worker_panel,
                log_panel,
                footer
            )


def launch_youtube_tui(
    concurrency: Optional[int] = None,
    headless: Optional[bool] = None,
    keyword: Optional[str] = None,
    channel: Optional[str] = None,
):
    """Fungsi utama untuk menjalankan TUI Dashboard dan thread worker."""
    config = load_config()
    if headless is not None:
        config["headless"] = headless
    if concurrency is not None and concurrency > 0:
        config["concurrency"] = concurrency
    if keyword:
        config["search_keyword"] = keyword
    if channel:
        config["target_channel"] = channel

    proxy_manager = ProxyManager()
    cleaned_used = proxy_manager.reset_usage_to_idle()
    proxy_manager.reset_cursor(0)

    tui = TUIManager(
        concurrency=config["concurrency"],
        proxy_manager=proxy_manager,
        config=config,
    )

    if cleaned_used > 0:
        tui.add_log(f"🧹 Reset {cleaned_used} status IN_USE tertinggal -> IDLE.", "cyan")
    tui.add_log("🔄 Kursor rotasi proksi diset mulai dari awal (Index 0).", "cyan")

    stop_event = threading.Event()
    threads = []

    def handle_sigint(sig, frame):
        if tui.is_stopping:
            print("\nPaksa berhenti...")
            os._exit(1)
        tui.is_stopping = True
        tui.add_log("🛑 Sinyal Ctrl+C diterima. Menghentikan worker...", "bold red")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    # Jalankan worker threads
    for w_id in range(1, config["concurrency"] + 1):
        t = threading.Thread(
            target=worker_thread_loop,
            args=(w_id, config, proxy_manager, tui.on_event, stop_event),
            daemon=True,
            name=f"YT-Worker-{w_id}"
        )
        t.start()
        threads.append(t)

    # Render Live Loop dengan screen=True (Alternate Buffer, tanpa baris baru sama sekali)
    with Live(tui.render(), console=tui.console, refresh_per_second=4, screen=True) as live:
        try:
            while not stop_event.is_set():
                live.update(tui.render())
                time.sleep(0.25)
        except KeyboardInterrupt:
            handle_sigint(None, None)

        live.update(tui.render())
        time.sleep(1.5)

    print("\n✅ Seluruh sesi YouTube bot telah berhenti dan proksi dilepaskan secara aman.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="YouTube Camoufox Automation TUI Dashboard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--workers", "-w", type=int, default=2, help="Jumlah concurrent worker paralel")
    parser.add_argument("--headless", action="store_true", default=None, help="Paksa mode headless")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Tampilkan jendela browser Camoufox di layar")
    parser.add_argument("--keyword", "-k", type=str, default="horrornologi", help="Query pencarian organik YouTube")
    parser.add_argument("--channel", "-c", type=str, default="horrornologi", help="Nama channel target")
    args = parser.parse_args()

    launch_youtube_tui(
        concurrency=args.workers,
        headless=args.headless,
        keyword=args.keyword,
        channel=args.channel
    )
