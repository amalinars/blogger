#!/usr/bin/env python3
"""
open_camoufox.py
Membuka browser Camoufox (non-headless) memakai proxy ALIVE dari data/proxies.json,
lalu menjalankan audit anti-detect (webdriver, WebRTC leak, WebGL, canvas/audio, IP proxy).

Browser dibiarkan tetap terbuka sampai jendela ditutup atau Ctrl+C ditekan.

Contoh:
    python3 open_camoufox.py
    python3 open_camoufox.py https://iphey.com
    python3 open_camoufox.py --benchmark sannysoft
    python3 open_camoufox.py --require-safe https://browserleaks.com/webrtc
"""

import argparse
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.proxy_manager import ProxyManager
from automation.browser_verifier import BrowserVerifier
from automation.youtube.camoufox_engine import create_camoufox_session, get_random_viewport

MAX_PROXY_ATTEMPTS = 3


def log(msg: str):
    print(msg, flush=True)


def pick_and_validate_proxy(pm: ProxyManager, attempt: int) -> Optional[Dict[str, Any]]:
    """Ambil proxy sehat dengan rotasi persisten + verifikasi jaringan live."""
    caller_id = f"camoufox_manual_{int(time.time())}_{attempt}"
    proxy = pm.acquire_proxy(caller_id=caller_id, exclusive=True, verify_alive=True)
    if proxy:
        proxy["_lease_token"] = caller_id
    return proxy


def run_verifier(page, proxy_data: Dict[str, Any], benchmark: Optional[str]) -> Any:
    verifier = BrowserVerifier(strict_mode=False)
    page.goto("about:blank", timeout=30000)
    report = verifier.verify(
        page,
        expected_ip=proxy_data.get("ip_detected"),
        expected_country=proxy_data.get("country"),
        check_ads=True,
        benchmark=benchmark,
    )
    report.print_summary()

    actual = report.actual_state
    log("🔎 RINGKASAN ANTI-DETECT:")
    log(f"   - IP Aktual      : {actual.get('ip')}")
    log(f"   - IP Proxy       : {proxy_data.get('ip_detected')}")
    log(f"   - Country / ISP  : {actual.get('country')} | {actual.get('isp')}")
    log(f"   - navigator.webdriver : {actual.get('webdriver')} "
        f"({'AMAN' if actual.get('webdriver') is False else 'TERDETEKSI BOT'})")
    log(f"   - WebRTC Leak    : {'BOCOR' if actual.get('webrtc_leak') else 'AMAN'} "
        f"{actual.get('webrtc_ips') or ''}")
    log(f"   - WebGL          : {actual.get('webgl_vendor')} | {actual.get('webgl_renderer')}")
    log(f"   - Canvas / Audio : {actual.get('canvas_ok')} / {actual.get('audio_ok')}")
    log(f"   - OS Terdeteksi  : {actual.get('detected_os')}")
    log(f"   - Ads Allowed    : {actual.get('ads_allowed')}")

    for name, result in (report.benchmarks or {}).items():
        log(f"   - Benchmark {name}: {result}")

    return report


def keep_browser_open(browser):
    """Tahan proses selama browser/jendela masih terbuka."""
    log("\n🖥️  Browser siap dipakai. Tutup jendela browser (atau Ctrl+C) untuk keluar dan melepas proxy.\n")
    try:
        while True:
            try:
                if not browser.is_connected():
                    break
                pages = [p for ctx in browser.contexts for p in ctx.pages]
                if not pages:
                    break
            except Exception:
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        log("\n⏹️  Ctrl+C diterima, menutup browser...")


