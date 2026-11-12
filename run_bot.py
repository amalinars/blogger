#!/usr/bin/env python3
"""Unified Terminal CLI Entrypoint for Bot Ad Impression (Monetag).

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
import atexit
import os
import re
import uuid
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
from automation.chain_provider import ChainProxyProvider
from automation.engine import load_config
from automation.session import SessionBudget
from automation.monetag.flow import monetag_worker_thread_loop, run_monetag_session
from automation.safelinkearn.bot import safelink_worker_thread_loop
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

# Warna konsisten per worker agar log multi-worker mudah dipisahkan.
WORKER_COLORS = (CYAN, MAGENTA, GREEN, BLUE, YELLOW)


def print_banner(node_name: str, target: str, workers: int, unlimited: bool, headless: bool, url: str, potato: bool = True) -> None:
    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════════════════════════════╗{RESET}", flush=True)
    print(f"{BOLD}{CYAN}║     🚀 BOT AD IMPRESSION RUNNER - DISTRIBUTED CLI TERMINAL         ║{RESET}", flush=True)
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════════════════════╝{RESET}", flush=True)
    print(f"  {BOLD}Node ID / Name :{RESET} {GREEN}{node_name}{RESET}", flush=True)
    print(f"  {BOLD}Target Network :{RESET} {MAGENTA if 'monetag' in target else YELLOW}{target.upper()}{RESET}", flush=True)
    print(f"  {BOLD}Concurrent     :{RESET} {CYAN}{workers} Browser Worker{RESET}", flush=True)
    print(f"  {BOLD}Mode Kuota     :{RESET} {GREEN}Tanpa Batas (∞ Looping Continuous){RESET}" if unlimited else f"  {BOLD}Mode Kuota     :{RESET} Terbatas", flush=True)
    print(f"  {BOLD}Headless       :{RESET} {'🟢 Aktif (Tanpa Layar)' if headless else '🖥️ Non-Headless (Layar Terlihat)'}", flush=True)
    print(f"  {BOLD}Target URL     :{RESET} {BLUE}{url}{RESET}", flush=True)
    print(f"  {BOLD}Potato Mode    :{RESET} {GREEN}🥔 Aktif (Ultra-Ringan: Single Process, Block Video Ad, Browser Reuse){RESET}" if potato else f"  {BOLD}Potato Mode    :{RESET} 🔴 Nonaktif", flush=True)
    print(f"  {BOLD}Live Monitor   :{RESET} {BOLD}{GREEN}https://article.riztama.my.id/monitoring{RESET}", flush=True)
    print(f"{DIM}───────────────────────────────────────────────────────────────────{RESET}\n", flush=True)



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
        raw_name = self.args.name or os.environ.get("BOT_NODE_ID") or f"node_{uuid.uuid4().hex[:6]}"
        self.node_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_name)
        self.proxy_manager = ProxyManager(reset_stale_usage=True, node_id=self.node_id)
        self.proxy_manager.reset_usage_to_idle()
        stats = self.proxy_manager.get_stats()
        if stats.get("total", 0) == 0 or getattr(self.args, "sync_supabase", False):
            synced = self.proxy_manager.sync_from_supabase()
            if synced > 0:
                print(f"{GREEN}☁️ Berhasil mensinkronkan {synced} proxy dari Supabase (schema: proxxies).{RESET}", flush=True)
            elif stats.get("total", 0) == 0:
                print(f"{YELLOW}⚠️ Info: proxies.json kosong dan belum ada proxy di tabel proxxies.proxy_list Supabase.{RESET}", flush=True)
        self.reporter = get_telemetry_reporter()

        if self.args.name:
            self.reporter.set_node_name(self.args.name)

        # Budget session
        max_sess = 0 if self.args.unlimited else self.args.sessions
        self.budget = SessionBudget(max_sess, 1)

        self.workers_state: Dict[int, Dict[str, Any]] = {}
        for wid in range(1, self.args.workers + 1):
            t_net = "🔗 SafelinkEarn" if self.args.target in ("safelink", "safelinkearn") else "💎 Monetag"
            self.workers_state[wid] = {
                "worker_id": wid,
                "target_net": t_net,
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
        self._console_lock = threading.Lock()

    @staticmethod
    def _worker_color(worker_id: Any) -> str:
        try:
            index = (int(worker_id) - 1) % len(WORKER_COLORS)
        except (TypeError, ValueError):
            index = 0
        return WORKER_COLORS[index]

    def _console(self, worker_id: Any, message: str) -> None:
        """Cetak satu baris log worker dengan warna & prefix tetap yang rapi."""
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            tag = f"W{int(worker_id):>2}"
        except (TypeError, ValueError):
            tag = "W?"
        color = self._worker_color(worker_id)
        with self._console_lock:
            print(f"[{ts}] {color}[{tag}]{RESET} {message}", flush=True)

    def _chain_log(self, message: str) -> None:
        """Rapikan log ChainProxyProvider: ikut warna worker bila ada prefix [Wn]."""
        text = str(message)
        match = re.match(r"^\[W\s*(\d+)\]\s*(.*)$", text)
        if match:
            self._console(int(match.group(1)), match.group(2))
            return
        with self._console_lock:
            print(text, flush=True)

    def _on_worker_event(self, etype: str, data: Dict[str, Any]) -> None:
        wid = data.get("worker_id", 1)
        w = self.workers_state.setdefault(wid, {"worker_id": wid})
        ts = datetime.now().strftime("%H:%M:%S")

        # Riwayat aktivitas log real-time per worker (ring buffer 15 baris)
        logs = w.setdefault("logs", [])

        if etype == "log_message":
            msg = re.sub(r"^\[W\d+\]\s*", "", data.get("message", ""))
            if msg:
                logs.append(f"[{ts}] {msg}")
                w["logs"] = logs[-15:]
                w["activity"] = msg[:75]
                self._console(wid, msg)

        elif etype == "stepper_update":
            stage = data.get("stage", "")
            status = data.get("status", "")
            w["stepper"] = stage
            w["activity"] = status
            logs.append(f"[{ts}] {stage} - {status}")
            w["logs"] = logs[-15:]
            if stage or status:
                self._console(wid, f"⏳ {stage} — {status}")

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
            self._console(wid, f"🛡️ IP Dialokasikan: {BOLD}{w['proxy_ip']}{RESET} ({c_flag} {c_name}) - {w['target_net']}")

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
            self._console(wid, f"🔍 Audit Anti-Detect: {score_col}{score}/100{RESET} | Bot Flag: {w['bot']} | WebRTC: {w['webrtc']}")

        elif etype == "session_started":
            w["stepper"] = "🌐 Buka Web"
            w["activity"] = "Membuka halaman web target..."
            logs.append(f"[{ts}] 🌐 Membuka target: {self.args.url}")
            w["logs"] = logs[-15:]
            self._console(wid, f"🌐 Membuka halaman target: {self.args.url}")

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
            self._console(wid, f"🎯 Interaksi iklan: {ad_type}")

        elif etype == "flow_completed":
            w["stepper"] = "🏁 Impresi Selesai"
            w["activity"] = "Seluruh tahapan impresi iklan berhasil diselesaikan!"
            logs.append(f"[{ts}] 🏁 Seluruh alur impresi iklan selesai dengan sukses")
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
            self._console(wid, f"🏁 Sesi Selesai: {status_col}{label}{RESET} (Total Sukses: {w['sessions_done']})")

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
                t_key = "safelink" if self.args.target in ("safelink", "safelinkearn") else "monetag"
                tu = p.get("target_usage") or {}
                mn_hit = (tu.get(t_key) or {}).get("count", 0)
                last_used = (tu.get(t_key) or {}).get("last_used", 0) or 0
                p_list.append({
                    "ip": ip,
                    "port": p.get("port", 0),
                    "country": c_name,
                    "country_flag": c_flag,
                    "health": health,
                    "is_active": is_active,
                    "used_by": active_ips.get(ip, None),
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
        is_safelink = self.args.target in ("safelink", "safelinkearn")
        default_url = "https://sfe.ad/pB5n5lnLGp" if is_safelink else "https://article.riztama.my.id"
        target_url = self.args.url or default_url
        self.args.url = target_url

        print_banner(
            node_name=self.reporter.node_name,
            target=self.args.target,
            workers=self.args.workers,
            unlimited=self.args.unlimited,
            headless=self.args.headless,
            url=target_url,
            potato=getattr(self.args, "potato", True),
        )

        chain_provider = None
        if not is_safelink and not getattr(self.args, "no_chain", False):
            try:
                chain_provider = ChainProxyProvider(
                    hop_tries=getattr(self.args, "hop_tries", 3),
                    timeout=getattr(self.args, "chain_timeout", 15.0),
                    dead_confirm_hops=getattr(self.args, "dead_confirm_hops", 2),
                    verbose=bool(getattr(self.args, "chain_verbose", False)),
                    target="monetag",
                    channel="automation",
                    strict_channel=False,
                    target_max_uses_per_day=self.args.max_uses,
                    target_cooldown_seconds=self.args.cooldown * 3600,
                    target_window_seconds=24 * 3600,
                    residential_host_contains="floppydata",
                    proxy_manager=self.proxy_manager,
                    log_func=self._chain_log,
                )
                print(
                    f"{GREEN}🔗 Chain mode aktif: hop 3xK -> residential FloppyData "
                    f"(target=monetag, {len(chain_provider.hops)} hop).{RESET}",
                    flush=True,
                )
            except Exception as exc:
                print(f"{RED}❌ Chain tidak bisa dimulai: {exc}{RESET}", flush=True)
                print(
                    f"{YELLOW}   Perbaiki Supabase/hop, atau jalankan dengan --no-chain.{RESET}",
                    flush=True,
                )
                raise SystemExit(1)
        elif not is_safelink:
            print(f"{YELLOW}⚠️ Chain dimatikan (--no-chain); memakai residential langsung.{RESET}", flush=True)

        base_config = load_config()
        base_config.update({
            "target_url": target_url,
            "headless": self.args.headless,
            "max_uses_per_day": self.args.max_uses,
            "proxy_cooldown_hours": self.args.cooldown,
            "run_browser_verifier": True,
            "use_chain": chain_provider is not None,
            "max_sessions_per_run": 0 if self.args.unlimited else self.args.sessions,
            "target_name": self.args.target,
            "errorlogs": getattr(self.args, "errorlogs", False),
            "lightweight": getattr(self.args, "potato", True),
        })

        if chain_provider is not None and getattr(self.args, "chain_test", False):
            print(f"{CYAN}🧪 Menjalankan chain test (hop -> residential -> exit IP)...{RESET}", flush=True)
            test_proxy = chain_provider.next_proxy(caller_id=f"chain_test_{int(time.time())}")
            if not test_proxy:
                print(f"{RED}❌ Chain test gagal: tidak ada kombinasi hop/residential yang lolos.{RESET}", flush=True)
                raise SystemExit(1)
            print(
                f"{GREEN}✅ Chain test OK: hop {test_proxy.get('hop_ip')}:{test_proxy.get('hop_port')} "
                f"-> exit {test_proxy.get('expected_ip')} ({test_proxy.get('country') or '?'}) "
                f"| {test_proxy.get('latency_ms')}ms{RESET}",
                flush=True,
            )
            chain_provider.finish_session(test_proxy, False, error_kind="test")
            return

        pool_lock = threading.Lock()

        def _reset_pool() -> None:
            if getattr(self.proxy_manager, "supabase_enabled", False):
                return
            with pool_lock:
                self.proxy_manager.reset_usage_to_idle()
                self.proxy_manager.reset_cursor(0)
                t_key = "safelink" if is_safelink else "monetag"
                reset_hits = self.proxy_manager.reset_target_usage(t_key)
                self.budget.reset_proxy_counts()
                print(f"\n{YELLOW}♻️ [Mode Tanpa Batas Lokal] Pool proxy direset kembali ke 0/2 ({reset_hits} IP). Melanjutkan putaran...{RESET}\n")

        # Spawn workers
        for wid in range(1, self.args.workers + 1):
            if is_safelink:
                w_fn = safelink_worker_thread_loop
                w_tag = "SafelinkEarn"
            else:
                w_fn = monetag_worker_thread_loop
                w_tag = "Monetag"
            worker_kwargs: Dict[str, Any] = {
                "reset_pool_callback": _reset_pool if self.budget.unlimited else None,
            }
            if not is_safelink:
                worker_kwargs["chain_provider"] = chain_provider
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
                kwargs=worker_kwargs,
                daemon=True,
                name=f"{w_tag}-Worker-{wid}",
            )
            t.start()
            self.threads.append(t)
            self._console(wid, f"🚀 Worker {w_tag} diaktifkan, mulai mencari & mengalokasikan proxy...")
            if wid < self.args.workers:
                time.sleep(3.0)

        # Daftarkan handler pembersihan status proxy saat Ctrl+C / Stop / Exit
        def _cleanup(*_):
            self.stop_event.set()
            print(f"\n{CYAN}🔄 Mereset status proxy node ({self.node_id}) ke IDLE di Supabase & lokal...{RESET}", flush=True)
            cleaned = self.proxy_manager.reset_usage_to_idle()
            print(f"{GREEN}✅ Status proxy node ({self.node_id}) berhasil dikembalikan ke IDLE (Total: {cleaned} lokal).{RESET}\n", flush=True)

        try:
            signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
            signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
        except Exception:
            pass
        atexit.register(_cleanup)

        # Heartbeat loop
        try:
            while not self.stop_event.is_set():
                self._broadcast_now()
                time.sleep(2.0)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}⚠️ Menghentikan worker secara aman...{RESET}")
        finally:
            self.stop_event.set()
            self._broadcast_now()
            print(f"{GREEN}✅ Bot selesai dijalankan secara bersih.{RESET}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bot Ad Impression Runner CLI (Monetag) dengan Telemetry Supabase Realtime.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--target",
        choices=["monetag", "safelinkearn", "safelink"],
        default="monetag",
        help="Jaringan target: monetag, safelinkearn",
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
        default=None,
        help="URL web target tujuan (default: Monetag -> article.riztama.my.id, SafelinkEarn -> sfe.ad/pB5n5lnLGp)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Nama node mesin ini (misal: '💻 Localhost (Jovan)' atau '⚡ Server A')",
    )
    parser.add_argument(
        "--sync-supabase",
        action="store_true",
        help="Paksa sinkronisasi proxy dari database Supabase sebelum bot berjalan",
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
    parser.add_argument(
        "--no-chain",
        action="store_true",
        help="Nonaktifkan chain hop 3xK; pakai residential FloppyData langsung (fallback)",
    )
    parser.add_argument(
        "--chain-test",
        action="store_true",
        help="Tes satu kombinasi hop + residential lalu keluar tanpa menjalankan sesi",
    )
    parser.add_argument(
        "--hop-tries",
        type=int,
        default=3,
        help="Jumlah hop acak yang dicoba per sesi chain",
    )
    parser.add_argument(
        "--chain-timeout",
        type=float,
        default=15.0,
        help="Timeout probe TCP/HTTP chain dalam detik",
    )
    parser.add_argument(
        "--dead-confirm-hops",
        type=int,
        default=2,
        help="Jumlah hop gagal sebelum residential dianggap DEAD",
    )
    parser.add_argument(
        "--chain-verbose",
        action="store_true",
        help="Tampilkan log detail probe chain",
    )
    parser.add_argument(
        "--errorlogs",
        "--error-logs",
        action="store_true",
        help="Aktifkan logging diagnostik mendalam Turnstile (khususnya di Google Colab / VPS)",
    )
    parser.add_argument(
        "--potato",
        "--lite",
        action="store_true",
        default=True,
        help="Mode ultra-ringan untuk laptop kentang (blokir video ad, hemat RAM/CPU, browser reuse, default: aktif)",
    )
    parser.add_argument(
        "--no-potato",
        action="store_false",
        dest="potato",
        help="Nonaktifkan mode ultra-ringan potato",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    runner = BotRunnerCLI(args)
    runner.run()
