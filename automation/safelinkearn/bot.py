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


class TurnstileDiagnostics:
    """Modul diagnostik mendalam Cloudflare Turnstile (--errorlogs)."""
    def __init__(self, page: Any, tag: str = "", worker_id: int = 1, enabled: bool = False, proxy_info: str = "direct"):
        self.page = page
        self.tag = tag
        self.worker_id = worker_id
        self.enabled = enabled
        self.proxy_info = proxy_info
        self.console_logs: List[str] = []
        self.failed_requests: List[Dict[str, Any]] = []
        self.page_errors: List[str] = []
        self.cf_frames_detected: List[str] = []
        self.click_attempts: List[str] = []
        self.saved_artifacts: List[str] = []
        self.start_time = time.time()
        self.last_diagnostic_time = 0.0

        if self.enabled and self.page:
            self._setup_listeners()

    def _setup_listeners(self) -> None:
        try:
            def on_console(msg: Any) -> None:
                text = msg.text or ""
                mtype = msg.type or "log"
                lower_text = text.lower()
                if mtype in ("error", "warning") or any(k in lower_text for k in ["turnstile", "cloudflare", "challenge", "token", "captcha", "cf-"]):
                    entry = f"[{mtype.upper()}] {text}"
                    self.console_logs.append(entry)
                    if len(self.console_logs) > 80:
                        self.console_logs.pop(0)
                    if any(k in lower_text for k in ["turnstile", "challenge", "cf-error", "300030", "110200", "600010"]):
                        logger.warning(f"{self.tag}🔍 [ERRORLOGS:Console] {entry[:140]}")

            def on_page_error(exc: Any) -> None:
                err = str(exc)
                self.page_errors.append(err)
                logger.warning(f"{self.tag}💥 [ERRORLOGS:PageError] {err[:140]}")

            def on_request_failed(req: Any) -> None:
                url = (req.url or "")
                if any(k in url.lower() for k in ["cloudflare", "turnstile", "challenges", "sfe.ad", "safelinkearn"]):
                    failure = req.failure or "Unknown failure"
                    entry = {"url": url[:100], "method": req.method, "failure": str(failure)}
                    self.failed_requests.append(entry)
                    if len(self.failed_requests) > 40:
                        self.failed_requests.pop(0)
                    logger.warning(f"{self.tag}🌐 [ERRORLOGS:ReqFailed] {req.method} {url[:70]} -> {failure}")

            self.page.on("console", on_console)
            self.page.on("pageerror", on_page_error)
            self.page.on("requestfailed", on_request_failed)
        except Exception as e:
            logger.debug(f"{self.tag}Gagal mengaitkan listener diagnostik: {e}")

    def log_click_attempt(self, detail: str) -> None:
        if self.enabled:
            self.click_attempts.append(detail)
            logger.info(f"{self.tag}🖱️ [ERRORLOGS:Click] {detail}")

    def inspect_turnstile_state(self, trigger: str = "periodic") -> Dict[str, Any]:
        """Memeriksa struktur DOM induk dan status frame Turnstile secara mendalam."""
        if not self.enabled or not self.page:
            return {}

        now = time.time()
        if now - self.last_diagnostic_time < 3.5:
            return {}
        self.last_diagnostic_time = now

        info: Dict[str, Any] = {
            "trigger": trigger,
            "url": getattr(self.page, "url", ""),
            "frames_total": len(self.page.frames),
            "cf_frames": [],
            "parent_has_container": False,
            "parent_token_len": 0,
            "parent_blocked_msg": None,
        }

        try:
            parent_dom = self.page.evaluate("""() => {
                const tok = document.querySelector("[name='cf-turnstile-response']");
                const cont = document.querySelector(".cf-turnstile, [data-sitekey], #turnstile-container");
                const ifr = document.querySelector("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']");
                const blocked = document.querySelector(".step-blocked, .alert-danger");
                let ifrBox = null;
                if (ifr) {
                    const r = ifr.getBoundingClientRect();
                    ifrBox = {
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                        visible: (r.width > 0 && r.height > 0)
                    };
                }
                return {
                    hasContainer: !!cont,
                    sitekey: cont ? cont.getAttribute("data-sitekey") : null,
                    tokenLen: tok ? (tok.value || "").length : 0,
                    iframeBox: ifrBox,
                    blockedMsg: blocked ? blocked.innerText.trim() : null,
                };
            }""")
            info.update(parent_dom)
        except Exception as e:
            info["parent_eval_error"] = str(e)

        for idx, frame in enumerate(self.page.frames):
            f_url = (frame.url or "").lower()
            if "challenges.cloudflare.com" in f_url or "turnstile" in f_url:
                frame_detail: Dict[str, Any] = {
                    "index": idx,
                    "url": frame.url[:90],
                    "name": frame.name,
                }
                if frame.url[:90] not in self.cf_frames_detected:
                    self.cf_frames_detected.append(frame.url[:90])
                try:
                    frame_dom = frame.evaluate("""() => {
                        const bodyText = document.body ? document.body.innerText.trim() : "";
                        const checkbox = document.querySelector('input[type="checkbox"]');
                        const stage = document.getElementById("challenge-stage");
                        const fail = document.querySelector("#fail-state, .error-text, #challenge-error-title, .ctp-error");
                        const success = document.querySelector("#success-state, .ctp-success");
                        const spinner = document.querySelector("#spinner, .ctp-spinner, #loading-stage");
                        return {
                            bodyText: bodyText.substring(0, 100),
                            hasCheckbox: !!checkbox,
                            checkboxVisible: checkbox ? checkbox.offsetParent !== null : false,
                            hasStage: !!stage,
                            hasFailState: !!fail,
                            failText: fail ? fail.innerText.trim() : null,
                            hasSuccessState: !!success,
                            hasSpinner: !!spinner,
                        };
                    }""")
                    frame_detail.update(frame_dom)
                except Exception as ef:
                    frame_detail["eval_error"] = str(ef)

                info["cf_frames"].append(frame_detail)

        logger.info(
            f"{self.tag}🔍 [ERRORLOGS:Diagnose - {trigger}] "
            f"Container: {info.get('hasContainer')} | Sitekey: {info.get('sitekey')} | "
            f"TokenLen: {info.get('tokenLen')} | CF Frames: {len(info.get('cf_frames', []))}"
        )
        if info.get("iframeBox"):
            ibox = info["iframeBox"]
            logger.info(f"{self.tag}   🖼️ Turnstile Iframe Box: {ibox['width']}x{ibox['height']} (x:{ibox['x']}, y:{ibox['y']}) | Visible: {ibox['visible']}")
        for cf in info.get("cf_frames", []):
            txt = cf.get("bodyText", "").replace("\n", " ")
            logger.info(f"{self.tag}   🎯 CF Frame #{cf.get('index')}: '{txt[:50]}' | Checkbox: {cf.get('hasCheckbox')} | FailState: {cf.get('hasFailState')}")
            if cf.get("hasFailState") and cf.get("failText"):
                logger.error(f"{self.tag}   🚨 CF TURNSTILE ERROR: '{cf.get('failText')}'")

        return info

    def capture_artifacts(self, page: Any, reason: str = "error") -> None:
        """Menyimpan screenshot visual dan dump DOM saat terjadi kendala Turnstile."""
        if not self.enabled or not page:
            return
        try:
            os.makedirs("data/errorlogs", exist_ok=True)
            ts = int(time.time())
            scr_path = f"data/errorlogs/safelink_turnstile_{reason}_{ts}.png"
            html_path = f"data/errorlogs/safelink_turnstile_{reason}_{ts}.html"

            page.screenshot(path=scr_path, full_page=True)
            self.saved_artifacts.append(scr_path)

            html_content = page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            self.saved_artifacts.append(html_path)

            logger.info(f"{self.tag}📸 [ERRORLOGS] Screenshot tersimpan: {scr_path}")
            logger.info(f"{self.tag}📄 [ERRORLOGS] HTML DOM tersimpan : {html_path}")
        except Exception as e:
            logger.debug(f"{self.tag}Gagal capture artifact: {e}")

    def print_summary(self, tag: str = "") -> None:
        """Mencetak laporan ringkasan penyebab utama kegagalan Turnstile."""
        if not self.enabled:
            return

        print("\n" + "=" * 75)
        print(f"📋 {tag}LAPORAN DIAGNOSTIK KEGAGALAN CLOUDFLARE TURNSTILE (--errorlogs)")
        print("=" * 75)
        print(f"• Proksi Digunakan    : {self.proxy_info}")
        print(f"• Frame CF Terdeteksi : {len(self.cf_frames_detected)} frame ({', '.join(self.cf_frames_detected) or 'Tidak Ada'})")
        print(f"• Upaya Klik Dilakukan: {len(self.click_attempts)} kali")

        print("\n🔎 KEMUNGKINAN AKAR MASALAH DI GOOGLE COLAB:")
        if self.proxy_info == "direct" or "direct" in str(self.proxy_info).lower():
            print("  🚨 1. IP GOOGLE DATACENTER (COLAB):")
            print("        Sesi dijalankan TANPA PROXY residensial (IP bawaan Google Colab AS15169).")
            print("        Cloudflare Turnstile secara otomatis MEMBLOKIR atau memberi score bot 100% pada IP Datacenter.")
            print("        -> SOLUSI: Selalu tambahkan flag `--proxy` agar bot menggunakan IP Residential dari Supabase.")
        else:
            print(f"  🌐 1. IP Residential Terpakai: {self.proxy_info}")
            print("        Jika tetap gagal, kemungkinan IP residensial tersebut sudah masuk blacklist Cloudflare.")

        if not self.cf_frames_detected:
            print("  ⚠️  2. IFRAME TURNSTILE TIDAK DIMUAT:")
            print("        Domain `challenges.cloudflare.com` tidak berhasil ter-render di dalam browser.")
            print("        -> Kemungkinan koneksi timeout, terblokir DNS, atau CSP halaman membatalkan request.")
        else:
            print("  🧩 2. IFRAME TURNSTILE TERMUAT TETAPI TERTUTUP/GAGAL VERIFIKASI:")
            print("        Turnstile muncul tetapi tidak menghasilkan token `cf-turnstile-response`.")
            print("        -> Biasanya karena Turnstile mendeteksi atribut headless atau mouse event dicurigai sebagai bot.")

        if self.page_errors:
            print(f"\n💥 JavaScript Page Errors ({len(self.page_errors)}):")
            for pe in self.page_errors[-3:]:
                print(f"   • {pe}")

        if self.console_logs:
            print(f"\n📝 Console Messages Relevan ({len(self.console_logs)}):")
            for cl in self.console_logs[-6:]:
                print(f"   • {cl}")

        if self.failed_requests:
            print(f"\n🌐 Network Requests Gagal ({len(self.failed_requests)}):")
            for fr in self.failed_requests[-4:]:
                print(f"   • {fr.get('method')} {fr.get('url')} -> {fr.get('failure')}")

        if self.saved_artifacts:
            print(f"\n📁 Bukti Visual Screenshot & HTML Tersimpan:")
            for art in self.saved_artifacts:
                print(f"   • {art}")
            print("   👉 Di Google Colab, Anda dapat menampilkan gambar langsung dengan:")
            print(f"      from IPython.display import Image; display(Image('{self.saved_artifacts[0]}'))")

        print("=" * 75 + "\n", flush=True)