def main() -> int:
    parser = argparse.ArgumentParser(description="Buka Camoufox dengan proxy aktif + audit anti-detect.")
    parser.add_argument("url", nargs="?", default="about:blank", help="URL awal (default: about:blank)")
    parser.add_argument("--headless", action="store_true", help="Jalankan tanpa jendela (default: False)")
    parser.add_argument("--benchmark", choices=["sannysoft", "canvas", "iphey", "all"], default=None,
                        help="Audit live tambahan (membuka situs benchmark)")
    parser.add_argument("--require-safe", action="store_true", help="Batal membuka browser jika audit FAIL")
    parser.add_argument("--no-verify", action="store_true", help="Lewati audit anti-detect")
    parser.add_argument("--no-humanize", action="store_true", help="Matikan humanize Camoufox")
    parser.add_argument("--allow-adblock", action="store_true", help="Aktifkan uBlock Origin (blokir iklan)")
    args = parser.parse_args()

    def _graceful(signum, frame):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, _graceful)
        except (ValueError, OSError):
            pass

    pm = ProxyManager()
    stats = pm.get_stats()
    log("=" * 70)
    log("🦊 CAMOUFOX PROXY LAUNCHER")
    log(f"   Pool proxy: {stats['total']} total | ALIVE={stats['alive']} | "
        f"DEAD={stats['dead']} | UNKNOWN={stats['unknown']} | COOLDOWN={stats['cooldown']}")

    proxy_data: Optional[Dict[str, Any]] = None

    def release_lease():
        if proxy_data:
            try:
                pm.release_proxy(proxy_data.get("id"), caller_id=proxy_data.get("_lease_token"))
            except Exception:
                pass

    try:
        for attempt in range(1, MAX_PROXY_ATTEMPTS + 1):
            log(f"\n🔍 Mencari proxy aktif (percobaan {attempt}/{MAX_PROXY_ATTEMPTS})...")
            proxy_data = pick_and_validate_proxy(pm, attempt)
            if not proxy_data:
                log("❌ Tidak ada proxy ALIVE yang bisa dipakai.")
                return 1

            log(f"✅ Proxy dipakai : {proxy_data.get('country')} | "
                f"{proxy_data.get('ip_detected')} | {proxy_data.get('host')}:{proxy_data.get('port')} "
                f"| {proxy_data.get('latency_ms')} ms")

            log("🚀 Meluncurkan Camoufox...")
            try:
                with create_camoufox_session(
                    proxy_data=proxy_data,
                    headless=args.headless,
                    humanize=not args.no_humanize,
                    allow_ads=not args.allow_adblock,
                ) as browser:
                    page = browser.new_page(viewport=get_random_viewport())

                    if not args.no_verify:
                        log("🛡️  Menjalankan audit anti-detect...")
                        try:
                            report = run_verifier(page, proxy_data, args.benchmark)
                            if args.require_safe and not report.is_safe:
                                log("⛔ Audit FAIL dan --require-safe aktif. Browser tidak dibuka untuk dipakai.")
                                return 2
                        except Exception as exc:
                            log(f"⚠️  Audit gagal dijalankan: {exc}")
                            if args.require_safe:
                                return 2

                    if args.url and args.url != "about:blank":
                        log(f"🌐 Membuka {args.url} ...")
                        try:
                            page.goto(args.url, timeout=60000, wait_until="domcontentloaded")
                        except Exception as exc:
                            log(f"⚠️  Gagal membuka {args.url}: {exc}")

                    keep_browser_open(browser)
                    release_lease()
                    return 0

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log(f"❌ Gagal meluncurkan/memakai proxy: {exc}")
                try:
                    pm.report_failure(
                        proxy_data.get("id"),
                        error_message=str(exc),
                        is_proxy_error=True,
                    )
                except Exception:
                    pass
                release_lease()
                proxy_data = None
                if attempt == MAX_PROXY_ATTEMPTS:
                    log("❌ Semua percobaan proxy gagal.")
                    return 1
                log("🔄 Mencoba proxy lain...")

        return 1
    finally:
        release_lease()
        log("🔓 Proxy dikembalikan ke pool.")
        log("👋 Selesai.")


if __name__ == "__main__":
    raise SystemExit(main())
