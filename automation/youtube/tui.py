#!/usr/bin/env python3
"""
YouTube Organic Retention & Ad Viewer Suite — Terminal UI (TUI) Dashboard
Dibangun menggunakan Python Rich Live Dashboard (In-Place Terminal Rendering).
Tidak menghasilkan spam baris baru, tampilan fixed seperti htop / dashboard modern.
"""

import os
import sys
import time
import json
import random
import signal
import threading
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional
from collections import deque

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.live import Live
from rich import box
from rich.align import Align

# Import engine logic dari bot.py
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from bot import (
    load_config,
    load_proxies,
    UniqueProxyPool,
    worker_loop,
    get_country_badge,
    CONFIG_PATH,
    PROXIES_PATH
)


class TUIManager:
    """Manajer State & Tampilan Terminal UI Dashboard."""

    def __init__(self, concurrency: int, total_proxies: int, config: dict):
        self.concurrency = concurrency
        self.total_initial_proxies = total_proxies
        self.config = config
        self.console = Console()
        self.lock = threading.RLock()
        self.is_stopping = False

        # State Worker
        self.workers: Dict[int, Dict[str, Any]] = {}
        for w_id in range(1, concurrency + 1):
            self.workers[w_id] = {
                "status": "Inisialisasi...",
                "status_style": "dim white",
                "ip": "-",
                "country": "-",
                "latency": "-",
                "video": "-",
                "progress_pct": 0.0,
                "time_str": "00:00 / 00:00",
                "ad_status": "Clean",
                "ad_style": "dim",
                "ads_skipped_count": 0,
                "proxy_idx": -1,
            }

        # KPI Counter
        self.stat_views_completed = 0
        self.stat_ads_skipped = 0
        self.proxy_used = 0
        self.proxy_failed = 0
        self.proxy_remaining = total_proxies

        # Log Activity (Antrean riwayat 8 pesan terakhir)
        self.recent_logs: deque = deque(maxlen=7)
        self.add_log(f"🚀 Sistem TUI diinisialisasi dengan {concurrency} worker.", "green")

        # Proksi Tracker (Menyimpan riwayat status proksi terbaru)
        self.active_proxy_map: Dict[int, int] = {}  # worker_id -> proxy_idx

    def add_log(self, text: str, style: str = "white"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.recent_logs.append((timestamp, text, style))

    def on_event(self, event_type: str, data: dict):
        w_id = data.get("worker_id", 1)
        p_idx = data.get("proxy_idx", -1)

        with self.lock:
            if w_id not in self.workers:
                return

            w = self.workers[w_id]

            if event_type == "status_update":
                st = data.get("status", "")
                w["status"] = st
                if "Mencari" in st:
                    w["status_style"] = "bold yellow"
                    self.add_log(f"[W{w_id}] 🔎 {st}", "yellow")
                elif "Browser" in st:
                    w["status_style"] = "cyan"
                    self.add_log(f"[W{w_id}] 🌐 {st}", "cyan")
                elif "Cooldown" in st:
                    w["status_style"] = "dim cyan"
                    self.add_log(f"[W{w_id}] 💤 {st}", "dim cyan")
                elif "Error" in st:
                    w["status_style"] = "bold red"
                    self.add_log(f"[W{w_id}] ⚠️ {st}", "red")
                else:
                    w["status_style"] = "cyan"

            elif event_type == "proxy_testing":
                host = data.get("host", "")
                port = data.get("port", "")
                country = data.get("country", "")
                w["status"] = "Menguji Proksi..."
                w["status_style"] = "bold yellow"
                w["ip"] = f"{host}:{port}"
                w["country"] = country
                w["latency"] = "..."
                self.add_log(f"[W{w_id}] Menguji proksi {host}:{port} ({country})", "yellow")

            elif event_type == "proxy_assigned":
                exit_ip = data.get("exit_ip", "")
                country = data.get("country", "")
                lat = data.get("latency", 0)
                w["status"] = "Proksi Aktif"
                w["status_style"] = "bold green"
                w["ip"] = exit_ip or f"{data.get('host')}:{data.get('port')}"
                w["country"] = country
                w["latency"] = f"{lat}ms"
                w["proxy_idx"] = p_idx
                self.active_proxy_map[w_id] = p_idx
                self.add_log(f"[W{w_id}] Proksi lolos: {w['ip']} ({country} • {lat}ms)", "green")

            elif event_type == "proxy_failed":
                w["status"] = "Proksi Gagal (Mati)"
                w["status_style"] = "bold red"
                self.proxy_failed += 1
                self.add_log(f"[W{w_id}] ❌ Proksi gagal merespons, dibuang dari pool.", "red")

            elif event_type == "video_picked":
                title = data.get("title", "")
                w["video"] = title
                w["status"] = "Menonton"
                w["status_style"] = "bold green"
                self.add_log(f"[W{w_id}] 🎬 Menemukan video: {title[:40]}...", "bold cyan")

            elif event_type == "playback_progress":
                pct = data.get("percent", 0.0)
                cur_s = data.get("formatted_current", "00:00")
                tgt_s = data.get("formatted_target", "00:00")
                w["progress_pct"] = pct
                w["time_str"] = f"{cur_s} / {tgt_s}"

            elif event_type == "ad_event":
                status = data.get("status", "")
                action = data.get("action", "clean")
                if action == "skipped":
                    w["ads_skipped_count"] += 1
                    w["ad_status"] = f"⏩ Skip ({w['ads_skipped_count']})"
                    w["ad_style"] = "bold green"
                    self.stat_ads_skipped += 1
                    self.add_log(f"[W{w_id}] ⏩ Berhasil skip iklan YouTube!", "bold green")
                elif action == "playing":
                    w["ad_status"] = "🎬 Iklan Aktif"
                    w["ad_style"] = "bold yellow"
                else:
                    w["ad_status"] = "Clean"
                    w["ad_style"] = "dim"

            elif event_type == "session_finished":
                success = data.get("success", False)
                if success:
                    self.stat_views_completed += 1
                    w["status"] = "Idle (Selesai)"
                    w["status_style"] = "bold green"
                    self.add_log(f"[W{w_id}] [✓] Selesai 1 tontonan organik penuh!", "bold green")
                else:
                    w["status"] = "Idle"
                    w["status_style"] = "dim"
                    self.add_log(f"[W{w_id}] Sesi berakhir, pendinginan...", "dim")

                # Proksi selesai dipakai -> Idle
                if w_id in self.active_proxy_map:
                    del self.active_proxy_map[w_id]

    def render_header(self) -> Panel:
        """Membuat panel Header ringkas & keren."""
        target_ch = self.config.get("target_channel", "horrornologi")
        search_kw = self.config.get("search_keyword", "horrornologi")
        headless_mode = "Headless (Background)" if self.config.get("headless", True) else "GUI Window"

        t = Text()
        t.append("🎬 YOUTUBE ORGANIC VIEW ENGINE & AD VIEWER SUITE", style="bold red")
        t.append("  |  ", style="dim")
        t.append(f"Target: @{target_ch}", style="bold white")
        t.append("  |  ", style="dim")
        t.append(f"Search: '{search_kw}'", style="yellow")
        t.append("  |  ", style="dim")
        t.append(f"Mode: {headless_mode}", style="cyan")
        t.append("  |  ", style="dim")
        t.append("Resolusi: 144p Ultra-Lite", style="green")

        return Panel(Align.center(t), box=box.ROUNDED, style="bright_blue", padding=(0, 1))

    def render_kpi(self) -> Table:
        """Membuat panel statistik ringkas."""
        t = Table.grid(expand=True)
        t.add_column(justify="center", ratio=1)
        t.add_column(justify="center", ratio=1)
        t.add_column(justify="center", ratio=1)
        t.add_column(justify="center", ratio=1)

        p_views = Panel(
            Align.center(f"[bold green]{self.stat_views_completed}[/]\n[dim]Views Berhasil[/]"),
            box=box.ROUNDED, style="green"
        )
        p_ads = Panel(
            Align.center(f"[bold yellow]{self.stat_ads_skipped}[/]\n[dim]Iklan Diskip[/]"),
            box=box.ROUNDED, style="yellow"
        )
        p_workers = Panel(
            Align.center(f"[bold cyan]{self.concurrency}[/] [dim]Aktif[/]\n[dim]Worker Concurrency[/]"),
            box=box.ROUNDED, style="cyan"
        )
        p_proxies = Panel(
            Align.center(f"[bold magenta]{self.total_initial_proxies}[/] [dim]Total[/]\n[dim]Residential Pool[/]"),
            box=box.ROUNDED, style="magenta"
        )

        t.add_row(p_views, p_ads, p_workers, p_proxies)
        return t

    def _render_progress_bar(self, pct: float, width: int = 12) -> str:
        pct = max(0.0, min(100.0, pct))
        filled = int((pct / 100.0) * width)
        empty = width - filled
        return f"[bold green]{'█' * filled}[/][dim white]{'░' * empty}[/]"

    def render_workers_table(self) -> Table:
        """Tabel live status setiap worker."""
        tbl = Table(box=box.ROUNDED, expand=True, header_style="bold bright_white")
        tbl.add_column("#", justify="center", width=5, style="bold cyan")
        tbl.add_column("Status Worker", justify="left", width=18)
        tbl.add_column("Exit IP Publik", justify="left", width=18)
        tbl.add_column("Negara", justify="left", width=15)
        tbl.add_column("Latency", justify="right", width=9)
        tbl.add_column("Target Video", justify="left", ratio=3)
        tbl.add_column("Progress Nonton", justify="left", width=26)
        tbl.add_column("Iklan (Ads)", justify="center", width=14)

        for w_id in range(1, self.concurrency + 1):
            w = self.workers[w_id]
            st_text = Text(w["status"], style=w["status_style"])
            ip_text = Text(w["ip"], style="bold green" if w["ip"] != "-" else "dim")
            country_badge = get_country_badge(w["country"]) if w["country"] != "-" else "-"
            lat_text = Text(w["latency"], style="cyan" if w["latency"] != "..." else "yellow")
            
            # Potong judul video jika kepanjangan
            raw_v = w["video"]
            disp_v = (raw_v[:36] + "...") if len(raw_v) > 36 else raw_v
            vid_text = Text(disp_v, style="white" if raw_v != "-" else "dim")

            # Bar progress
            bar = self._render_progress_bar(w["progress_pct"])
            prog_text = f"{bar} {w['time_str']}"

            # Status iklan
            ad_text = Text(w["ad_status"], style=w["ad_style"])

            tbl.add_row(
                f"W{w_id}",
                st_text,
                ip_text,
                country_badge,
                lat_text,
                vid_text,
                prog_text,
                ad_text
            )

        return tbl

    def render_bottom_panels(self) -> Table:
        """Menampilkan log event 7 baris terakhir + tracker info."""
        t = Table.grid(expand=True)
        t.add_column(ratio=2)
        t.add_column(ratio=1)

        # Log table
        log_content = Text()
        if not self.recent_logs:
            log_content.append("Menunggu aktivitas worker...", style="dim")
        else:
            for ts, msg, stl in self.recent_logs:
                log_content.append(f"[{ts}] ", style="dim")
                log_content.append(f"{msg}\n", style=stl)

        log_panel = Panel(
            log_content,
            title="[bold yellow]📡 Live Event Activity Log[/]",
            box=box.ROUNDED,
            style="white"
        )

        # Tracker ringkas
        act_cnt = len(self.active_proxy_map)
        idle_cnt = max(0, self.concurrency - act_cnt)
        info_text = Text()
        info_text.append(f"• Proksi Aktif Digunakan : ", style="dim")
        info_text.append(f"{act_cnt} Worker\n", style="bold green")
        info_text.append(f"• Proksi Selesai (Idle)  : ", style="dim")
        info_text.append(f"{self.stat_views_completed} Selesai\n", style="bold cyan")
        info_text.append(f"• Proksi Gagal/Dibuang   : ", style="dim")
        info_text.append(f"{self.proxy_failed} Proksi\n", style="bold red" if self.proxy_failed else "dim")
        info_text.append(f"• Single-Use Rotation    : ", style="dim")
        info_text.append("1 Video 1 IP Baru\n", style="bold yellow")
        info_text.append(f"• Browser Engine         : ", style="dim")
        info_text.append("Chromium Anti-Detect", style="green")

        tracker_panel = Panel(
            info_text,
            title="[bold magenta]🛡️ Proksi & Engine[/]",
            box=box.ROUNDED,
            style="magenta"
        )

        t.add_row(log_panel, tracker_panel)
        return t

    def render_footer(self) -> Panel:
        """Footer instruksi."""
        if self.is_stopping:
            t = Text("🛑 Sedang menghentikan seluruh worker dan menutup browser... Mohon tunggu...", style="bold yellow")
        else:
            t = Text()
            t.append("Tekan ", style="dim")
            t.append("[Ctrl + C]", style="bold red")
            t.append(" untuk menghentikan bot secara aman | Dashboard me-refresh in-place secara real-time", style="dim")

        return Panel(Align.center(t), box=box.ROUNDED, style="dim")

    def build_dashboard(self) -> Group:
        """Menggabungkan seluruh komponen menjadi 1 tampilan utuh."""
        return Group(
            self.render_header(),
            self.render_kpi(),
            self.render_workers_table(),
            self.render_bottom_panels(),
            self.render_footer(),
        )


def main():
    parser = argparse.ArgumentParser(description="YouTube Organic View Suite — Full TUI Dashboard")
    parser.add_argument("--search", type=str, default="", help="Kata kunci pencarian YouTube (default: horrornologi)")
    parser.add_argument("--channel", type=str, default="", help="Nama channel target (default: horrornologi)")
    parser.add_argument("--concurrency", "-c", type=int, default=0, help="Jumlah worker bersamaan (default: 5)")
    parser.add_argument("--headless", action="store_true", default=True, help="Mode background headless (default: True)")
    parser.add_argument("--no-headless", action="store_true", help="Tampilkan jendela browser secara fisik")
    parser.add_argument("--no-proxy", action="store_true", help="Gunakan internet langsung tanpa proksi")
    parser.add_argument("--watch-min", type=int, default=0, help="Durasi minimal tonton (detik)")
    parser.add_argument("--watch-max", type=int, default=0, help="Durasi maksimal tonton (detik)")
    args = parser.parse_args()

    cfg = load_config()
    if args.search:
        cfg["search_keyword"] = args.search
    if args.channel:
        cfg["target_channel"] = args.channel
    if args.watch_min > 0:
        cfg["watch_duration"]["min_seconds"] = args.watch_min
    if args.watch_max > 0:
        cfg["watch_duration"]["max_seconds"] = args.watch_max
    if args.no_headless:
        cfg["headless"] = False
    else:
        cfg["headless"] = True

    concurrency = args.concurrency or cfg.get("concurrency", 5)

    proxy_source = cfg.get("proxy_source", str(PROXIES_PATH))
    raw_proxies = []
    if not args.no_proxy:
        raw_proxies = load_proxies(proxy_source)

    proxy_pool = UniqueProxyPool(raw_proxies)
    tui = TUIManager(concurrency=concurrency, total_proxies=len(raw_proxies), config=cfg)

    stop_event = threading.Event()

    def handle_sigint(sig, frame):
        tui.is_stopping = True
        tui.add_log("🛑 Sinyal Ctrl+C diterima. Menghentikan bot...", "bold red")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    # Thread executor untuk menjalankan worker bot di latar belakang
    executor = ThreadPoolExecutor(max_workers=concurrency)
    futures = [
        executor.submit(
            worker_loop,
            w_id,
            proxy_pool,
            cfg,
            stop_event,
            concurrency,
            tui.on_event
        )
        for w_id in range(1, concurrency + 1)
    ]

    console = Console()
    try:
        # Jalankan Rich Live rendering loop (In-Place, Fixed Screen)
        with Live(tui.build_dashboard(), console=console, refresh_per_second=4, screen=True) as live:
            while not stop_event.is_set():
                live.update(tui.build_dashboard())
                time.sleep(0.25)

                # Cek jika semua worker sudah selesai
                if all(f.done() for f in futures):
                    break

            # Sesi berhenti, beri waktu update terakhir
            live.update(tui.build_dashboard())
            time.sleep(1.0)

    except Exception:
        stop_event.set()
    finally:
        tui.is_stopping = True
        stop_event.set()
        executor.shutdown(wait=True, cancel_futures=True)

        # Cetak rekap bersih di terminal setelah screen ditutup
        used, failed, remaining = proxy_pool.get_stats()
        console.print("\n[bold green]=======================================================[/]")
        console.print("  [bold red]🎬 YOUTUBE ORGANIC VIEW ENGINE SELESAI[/]")
        console.print(f"  • Total Views Selesai Ditonton : [bold green]{tui.stat_views_completed}[/]")
        console.print(f"  • Total Iklan Berhasil Diskip  : [bold yellow]{tui.stat_ads_skipped}[/]")
        console.print(f"  • Proksi Berhasil Digunakan    : [bold cyan]{used}[/]")
        console.print(f"  • Proksi Gagal Dibuang         : [bold red]{failed}[/]")
        console.print(f"  • Sisa Proksi Belum Terpakai   : [bold magenta]{remaining}[/]")
        console.print("[bold green]=======================================================[/]\n")


if __name__ == "__main__":
    main()
