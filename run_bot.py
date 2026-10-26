#!/usr/bin/env python3
"""Unified Terminal CLI Entrypoint for Bot Shortlink (Adsterra & Monetag).

Menjalankan bot langsung dari terminal:
- Mendukung mode Adsterra, Monetag, atau Hybrid.
- Terhubung otomatis ke Supabase Realtime Telemetry WebSocket (0 byte di database Supabase).
- Data statistik performa otomatis dicatat di file JSON lokal data/local_node_stats.json.
- Bisa dipantau secara langsung lewat browser di http://localhost:3000/monitoring!

Contoh pemakaian:
  python3 run_bot.py --target adsterra --workers 1 --unlimited
  python3 run_bot.py --target monetag --workers 2 --unlimited
  python3 run_bot.py --target adsterra --no-headless
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

# Pastikan output terminal langsung keluar dan tidak dibuffer di background tmux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.proxy_manager import ProxyManager
from core.telemetry_reporter import get_telemetry_reporter
from automation.adsterra.qa import SessionBudget, load_config
from automation.adsterra.flow_qa import flow_worker_thread_loop
from automation.monetag.flow import run_monetag_session

# ANSI Color codes untuk terminal modern
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"
BLUE = "\033[34m"


def print_banner(node_name: str, target: str, workers: int, unlimited: bool, headless: bool, url: str) -> None:
    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════════════════════════════╗{RESET}", flush=True)
    print(f"{BOLD}{CYAN}║     🚀 BOT SHORTLINK RUNNER - DISTRIBUTED CLI TERMINAL            ║{RESET}", flush=True)
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════════════════════╝{RESET}", flush=True)
    print(f"  {BOLD}Node ID / Name :{RESET} {GREEN}{node_name}{RESET}", flush=True)
    print(f"  {BOLD}Target Network :{RESET} {MAGENTA if 'monetag' in target else YELLOW}{target.upper()}{RESET}", flush=True)
    print(f"  {BOLD}Concurrent     :{RESET} {CYAN}{workers} Browser Worker{RESET}", flush=True)
    print(f"  {BOLD}Mode Kuota     :{RESET} {GREEN}Tanpa Batas (∞ Looping Continuous){RESET}" if unlimited else f"  {BOLD}Mode Kuota     :{RESET} Terbatas", flush=True)
    print(f"  {BOLD}Headless       :{RESET} {'🟢 Aktif (Tanpa Layar)' if headless else '🖥️ Non-Headless (Layar Terlihat)'}", flush=True)
    print(f"  {BOLD}Target URL     :{RESET} {BLUE}{url}{RESET}", flush=True)
    print(f"  {BOLD}Live Monitor   :{RESET} {BOLD}{GREEN}https://article.riztama.my.id/monitoring{RESET}", flush=True)
    print(f"{DIM}───────────────────────────────────────────────────────────────────{RESET}\n", flush=True)


def monetag_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Any] = None,
    stop_event: Optional[threading.Event] = None,
    reset_pool_callback: Optional[Any] = None,
) -> None:
    """Worker loop untuk Monetag Automation."""
    target_name = "monetag"
    max_u = int(config.get("max_uses_per_day", 2))
    cd_h = float(config.get("proxy_cooldown_hours", 6.0))

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break

        caller_id = f"cli_monetag_w{worker_id}_{int(time.time() * 1000)}"
        proxy = proxy_manager.acquire_proxy(
            caller_id=caller_id,
            exclusive=True,
            verify_alive=False,
            target=target_name,
            max_uses_per_day=max_u,
            cooldown_seconds=cd_h * 3600,
        )

        if not proxy:
            if budget.unlimited and reset_pool_callback:
                reset_pool_callback()
                time.sleep(2.0)
                continue
            time.sleep(3.0)
            continue

        ip = proxy.get("ip_detected") or proxy.get("host", "?")
        if event_callback:
            event_callback("proxy_assigned", {
                "worker_id": worker_id,
                "ip": ip,
                "country": proxy.get("country", "Unknown"),
                "target_network": "💎 Monetag",
            })
            event_callback("session_started", {"worker_id": worker_id})

        try:
            res = run_monetag_session(worker_id=worker_id, proxy_data=proxy, config=config)
            proxy_manager.record_target_hit(proxy, target=target_name)
            proxy_manager.mark_proxy_success(proxy)
            budget.record_session(proxy.get("id", ip), True)

            if event_callback:
                event_callback("session_completed", {
                    "worker_id": worker_id,
                    "status": "PASS",
                    "details": res,
                })
        except Exception as err:
            proxy_manager.mark_proxy_failure(proxy, error=str(err))
            budget.record_session(proxy.get("id", ip), False)
            if event_callback:
                event_callback("session_completed", {
                    "worker_id": worker_id,
                    "status": "FAIL",
                    "error": str(err),
                })

        time.sleep(2.0)


def get_country_flag(country: Optional[str]) -> str:
    if not country or country == "Unknown":
        return "🌐"
    mapping = {
        "united states": "🇺🇸", "us": "🇺🇸", "usa": "🇺🇸",
        "canada": "🇨🇦", "ca": "🇨🇦",
        "indonesia": "🇮🇩", "id": "🇮🇩",
        "united kingdom": "🇬🇧", "gb": "🇬🇧", "uk": "🇬🇧",
        "germany": "🇩🇪", "de": "🇩🇪",
        "france": "🇫🇷", "fr": "🇫🇷",
        "netherlands": "🇳🇱", "nl": "🇳🇱",
        "singapore": "🇸🇬", "sg": "🇸🇬",
        "japan": "🇯🇵", "jp": "🇯🇵",
        "australia": "🇦🇺", "au": "🇦🇺",
        "brazil": "🇧🇷", "br": "🇧🇷",
        "india": "🇮🇳", "in": "🇮🇳",
        "russia": "🇷🇺", "ru": "🇷🇺",
        "china": "🇨🇳", "cn": "🇨🇳",
        "vietnam": "🇻🇳", "vn": "🇻🇳",
        "thailand": "🇹🇭", "th": "🇹🇭",
        "malaysia": "🇲🇾", "my": "🇲🇾",
        "philippines": "🇵🇭", "ph": "🇵🇭",
        "spain": "🇪🇸", "es": "🇪🇸",
        "italy": "🇮🇹", "it": "🇮🇹",
        "turkey": "🇹🇷", "tr": "🇹🇷",
        "poland": "🇵🇱", "pl": "🇵🇱",
        "ukraine": "🇺🇦", "ua": "🇺🇦",
    }
    return mapping.get(str(country).lower().strip(), "🏳️")


class BotRunnerCLI:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop_event = threading.Event()
        self.proxy_manager = ProxyManager(reset_stale_usage=True)
        self.proxy_manager.reset_usage_to_idle()
        self.reporter = get_telemetry_reporter()

        if self.args.name:
            self.reporter.set_node_name(self.args.name)

        # Budget session
        max_sess = 0 if self.args.unlimited else self.args.sessions
        self.budget = SessionBudget(max_sess, 1)

        self.workers_state: Dict[int, Dict[str, Any]] = {}
        for wid in range(1, self.args.workers + 1):
            t_net = "💎 Monetag" if self.args.target == "monetag" else "⚡ Adsterra"
            if self.args.target == "both":
                t_net = "💎 Monetag" if wid % 2 == 1 else "⚡ Adsterra"
            self.workers_state[wid] = {
                "worker_id": wid,
                "target_net": t_net,
                "proxy_ip": "—",
                "country": "—",
                "country_flag": "🌐",
                "stepper": "⏳ Memulai",
                "activity": "Menyiapkan worker...",
                "vscore": "—",
                "bot": "Aman",
                "webrtc": "Aman",
                "ads": "OK",
                "status": "SIAP",
                "sessions_done": 0,
                "logs": [],
            }

        self.started_at = time.time()
        self.threads: List[threading.Thread] = []

    def _on_worker_event(self, etype: str, data: Dict[str, Any]) -> None:
        wid = data.get("worker_id", 1)
        w = self.workers_state.setdefault(wid, {"worker_id": wid})
        ts = datetime.now().strftime("%H:%M:%S")

        # Riwayat aktivitas log real-time per worker (ring buffer 15 baris)
        logs = w.setdefault("logs", [])

        if etype == "log_message":
            msg = data.get("message", "")
            if msg:
                logs.append(f"[{ts}] {msg}")
                w["logs"] = logs[-15:]
                w["activity"] = msg[:75]

        elif etype == "proxy_assigned":
            c_name = data.get("country", "Unknown")
            c_flag = get_country_flag(c_name)
            w["proxy_ip"] = data.get("ip", "—")
            w["country"] = c_name
            w["country_flag"] = c_flag
            t_net = data.get("target_network")
            if t_net:
                w["target_net"] = t_net
            w["stepper"] = "🛡️ Alokasi IP"
            w["activity"] = f"IP terpilih: {w['proxy_ip']} ({c_flag} {c_name})"
            logs.append(f"[{ts}] 🛡️ IP Dialokasikan: {w['proxy_ip']} ({c_flag} {c_name})")
            w["logs"] = logs[-15:]
            print(f"[{ts}] {CYAN}[W{wid}]{RESET} 🛡️ IP Dialokasikan: {BOLD}{w['proxy_ip']}{RESET} ({c_flag} {c_name}) - {w['target_net']}", flush=True)

        elif etype == "verifier_report":
            w["out_ip"] = data.get("detected_ip") or w["proxy_ip"]
            c_name = data.get("detected_country") or w.get("country")
            w["country"] = c_name
            w["country_flag"] = get_country_flag(c_name)
            score = data.get("score", 0)
            w["vscore"] = str(score)
            w["bot"] = "Bot!" if data.get("bot_detected") else "Aman"
            w["webrtc"] = "Bocor" if data.get("webrtc_leak") else "Aman"
            w["ads"] = "Blokir" if (data.get("adblock_detected") or not data.get("ads_allowed", True)) else "OK"
            w["user_agent"] = data.get("user_agent", "—")
            w["activity"] = f"Audit anti-detect: {score}/100 (Bot: {w['bot']}, WebRTC: {w['webrtc']})"
            logs.append(f"[{ts}] 🔍 Hasil Audit Stealth: {score}/100 | Bot Flag: {w['bot']} | WebRTC: {w['webrtc']}")
            w["logs"] = logs[-15:]
            score_col = GREEN if score >= 80 else (YELLOW if score >= 60 else RED)
            print(f"[{ts}] {CYAN}[W{wid}]{RESET} 🔍 Audit Anti-Detect: {score_col}{score}/100{RESET} | Bot Flag: {w['bot']} | WebRTC: {w['webrtc']}", flush=True)

        elif etype == "session_started":
            w["stepper"] = "🌐 Buka Web"
            w["activity"] = "Membuka halaman target web shortlink..."
            logs.append(f"[{ts}] 🌐 Membuka target: {self.args.url}")
            w["logs"] = logs[-15:]
            print(f"[{ts}] {CYAN}[W{wid}]{RESET} 🌐 Membuka halaman target: {self.args.url}", flush=True)

        elif etype == "step_waiting":
            step = data.get("index", 1)
            w["stepper"] = f"⏳ Menunggu Step {step}"
            w["activity"] = f"Menunggu elemen step {step} siap di halaman..."
            logs.append(f"[{ts}] ⏳ Menunggu tombol/konten step {step}...")
            w["logs"] = logs[-15:]

        elif etype == "step_countdown_wait":
            step = data.get("step", 1)
            seconds = data.get("seconds", 0)
            w["stepper"] = f"⏳ Step {step} ({seconds}s)"
            w["activity"] = f"Menunggu hitung mundur countdown step {step} ({seconds} detik)..."
            logs.append(f"[{ts}] ⏳ Step {step}: Countdown timer berjalan ({seconds}s)")
            w["logs"] = logs[-15:]

        elif etype == "step_submit_click":
            step = data.get("step", 1)
            w["stepper"] = f"🖱️ Klik Step {step}"
            w["activity"] = f"Mengeklik tombol Lanjut/Open Order step {step}..."
            logs.append(f"[{ts}] 🖱️ Step {step}: Klik tombol Lanjut dengan interaksi humanize")
            w["logs"] = logs[-15:]

        elif etype == "step_completed":
            idx = data.get("index", 1)
            w["stepper"] = f"✅ Step {idx} Selesai"
            w["activity"] = f"Step {idx} berhasil dilewati!"
            logs.append(f"[{ts}] ✅ Step {idx} tuntas, menuju step selanjutnya")
            w["logs"] = logs[-15:]

        elif etype == "banner_click":
            w["stepper"] = "🎯 Klik Banner"
            w["activity"] = f"Interaksi klik banner iklan: {str(data.get('url', ''))[:40]}..."
            logs.append(f"[{ts}] 🎯 Memicu klik humanize pada banner iklan")
            w["logs"] = logs[-15:]

        elif etype == "ad_checked":
            ad_type = data.get("ad_type", "iklan")
            w["stepper"] = f"🎯 {ad_type}"
            w["activity"] = f"Verifikasi & interaksi iklan: {ad_type}..."
            logs.append(f"[{ts}] 🎯 Memverifikasi viewability iklan: {ad_type}")
            w["logs"] = logs[-15:]
            print(f"[{ts}] {CYAN}[W{wid}]{RESET} 🎯 Interaksi iklan: {ad_type}", flush=True)

        elif etype == "flow_completed":
            w["stepper"] = "🏁 Flow Lolos"
            w["activity"] = "Seluruh tahapan shortlink berhasil diselesaikan!"
            logs.append(f"[{ts}] 🏁 Seluruh alur shortlink selesai dengan sukses")
            w["logs"] = logs[-15:]

        elif etype == "session_completed":
            raw = data.get("status", "FAIL")
            label = {"PASS": "LOLOS", "WARN": "WASPADA", "FAIL": "GAGAL"}.get(raw, raw)
            w["status"] = label
            w["stepper"] = f"✅ {label}" if raw == "PASS" else f"❌ {label}"
            w["activity"] = f"Selesai dengan status {label}"
            w["sessions_done"] = w.get("sessions_done", 0) + 1
            logs.append(f"[{ts}] 🏁 Sesi kunjungan selesai dengan hasil {label}")
            w["logs"] = logs[-15:]

            status_col = GREEN if raw == "PASS" else (YELLOW if raw == "WARN" else RED)
            print(f"[{ts}] {CYAN}[W{wid}]{RESET} 🏁 Sesi Selesai: {status_col}{label}{RESET} (Total Sukses: {w['sessions_done']})", flush=True)

            # Catat ke JSON lokal & broadcast
            self.reporter.record_session_result(
                target=w.get("target_net", "Adsterra"),
                passed=(raw == "PASS"),
                score=int(w.get("vscore") or 0) if str(w.get("vscore")).isdigit() else 80,
                bot_detected=(w.get("bot") == "Bot!"),
                proxy_ip=w.get("proxy_ip", "—"),
                country=w.get("country", "—"),
            )

        # Broadcast state langsung ke Supabase Realtime
        self._broadcast_now()

    def _broadcast_now(self) -> None:
        try:
            stats = self.proxy_manager.get_stats()
            uptime_s = int(time.time() - self.started_at)

            # Buat inventaris proxy real-time yang lengkap & transparan
            all_proxies = self.proxy_manager.get_proxies()
            active_ips = {
                w.get("proxy_ip"): f"Worker #{wid} ({w.get('target_net', '—')})"
                for wid, w in self.workers_state.items()
                if w.get("proxy_ip") and w.get("proxy_ip") != "—"
            }

            p_list = []
            for p in all_proxies:  # Kirim seluruh daftar proxy di pool
                ip = p.get("ip_detected") or p.get("host", "?")
                c_name = p.get("country", "Unknown")
                c_flag = get_country_flag(c_name)
                # Proxy HANYA berstatus aktif jika benar-benar sedang dipegang oleh worker yang aktif!
                is_active = bool(ip in active_ips)
                health = p.get("health", "ALIVE")
                tu = p.get("target_usage") or {}
                ad_hit = (tu.get("adsterra") or {}).get("count", 0)
                mn_hit = (tu.get("monetag") or {}).get("count", 0)
                l_ad = (tu.get("adsterra") or {}).get("last_used", 0) or 0
                l_mn = (tu.get("monetag") or {}).get("last_used", 0) or 0
                last_used = max(l_ad, l_mn)

                p_list.append({
                    "ip": ip,
                    "port": p.get("port", 0),
                    "country": c_name,
                    "country_flag": c_flag,
                    "health": health,
                    "is_active": is_active,
                    "used_by": active_ips.get(ip, None),
                    "adsterra_hit": ad_hit,
                    "monetag_hit": mn_hit,
                    "last_used": last_used,
                    "latency_ms": p.get("latency_ms", 0),
                })

            self.reporter.broadcast_state(
                target_network=self.args.target.upper(),
                running=not self.stop_event.is_set(),
                uptime_seconds=uptime_s,
                workers=list(self.workers_state.values()),
                proxy_summary={
                    "total": stats.get("total", 0),
                    "alive": stats.get("alive", 0),
                    "in_use": stats.get("in_use", 0),
                    "fresh": stats.get("fresh", 0),
                },
                proxies=p_list,
            )
        except Exception:
            pass

    def run(self) -> None:
        print_banner(
            node_name=self.reporter.node_name,
            target=self.args.target,
            workers=self.args.workers,
            unlimited=self.args.unlimited,
            headless=self.args.headless,
            url=self.args.url,
        )

        base_config = load_config()
        base_config.update({
            "target_url": self.args.url,
            "headless": self.args.headless,
            "max_uses_per_day": self.args.max_uses,
            "proxy_cooldown_hours": self.args.cooldown,
            "run_browser_verifier": True,
            "max_sessions_per_run": 0 if self.args.unlimited else self.args.sessions,
            "target_name": self.args.target,
        })

        pool_lock = threading.Lock()

        def _reset_pool() -> None:
            with pool_lock:
                self.proxy_manager.reset_usage_to_idle()
                self.proxy_manager.reset_cursor(0)
                t = self.args.target if self.args.target in ("monetag", "adsterra") else None
                reset_hits = self.proxy_manager.reset_target_usage(t)
                self.budget.reset_proxy_counts()
                print(f"\n{YELLOW}♻️ [Mode Tanpa Batas] Pool proxy direset kembali ke 0/2 ({reset_hits} IP). Melanjutkan putaran...{RESET}\n")

        # Spawn workers
        for wid in range(1, self.args.workers + 1):
            if self.args.target == "monetag":
                w_fn = monetag_worker_thread_loop
                w_tag = "Monetag"
            elif self.args.target == "adsterra":
                w_fn = flow_worker_thread_loop
                w_tag = "Adsterra"
            else:
                is_m = (wid % 2 == 1)
                w_fn = monetag_worker_thread_loop if is_m else flow_worker_thread_loop
                w_tag = "Monetag" if is_m else "Adsterra"

            t = threading.Thread(
                target=w_fn,
                args=(
                    wid,
                    base_config,
                    self.proxy_manager,
                    self.budget,
                    self._on_worker_event,
                    self.stop_event,
                ),
                kwargs={"reset_pool_callback": _reset_pool if self.budget.unlimited else None},
                daemon=True,
                name=f"{w_tag}-Worker-{wid}",
            )
            t.start()
            self.threads.append(t)
            ts_now = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts_now}] {CYAN}[W{wid}]{RESET} 🚀 Worker {w_tag} diaktifkan, mulai mencari & mengalokasikan proxy...", flush=True)

        # Heartbeat loop
        try:
            while not self.stop_event.is_set():
                self._broadcast_now()
                time.sleep(2.0)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}⚠️ Menghentikan worker secara aman...{RESET}")
            self.stop_event.set()

        # Final broadcast
        self._broadcast_now()
        print(f"\n{GREEN}✅ Bot selesai dijalankan secara bersih.{RESET}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bot Shortlink Runner CLI (Adsterra & Monetag) dengan Telemetry Supabase Realtime.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--target",
        choices=["adsterra", "monetag", "both"],
        default="adsterra",
        help="Jaringan iklan target: adsterra, monetag, atau both",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        help="Jumlah browser concurrency berjalan bersamaan",
    )
    parser.add_argument(
        "-u", "--unlimited",
        action="store_true",
        default=True,
        help="Mode tanpa batas (looping terus, auto reset 0/2 saat pool habis)",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=0,
        help="Batas maksimal sesi kunjungan (0 = ikuti unlimited)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Jalankan browser tanpa GUI layar (mode stealth headless)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Tampilkan jendela browser Camoufox di layar",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://article.riztama.my.id",
        help="URL web shortlink tujuan",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Nama node mesin ini (misal: '💻 Localhost (Jovan)' atau '⚡ Server A')",
    )
    parser.add_argument(
        "--max-uses",
        type=int,
        default=2,
        help="Maksimal pemakaian per IP per hari (default: 2)",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=6.0,
        help="Jeda waktu pendinginan antar pemakaian IP dalam jam (default: 6.0)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    runner = BotRunnerCLI(args)
    runner.run()
