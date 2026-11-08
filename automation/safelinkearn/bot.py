#!/usr/bin/env python3
"""
automation.safelinkearn.bot
Bot automasi untuk membuka dan melewati shortlink SafelinkEarn / SafeLinkU
(sfe.ad / crm.urlwebsite.com / invest.datapendidikan.com / safelinkearn.com)
menggunakan Camoufox Anti-Detect Browser.

Mendukung eksekusi konkuren (multi-worker) via CLI (--workers N --count M).
"""

import argparse
import concurrent.futures
import json
import logging
import os
import sys
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
import requests
# Setup root path agar module core dan automation dapat diimport
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(CURRENT_DIR))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from camoufox import DefaultAddons
from camoufox.sync_api import Camoufox

try:
    from automation.engine import build_camoufox_kwargs, resolve_geo_profile
except ImportError:
    def build_camoufox_kwargs(**kwargs):
        return {
            "headless": kwargs.get("headless", False),
            "humanize": kwargs.get("humanize", True),
        }

    def resolve_geo_profile(proxy_data):
        return {}

try:
    from core.proxy_manager import acquire_proxy, release_proxy, record_target_usage, report_failure
except ImportError:
    acquire_proxy = None
    release_proxy = None
    record_target_usage = None
    report_failure = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("safelinkearn")

MAX_PROXY_ATTEMPTS = 25
BROWSER_LAUNCH_LOCK = threading.Lock()

# Daftar domain gateway atau CDN internal shortlink yang BUKAN tujuan akhir
INTERNAL_DOMAINS = [
    "sfe.ad",
    "safelinku.com",
    "safelinkearn.com",
    "sfl.gl",
    "sfe.me",
    "crm.urlwebsite.com",
    "invest.datapendidikan.com",
    "cloudflare.com",
    "challenges.cloudflare.com",
    "about:blank",
]

# Skrip bypass pendeteksi adblock bawaan halaman (compat.js / page-state-update)
ADBLOCK_BYPASS_SCRIPT = """
(function() {
    const origDispatch = EventTarget.prototype.dispatchEvent;
    EventTarget.prototype.dispatchEvent = function(evt) {
        if (evt && evt.type === "page-state-update") {
            return true;
        }
        return origDispatch.call(this, evt);
    };

    try {
        window.__pageReady = Promise.resolve(false);
    } catch (e) {}
    window.adblock = false;
})();
"""