def try_solve_turnstile(page: Any, tag: str = "", diag: Optional[TurnstileDiagnostics] = None) -> bool:
    """Mencari iframe Cloudflare Turnstile resmi dan mengklik checkbox jika perlu konfirmasi manusia."""
    found_cf_frame = False
    try:
        for idx, frame in enumerate(page.frames):
            f_url = (frame.url or "").lower()
            # HANYA interaksi dengan frame resmi Cloudflare Turnstile, JANGAN sentuh iframe iklan
            if "challenges.cloudflare.com" in f_url or "turnstile" in f_url:
                found_cf_frame = True
                if diag:
                    diag.log_click_attempt(f"Iframe Turnstile terdeteksi (Frame #{idx}: {frame.url[:70]})")

                # Cek apakah ada status failure/error langsung di dalam frame
                try:
                    fail_el = frame.locator('#fail-state, .error-text, #challenge-error-title, .ctp-error')
                    if fail_el.count() > 0 and fail_el.first.is_visible():
                        err_text = fail_el.first.inner_text()
                        logger.error(f"{tag}🚨 [Turnstile Fail-State] Frame menampilkan status error: '{err_text}'")
                        if diag:
                            diag.log_click_attempt(f"Turnstile FAIL-STATE: '{err_text}'")
                except Exception:
                    pass

                for sel in [
                    'input[type="checkbox"]',
                    '.ctp-checkbox-label',
                    '#challenge-stage input',
                    '#challenge-stage',
                    'span.mark',
                    '.ctp-checkbox-anchor',
                ]:
                    try:
                        loc = frame.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            loc.first.click(timeout=1500)
                            logger.info(f"{tag}👉 Checkbox Turnstile diklik di frame via {sel}")
                            if diag:
                                diag.log_click_attempt(f"Checkbox diklik via locator '{sel}'")
                            return True
                    except Exception as e_click:
                        if diag:
                            diag.log_click_attempt(f"Locator '{sel}' gagal: {e_click}")
                        continue

        # Fallback: Klik berdasarkan koordinat bounding box iframe di halaman induk
        try:
            ifr = page.query_selector('iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"]')
            if ifr and ifr.is_visible():
                box = ifr.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    click_x = box["x"] + 28
                    click_y = box["y"] + (box["height"] / 2)
                    page.mouse.click(click_x, click_y)
                    logger.info(f"{tag}👉 Fallback klik koordinat kotak Turnstile: ({int(click_x)}, {int(click_y)})")
                    if diag:
                        diag.log_click_attempt(f"Fallback coordinate click pada ({int(click_x)}, {int(click_y)})")
                    return True
        except Exception as e_coord:
            if diag:
                diag.log_click_attempt(f"Fallback coordinate click gagal: {e_coord}")

    except Exception as e:
        if diag:
            diag.log_click_attempt(f"try_solve_turnstile error: {e}")

    if diag and not found_cf_frame:
        diag.log_click_attempt("Tidak ada frame challenges.cloudflare.com yang ditemukan saat pengecekan.")

    return False


def run_single_attempt(
    target_url: str,
    headless: bool,
    proxy_data: Optional[Dict[str, Any]],
    max_timeout_sec: int,
    worker_id: int = 1,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    errorlogs: bool = False,
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
    camoufox_opts["disable_coop"] = True
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
        proxy_desc = f"{proxy_data.get('host')}:{proxy_data.get('port')} ({proxy_data.get('country')})" if proxy_data else "direct (Google Colab / Local IP)"
        diag = TurnstileDiagnostics(main_page, tag=tag, worker_id=worker_id, enabled=errorlogs, proxy_info=proxy_desc)
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
                    if elapsed_cf >= 4.0 and int(elapsed_cf) % 5 == 0:
                        try_solve_turnstile(main_page, tag=tag, diag=diag)
                    if diag and int(elapsed_cf) % 10 == 0:
                        diag.inspect_turnstile_state(trigger=f"wait_{int(elapsed_cf)}s")
                    if elapsed_cf > 25.0 and int(elapsed_cf) % 25 == 0 and diag:
                        diag.capture_artifacts(main_page, reason=f"wait_{int(elapsed_cf)}s")
                    if proxy_data and elapsed_cf > 65.0:
                        logger.warning(f"{tag}⚠️ Turnstile tertahan > 65 detik pada proksi ini. Merotasi proksi...")
                        if diag:
                            diag.capture_artifacts(main_page, reason="proxy_turnstile_timeout_65s")
                            diag.print_summary(tag)
                        break
                    elif not proxy_data and elapsed_cf > 45.0:
                        logger.warning(f"{tag}⚠️ Turnstile tertahan > 45 detik pada Direct IP (Colab). Kemungkinan terblokir Cloudflare.")
                        if diag:
                            diag.capture_artifacts(main_page, reason="direct_colab_blocked_45s")
                            diag.print_summary(tag)
                        break
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

        if not result["success"]:
            logger.warning(f"{tag}⚠️ Batas waktu tunggu tercapai sebelum tujuan akhir terdeteksi.")
            if diag:
                diag.capture_artifacts(main_page, reason="session_incomplete")
                diag.print_summary(tag)
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
    errorlogs: bool = False,
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
            errorlogs=errorlogs,
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
                errorlogs=errorlogs,
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
    errorlogs = bool(config.get("errorlogs", False))
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
                errorlogs=errorlogs,
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
    parser.add_argument(
        "--errorlogs",
        "--error-logs",
        "-e",
        action="store_true",
        dest="errorlogs",
        help="Aktifkan logging diagnostik mendalam untuk menyelidiki kegagalan Cloudflare Turnstile (khususnya di Google Colab / VPS)",
    )
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
    print(f"🔍  Error Logs   : {args.errorlogs}")

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
            errorlogs=args.errorlogs,
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