def validate_proxy_live(proxy_data: Dict[str, Any], timeout: int = 7) -> Dict[str, Any]:
    """Tes koneksi HTTP langsung ke api.ipify.org via proxy untuk menyaring 402/mati."""
    if not proxy_data:
        return {"success": False, "error": "No proxy data"}

    proxy_url = proxy_data.get("proxy_url")
    if not proxy_url:
        host = proxy_data.get("host")
        port = proxy_data.get("port")
        user = proxy_data.get("username", "")
        pwd = proxy_data.get("password", "")
        if user and pwd:
            proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = f"http://{host}:{port}"

    proxies = {"http": proxy_url, "https": proxy_url}
    start = time.time()
    try:
        resp = requests.get("http://api.ipify.org?format=json", proxies=proxies, timeout=timeout)
        latency = round((time.time() - start) * 1000, 2)
        if resp.status_code == 200:
            ip = resp.json().get("ip")
            return {"success": True, "ip": ip, "latency_ms": latency, "error": None}
        elif resp.status_code == 402:
            return {"success": False, "ip": None, "latency_ms": latency, "error": "HTTP 402 (Payment Required / Kuota Habis)"}
        else:
            return {"success": False, "ip": None, "latency_ms": latency, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        err_msg = type(e).__name__ + (f": {str(e)}" if str(e) else "")
        return {"success": False, "ip": None, "latency_ms": None, "error": err_msg}


def _is_destination_url(url: str) -> bool:
    """Mengecek apakah URL saat ini sudah keluar dari sistem shortlink/gateway."""
    if not url or url.startswith("about:") or url.startswith("chrome:"):
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return False

        for d in INTERNAL_DOMAINS:
            if host == d or host.endswith("." + d):
                return False

        ad_indicators = [
            "acscdn", "googleads", "doubleclick", "pubadx", "popcash",
            "adsterra", "uplcm", "syndication", "adnxs", "googlesyndication"
        ]
        if any(ind in host for ind in ad_indicators):
            return False

        return True
    except Exception:
        return False


def try_solve_turnstile(page: Any, tag: str = "") -> bool:
    """Mencari iframe Cloudflare Turnstile resmi dan mengklik checkbox jika perlu konfirmasi manusia."""
    try:
        for frame in page.frames:
            f_url = (frame.url or "").lower()
            # HANYA interaksi dengan frame resmi Cloudflare Turnstile, JANGAN sentuh iframe iklan
            if "challenges.cloudflare.com" in f_url or "turnstile" in f_url:
                for sel in [
                    'input[type="checkbox"]',
                    '.ctp-checkbox-label',
                    '#challenge-stage input',
                    '#challenge-stage',
                    'span.mark',
                ]:
                    try:
                        loc = frame.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            loc.first.click(timeout=1000)
                            logger.info(f"{tag}👉 Checkbox Turnstile diklik di frame via {sel}")
                            return True
                    except Exception:
                        continue
    except Exception:
        pass
    return False


def run_single_attempt(
    target_url: str,
    headless: bool,
    proxy_data: Optional[Dict[str, Any]],
    max_timeout_sec: int,
    worker_id: int = 1,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Menjalankan 1 sesi percobaan browser untuk menyelesaikan alur shortlink."""
    tag = f"[W{worker_id}] " if worker_id > 0 else ""
    geo_profile = resolve_geo_profile(proxy_data) if proxy_data else {}
    locale = geo_profile.get("locale") or "id-ID"
    timezone_id = geo_profile.get("timezone") or "Asia/Jakarta"

    camoufox_opts = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=True,
        allow_ads=True,
    )

    result: Dict[str, Any] = {
        "success": False,
        "worker_id": worker_id,
        "target_url": target_url,
        "final_url": "",
        "steps_completed": 0,
        "popups_detected": 0,
        "elapsed_sec": 0.0,
        "proxy": proxy_data.get("host") if proxy_data else "direct",
    }

    start_time = time.time()
    popups: List[str] = []

    def _emit(event_type: str, **kwargs: Any) -> None:
        if event_callback:
            try:
                event_callback(event_type, {"worker_id": worker_id, **kwargs})
            except Exception:
                pass

    # Gunakan startup lock agar peluncuran antar thread tidak bentrok
    with BROWSER_LAUNCH_LOCK:
        time.sleep(0.5)
        browser_ctx_manager = Camoufox(**camoufox_opts)
        browser = browser_ctx_manager.__enter__()

    try:
        context_opts: Dict[str, Any] = {
            "viewport": {"width": 1366, "height": 768},
            "locale": locale,
            "timezone_id": timezone_id,
        }
        context = browser.new_context(**context_opts)
        context.add_init_script(ADBLOCK_BYPASS_SCRIPT)

        main_page = context.new_page()

        def on_page_opened(p: Any):
            if p != main_page:
                p_url = p.url or "about:blank"
                popups.append(p_url)
                logger.info(f"{tag}🪟 Tab popup terdeteksi: {p_url[:75]}")
                if not seen_final_gate:
                    try:
                        p.close()
                        logger.info(f"{tag}🛡️  Popup iklan langsung ditutup: {p_url[:60]}")
                        main_page.bring_to_front()
                    except Exception:
                        pass
        context.on("page", on_page_opened)

        # 1. Buka URL shortlink awal
        logger.info(f"{tag}🌐 1. Membuka URL: {target_url}...")
        _emit("session_started")
        _emit("stepper_update", stage="🌐 Buka Link", status=f"Membuka {target_url[:55]}")
        main_page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(1.5)

        # 2. Tangani halaman gerbang awal (#go-btn form submit)
        logger.info(f"{tag}⏳ 2. Menunggu gerbang awal siap (#go-btn)...")
        for _ in range(25):
            time.sleep(1)
            try:
                has_flow = main_page.evaluate("() => !!document.getElementById('flow-data')")
                if has_flow:
                    logger.info(f"{tag}📄 Sudah berada di halaman artikel.")
                    break
            except Exception:
                pass

            try:
                btn_state = main_page.evaluate("""() => {
                    const btn = document.getElementById('go-btn');
                    if (!btn) return null;
                    return { disabled: btn.disabled, text: btn.innerText.trim() };
                }""")
                if btn_state:
                    logger.info(f"{tag}🔘 Tombol gerbang: '{btn_state.get('text')}' (disabled={btn_state.get('disabled')})")
                    if btn_state.get("disabled") is False:
                        logger.info(f"{tag}👉 Mengklik tombol gerbang #go-btn...")
                        _emit("stepper_update", stage="🚪 Gerbang Awal", status="Mengklik #go-btn...")
                        main_page.evaluate("() => document.getElementById('go-btn')?.click()")
                        time.sleep(2)
                        break
            except Exception:
                pass

        # 3. Loop stepper artikel sampai link tujuan akhir
        logger.info(f"{tag}🔄 3. Memulai proses stepper shortlink...")
        loop_start = time.time()
        steps_recorded = set()
        last_top_wait = None
        last_bot_wait = None
        turnstile_wait_start: Optional[float] = None
        seen_final_gate = False

        while time.time() - loop_start < max_timeout_sec:
            time.sleep(1.0)

            # Cek jika main_page sudah keluar dari internal domains setelah melewati gerbang akhir
            try:
                curr_url = main_page.url
                if (seen_final_gate or "3/3" in str(steps_recorded)) and _is_destination_url(curr_url):
                    logger.info(f"{tag}🎉🎉🎉 BERHASIL MENCAPAI TUJUAN AKHIR: {curr_url}")
                    _emit("stepper_update", stage="🎉 Selesai", status=f"Tujuan: {curr_url[:55]}")
                    result["success"] = True
                    result["final_url"] = curr_url
                    result["steps_completed"] = len(steps_recorded)
                    result["popups_detected"] = len(popups)
                    result["elapsed_sec"] = round(time.time() - start_time, 2)
                    return result
            except Exception:
                pass

            # Tangani tab lain: tutup popup iklan jika bukan di gerbang akhir
            try:
                if len(context.pages) > 1:
                    for p in list(context.pages):
                        if p != main_page:
                            try:
                                p_url = p.url or ""
                                if (seen_final_gate or "3/3" in str(steps_recorded)) and _is_destination_url(p_url):
                                    logger.info(f"{tag}🎉🎉🎉 BERHASIL MENCAPAI TUJUAN AKHIR (Tab Baru): {p_url}")
                                    _emit("stepper_update", stage="🎉 Selesai", status=f"Tujuan: {p_url[:55]}")
                                    result["success"] = True
                                    result["final_url"] = p_url
                                    result["steps_completed"] = len(steps_recorded)
                                    result["popups_detected"] = len(popups)
                                    result["elapsed_sec"] = round(time.time() - start_time, 2)
                                    return result
                                else:
                                    p.close()
                                    logger.info(f"{tag}🛡️  Menutup popup iklan: {p_url[:60]}")
                            except Exception:
                                pass
            except Exception:
                pass
            # Cek apakah berada di halaman gerbang akhir (/go/...)
            if "/go/" in curr_url or "safelinkearn.com/go" in curr_url:
                seen_final_gate = True
                try:
                    open_state = main_page.evaluate("""() => {
                        const btn = document.getElementById('open-btn');
                        if (!btn) return null;
                        return { disabled: btn.disabled, text: btn.innerText.trim() };
                    }""")
                    if open_state:
                        if open_state.get("disabled") is False:
                            logger.info(f"{tag}🎯 Gerbang akhir /go/ terdeteksi! Mengklik tombol '{open_state.get('text')}'...")
                            main_page.evaluate("() => document.getElementById('open-btn')?.click()")
                            time.sleep(2.5)
                            continue
                        else:
                            logger.info(f"{tag}⏳ Menunggu tombol gerbang akhir siap: '{open_state.get('text')}'...")
                            time.sleep(1.0)
                            continue
                except Exception as go_err:
                    logger.debug(f"{tag}Error pada /go/: {go_err}")
                    continue

            # Baca status stepper dari DOM halaman artikel
            try:
                state = main_page.evaluate("""() => {
                    const topCard = document.getElementById("step-top");
                    const botCard = document.getElementById("step-bottom");
                    const topBtn = topCard ? topCard.querySelector(".step-btn") : null;
                    const botBtn = botCard ? botCard.querySelector(".step-btn") : null;
                    const stepCount = document.querySelector(".step-count");
                    const tokEl = document.querySelector("[name='cf-turnstile-response']");
                    const blockedEl = document.querySelector(".step-blocked");
                    
                    return {
                        stepLabel: stepCount ? stepCount.innerText.trim() : null,
                        topText: topBtn ? topBtn.innerText.trim() : null,
                        topDisabled: topBtn ? topBtn.disabled : null,
                        botText: botBtn ? botBtn.innerText.trim() : null,
                        botDisabled: botBtn ? botBtn.disabled : null,
                        botHidden: botCard ? botCard.hidden : true,
                        hasToken: !!(tokEl && tokEl.value && tokEl.value.length > 5),
                        blockedMsg: blockedEl ? blockedEl.innerText.trim() : null,
                        url: window.location.href
                    };
                }""")
            except Exception as eval_err:
                logger.debug(f"{tag}Transisi halaman terdeteksi: {eval_err}")
                time.sleep(1.0)
                continue

            step_lbl = state.get("stepLabel")
            if step_lbl and step_lbl not in steps_recorded:
                steps_recorded.add(step_lbl)
                logger.info(f"{tag}📌 {step_lbl} ({state.get('url')})")
                _emit("stepper_update", stage=f"📌 {step_lbl}", status=state.get("url") or "")
            top_text = (state.get("topText") or "").strip()
            bot_text = (state.get("botText") or "").strip()
            top_dis = state.get("topDisabled")
            bot_dis = state.get("botDisabled")

            # Cek jika Turnstile sedang dibutuhkan
            if top_dis is True and "verify" in top_text.lower():
                if not state.get("hasToken"):
                    if turnstile_wait_start is None:
                        turnstile_wait_start = time.time()
                    elapsed_cf = time.time() - turnstile_wait_start
                    if int(elapsed_cf) % 5 == 0 or elapsed_cf < 3.0:
                        logger.info(f"{tag}🛡️ Menunggu penyelesaian Cloudflare Turnstile ({int(elapsed_cf)}s)...")
                    # Cek hanya frame challenges.cloudflare.com resmi
                    if elapsed_cf >= 5.0 and int(elapsed_cf) % 5 == 0:
                        try_solve_turnstile(main_page, tag=tag)
                    if proxy_data and elapsed_cf > 65.0:
                        logger.warning(f"{tag}⚠️ Turnstile tertahan > 65 detik pada proksi ini. Merotasi proksi...")
                        break
                time.sleep(1.0)
                continue
            else:
                turnstile_wait_start = None

            # Kasus A: Countdown di tombol atas ("Please Wait X")
            if "please wait" in top_text.lower():
                if top_text != last_top_wait:
                    logger.info(f"{tag}⏳ {top_text}...")
                    last_top_wait = top_text
                continue

            # Kasus B: Diminta scroll ke bawah ("Scroll down to continue")
            if "scroll down" in top_text.lower():
                logger.info(f"{tag}📜 Instruksi scroll terdeteksi: '{top_text}'. Menggulir ke penanda artikel...")
                main_page.evaluate("""() => {
                    const s = document.getElementById('step-sentinel');
                    if (s) {
                        s.scrollIntoView({ behavior: 'instant', block: 'center' });
                    }
                }""")
                time.sleep(1.0)
            # Kasus C: Tombol atas aktif untuk diverifikasi ("Click to Verify", "Click to Continue", dsb.)
            if top_dis is False and "please wait" not in top_text.lower() and "scroll" not in top_text.lower() and top_text:
                logger.info(f"{tag}🖱️ Mengklik tombol verifikasi atas: '{top_text}'...")
                _emit("stepper_update", stage="🖱️ Verifikasi Atas", status=top_text)
                main_page.evaluate("""() => {
                    const topBtn = document.querySelector('#step-top .step-btn');
                    if (topBtn) topBtn.click();
                }""")
                time.sleep(2.0)
                continue

            # Kasus D: Countdown di tombol bawah ("Please Wait X")
            if not state.get("botHidden") and "please wait" in bot_text.lower():
                if bot_text != last_bot_wait:
                    logger.info(f"{tag}⏳ Tombol bawah: {bot_text}...")
                    _emit("stepper_update", stage="⏳ Countdown Stepper", status=bot_text)
                    last_bot_wait = bot_text
                continue

            # Kasus E: Tombol bawah aktif ("Next", "Go to the Next Step", "Click Here to Continue", "Open Link", dsb.)
            if not state.get("botHidden") and bot_dis is False and "please wait" not in bot_text.lower() and bot_text:
                logger.info(f"{tag}🖱️ Mengklik tombol stepper bawah: '{bot_text}'...")
                _emit("stepper_update", stage="🖱️ Klik Stepper", status=bot_text)
                main_page.evaluate("""() => {
                    const botBtn = document.querySelector('#step-bottom .step-btn');
                    if (botBtn) {
                        botBtn.scrollIntoView({ behavior: 'auto', block: 'center' });
                        botBtn.click();
                    }
                }""")
                time.sleep(2.5)
                continue

        logger.warning(f"{tag}⚠️ Batas waktu tunggu tercapai sebelum tujuan akhir terdeteksi.")
        result["final_url"] = main_page.url
    finally:
        try:
            browser_ctx_manager.__exit__(None, None, None)
        except Exception:
            pass

    result["elapsed_sec"] = round(time.time() - start_time, 2)
    return result


def run_safelink_session(
    target_url: str = "https://sfe.ad/pB5n5lnLGp",
    headless: bool = False,
    use_proxy: bool = False,
    proxy_data: Optional[Dict[str, Any]] = None,
    max_timeout_sec: int = 180,
    worker_id: int = 1,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan alur penuh SafelinkEarn dengan retry loop otomatis untuk proksi per-worker.
    """
    tag = f"[W{worker_id}] " if worker_id > 0 else ""

    if not use_proxy:
        return run_single_attempt(
            target_url=target_url,
            headless=headless,
            proxy_data=None,
            max_timeout_sec=max_timeout_sec,
            worker_id=worker_id,
            event_callback=event_callback,
        )

    # Mode Proksi: Uji dan rotasi proksi hingga menemukan proksi yang benar-benar aktif
    max_attempts = MAX_PROXY_ATTEMPTS
    for attempt in range(1, max_attempts + 1):
        logger.info(f"{tag}🔍 Mencari proksi aktif (percobaan {attempt}/{max_attempts})...")
        leased_proxy = acquire_proxy(target="safelink")
        if not leased_proxy:
            logger.warning(f"{tag}❌ Tidak ada proksi yang tersedia di pool.")
            break

        host_port = f"{leased_proxy.get('host')}:{leased_proxy.get('port')}"
        logger.info(f"{tag}📡 Menguji koneksi proksi: {host_port} ({leased_proxy.get('country')})...")

        # Uji jaringan HTTP langsung sebelum menyerahkan ke browser
        test_res = validate_proxy_live(leased_proxy)
        if not test_res.get("success"):
            err_reason = test_res.get("error")
            logger.warning(f"{tag}⚠️ Proksi {host_port} tidak dapat dipakai: {err_reason}")
            if report_failure:
                report_failure(leased_proxy.get("id"), error_message=err_reason, is_proxy_error=True)
            if release_proxy:
                release_proxy(leased_proxy.get("id"))
            continue

        detected_ip = test_res.get("ip")
        leased_proxy["ip_detected"] = detected_ip
        logger.info(f"{tag}✅ Proksi aktif terverifikasi: {host_port} | IP: {detected_ip} | Latency: {test_res.get('latency_ms')} ms")

        try:
            res = run_single_attempt(
                target_url=target_url,
                headless=headless,
                proxy_data=leased_proxy,
                max_timeout_sec=max_timeout_sec,
                worker_id=worker_id,
                event_callback=event_callback,
            )
            if res.get("success"):
                if record_target_usage:
                    record_target_usage(leased_proxy.get("id"), target="safelink")
                return res
            else:
                logger.warning(f"{tag}⚠️ Percobaan pada proksi {host_port} belum berhasil mencapai tujuan.")
        except Exception as launch_err:
            logger.error(f"{tag}❌ Gagal meluncurkan browser dengan proksi {host_port}: {launch_err}")
            if report_failure:
                report_failure(leased_proxy.get("id"), error_message=str(launch_err), is_proxy_error=True)
        finally:
            if release_proxy:
                release_proxy(leased_proxy.get("id"))
                logger.info(f"{tag}🔓 Proksi {host_port} dilepaskan.")

    return {
        "success": False,
        "worker_id": worker_id,
        "target_url": target_url,
        "final_url": "",
        "steps_completed": 0,
        "popups_detected": 0,
        "elapsed_sec": 0.0,
        "proxy": "all_failed",
    }


def safelink_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: Any,
    budget: Any,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    reset_pool_callback: Optional[Callable[[], None]] = None,
) -> None:
    """
    Loop worker multi-sesi untuk SafelinkEarn dengan rotasi proxy residensial.
    Kompatibel penuh dengan CLI run_bot.py dan Supabase Telemetry dashboard.
    """
    tag = f"[W{worker_id}]"
    target_url = config.get("target_url") or "https://sfe.ad/pB5n5lnLGp"
    headless = bool(config.get("headless", True))
    max_timeout = int(config.get("max_timeout", 180))
    caller_prefix = f"safelink_w{worker_id}"

    if event_callback:
        try:
            event_callback("log_message", {
                "worker_id": worker_id,
                "message": f"{tag} Worker SafelinkEarn siap — IP dirotasi otomatis.",
                "style": "green",
            })
        except Exception:
            pass

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break
        if not budget.reserve():
            break

        target_name = "safelink"
        max_uses = int(config.get("max_uses_per_day", 2))
        cooldown_hrs = float(config.get("proxy_cooldown_hours", 6.0))
        caller_id = f"{caller_prefix}_{int(time.time() * 1000)}"

        proxy = proxy_manager.acquire_proxy(
            caller_id=caller_id,
            exclusive=True,
            verify_alive=False,
            target=target_name,
            max_uses_per_day=max_uses,
            cooldown_seconds=cooldown_hrs * 3600,
        )

        if not proxy:
            if getattr(budget, "unlimited", False) and reset_pool_callback and not getattr(proxy_manager, "supabase_enabled", False):
                reset_pool_callback()
                time.sleep(1.0)
                continue
            time.sleep(5.0)
            continue

        proxy_id = proxy.get("id") or proxy.get("proxy_url")
        ip = proxy.get("ip_detected") or proxy.get("host", "?")
        country = proxy.get("country", "Unknown")

        if event_callback:
            try:
                event_callback("proxy_assigned", {
                    "worker_id": worker_id,
                    "proxy_id": proxy_id,
                    "ip": ip,
                    "country": country,
                    "target_network": "🔗 SafelinkEarn",
                })
                event_callback("session_started", {"worker_id": worker_id})
            except Exception:
                pass

        # Tes koneksi proxy live
        test_res = validate_proxy_live(proxy)
        if not test_res.get("success"):
            err_reason = test_res.get("error", "Proxy dead")
            proxy_manager.report_failure(proxy, error_message=err_reason, is_proxy_error=True)
            proxy_manager.release_proxy(proxy)
            budget.record_session(proxy_id, "FAIL")
            if event_callback:
                try:
                    event_callback("session_completed", {
                        "worker_id": worker_id,
                        "status": "FAIL",
                        "error": err_reason,
                    })
                except Exception:
                    pass
            continue

        proxy["ip_detected"] = test_res.get("ip")

        try:
            res = run_single_attempt(
                target_url=target_url,
                headless=headless,
                proxy_data=proxy,
                max_timeout_sec=max_timeout,
                worker_id=worker_id,
                event_callback=event_callback,
            )
            is_success = bool(res.get("success"))
            if is_success:
                proxy_manager.record_target_hit(proxy, target=target_name)
                budget.record_session(proxy_id, "PASS")
                if event_callback:
                    try:
                        event_callback("session_completed", {
                            "worker_id": worker_id,
                            "status": "PASS",
                            "details": res,
                        })
                    except Exception:
                        pass
            else:
                proxy_manager.report_failure(proxy, error_message="Target not reached", is_proxy_error=False)
                budget.record_session(proxy_id, "FAIL")
                if event_callback:
                    try:
                        event_callback("session_completed", {
                            "worker_id": worker_id,
                            "status": "FAIL",
                            "error": "Target not reached",
                        })
                    except Exception:
                        pass
        except Exception as e:
            proxy_manager.report_failure(proxy, error_message=str(e), is_proxy_error=False)
            budget.record_session(proxy_id, "FAIL")
            if event_callback:
                try:
                    event_callback("session_completed", {
                        "worker_id": worker_id,
                        "status": "FAIL",
                        "error": str(e),
                    })
                except Exception:
                    pass
        finally:
            proxy_manager.release_proxy(proxy)

        time.sleep(random.uniform(1.0, 2.5))


def main():
    parser = argparse.ArgumentParser(description="SafelinkEarn / SafeLinkU Shortlink Concurrent Automation Bot")
    parser.add_argument(
        "url",
        nargs="?",
        default="https://sfe.ad/pB5n5lnLGp",
        help="URL shortlink target (default: https://sfe.ad/pB5n5lnLGp)",
    )
    parser.add_argument("-w", "--workers", type=int, default=1, help="Jumlah worker bersamaan / concurrent (default: 1)")
    parser.add_argument("-n", "--count", type=int, default=None, help="Total sesi yang ingin dijalankan (default: sama dengan workers)")
    parser.add_argument("--headless", action="store_true", help="Jalankan di mode headless (default: non-headless)")
    parser.add_argument("--proxy", action="store_true", help="Gunakan proxy residential dari pool Supabase")
    parser.add_argument("--timeout", type=int, default=180, help="Batas waktu maksimum per sesi dalam detik (default: 180)")

    args = parser.parse_args()

    workers = max(1, args.workers)
    total_count = args.count if args.count and args.count > 0 else workers

    print("=" * 65)
    print("🚀 SAFELINKU / SAFELINKEARN CONCURRENT BOT")
    print(f"🔗 Target URL   : {args.url}")
    print(f"👥 Workers      : {workers} paralel")
    print(f"🎯 Total Sesi   : {total_count}")
    print(f"🖥️  Headless Mode: {args.headless}")
    print(f"🛡️  Use Proxy    : {args.proxy}")
    print("=" * 65 + "\n")

    start_all = time.time()
    results: List[Dict[str, Any]] = []

    def _worker_task(task_index: int, worker_slot: int) -> Dict[str, Any]:
        # Stagger jeda awal jika ada beberapa worker agar tidak boot di detik milidetik yang sama persis
        if task_index < workers:
            stagger = task_index * 2.5
            if stagger > 0:
                time.sleep(stagger)

        return run_safelink_session(
            target_url=args.url,
            headless=args.headless,
            use_proxy=args.proxy,
            max_timeout_sec=args.timeout,
            worker_id=worker_slot,
        )

    if workers == 1 and total_count == 1:
        res = _worker_task(0, 1)
        results.append(res)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for i in range(total_count):
                slot = (i % workers) + 1
                fut = executor.submit(_worker_task, i, slot)
                futures.append(fut)

            for fut in concurrent.futures.as_completed(futures):
                try:
                    res = fut.result()
                    results.append(res)
                except Exception as exc:
                    logger.error(f"Worker task error: {exc}")

    elapsed_all = round(time.time() - start_all, 2)
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count

    print("\n" + "=" * 65)
    print("📊 RINGKASAN HASIL KONKURENSI:")
    print(f"- Total Dijalankan : {len(results)} sesi")
    print(f"- Sukses           : {success_count} ✅")
    print(f"- Gagal            : {fail_count} ❌")
    print(f"- Total Durasi     : {elapsed_all} detik")
    print("=" * 65)

    for idx, r in enumerate(results, 1):
        status_sym = "✅" if r.get("success") else "❌"
        print(f"[{idx}] Worker {r.get('worker_id', '?')} {status_sym} | Proksi: {r.get('proxy')} | Durasi: {r.get('elapsed_sec')}s | Tujuan: {r.get('final_url')}")
    print("=" * 65 + "\n")

    sys.exit(0 if success_count > 0 else 1)


if __name__ == "__main__":
    main()
