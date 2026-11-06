#!/usr/bin/env python3
"""
automation.move2link.flow
Workflow automasi penuh untuk shortlink Move2link (https://move2link.co/...)
menggunakan Camoufox Anti-Detect Browser.

Mekanisme yang ditangani secara otomatis:
1. Cloudflare Managed Challenge & Turnstile solver pada gateway move2link.co.
2. Penanganan popup tab iklan (Popunder Monetag / Adsterra & Shopee promo).
3. Penutupan modal awal ("Sebelum melanjutkan" -> "Lanjutkan").
4. Penanganan overlay ad vignette ("Before you go").
5. Eksekusi alur stepper 3-langkah (Step 1/3, 2/3, 3/3):
   - Deteksi tombol aksi: 'Continue Here', 'I\'m not a robot', 'Continue', 'Open',
     'Tap Here', 'Get Link', 'Go', 'Continue to Destination'.
   - Penanganan jeda countdown ('Waiting X seconds...', 'Scanning destination link...').
   - Pemenuhan tab visibility & impression cookie ('imps').
6. Redirect mulus hingga mencapai URL tujuan akhir asli.
"""

import argparse
import json
import logging
import os
import random
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

try:
    from automation.engine import build_camoufox_kwargs, resolve_geo_profile
except ImportError:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    try:
        from automation.engine import build_camoufox_kwargs, resolve_geo_profile
    except ImportError:
        def build_camoufox_kwargs(**kwargs):
            return {"headless": kwargs.get("headless", False), "humanize": True}
        def resolve_geo_profile(proxy_data):
            return {}

try:
    from core.proxy_manager import (
        acquire_proxy,
        release_proxy,
        record_target_usage,
        report_failure,
        get_proxy_by_index,
    )
except ImportError:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    from core.proxy_manager import (
        acquire_proxy,
        release_proxy,
        record_target_usage,
        report_failure,
        get_proxy_by_index,
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("move2link")

# Daftar kata kunci tombol aksi resmi dari shortlink engine
ACTION_BUTTON_KEYWORDS = [
    "Continue Here",
    "I'm not a robot",
    "Continue",
    "Next",
    "Open",
    "Tap Here",
    "Get Link",
    "Go",
    "Continue to Destination",
    "Download now!",
    "Teruskan",
    "Keep Going",
]


def _emit(callback: Optional[Callable[[str, Dict[str, Any]], None]], event_type: str, **kwargs: Any) -> None:
    if callback:
        try:
            callback(event_type, kwargs)
        except Exception:
            pass


def check_turnstile_status(page: Any) -> Dict[str, Any]:
    """Mengecek status Turnstile apakah token sudah terbit atau widget aktif."""
    try:
        return page.evaluate("""() => {
            const tokenEl = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
            const hasToken = !!(tokenEl && tokenEl.value && tokenEl.value.trim().length > 10);
            const tokenValue = hasToken ? tokenEl.value.substring(0, 20) + '...' : null;
            
            const iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src || '');
            const hasTurnstileIframe = iframes.some(src => 
                src.includes('challenges.cloudflare.com') || src.includes('turnstile') || src.includes('captcha')
            );
            const container = !!document.querySelector('.cf-turnstile, #cf-turnstile, [data-sitekey], div[class*="turnstile"]');
            
            return {
                solved: hasToken,
                token_preview: tokenValue,
                has_iframe: hasTurnstileIframe,
                has_container: container
            };
        }""")
    except Exception as e:
        return {"solved": False, "error": str(e), "has_iframe": False, "has_container": False}


def solve_cloudflare_turnstile(page: Any, max_wait_sec: float = 35.0) -> bool:
    """Mendeteksi dan menyelesaikan Cloudflare Turnstile pada gateway move2link."""
    logger.info("🛡️ Memeriksa Cloudflare Turnstile pada gateway...")
    start_time = time.time()

    status = check_turnstile_status(page)
    if status.get("solved"):
        logger.info(f"✨ Turnstile sudah terverifikasi! (Token: {status.get('token_preview')})")
        return True

    while time.time() - start_time < max_wait_sec:
        # Cek apakah sudah redirect keluar dari move2link.co
        if "move2link.co" not in page.url and "Just a moment" not in page.title():
            logger.info(f"✨ Challenge Cloudflare selesai! URL dialihkan: {page.url}")
            return True

        status = check_turnstile_status(page)
        if status.get("solved"):
            logger.info(f"✨ Cloudflare Turnstile BERHASIL dilewati! (Token: {status.get('token_preview')})")
            return True

        clicked = False

        # 1. Periksa frame untuk checkbox Turnstile
        for frame in page.frames:
            f_url = (frame.url or "").lower()
            if "challenges.cloudflare.com" in f_url or "turnstile" in f_url or "captcha" in f_url:
                for sel in [
                    'input[type="checkbox"]',
                    '.ctp-checkbox-label',
                    '#challenge-stage input',
                    '#challenge-stage',
                    '#cf-stage',
                    'span.mark',
                    'label',
                    'body',
                ]:
                    try:
                        loc = frame.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            loc.first.click(timeout=1500)
                            logger.info(f"👉 Checkbox Turnstile diklik via {sel}")
                            clicked = True
                            break
                    except Exception:
                        continue

                # Fallback klik koordinat bounding box di main page
                if not clicked:
                    try:
                        for ifr_sel in [
                            'iframe[src*="challenges.cloudflare.com"]',
                            'iframe[src*="turnstile"]',
                            'iframe#captcha-iframe',
                        ]:
                            ifr = page.query_selector(ifr_sel)
                            if ifr and ifr.is_visible():
                                box = ifr.bounding_box()
                                if box:
                                    page.mouse.click(box["x"] + 28, box["y"] + (box["height"] / 2))
                                    clicked = True
                                    break
                    except Exception:
                        pass

                if clicked:
                    page.wait_for_timeout(2000)
                    break

        # 2. Cek container turnstile di parent DOM
        if not clicked:
            for parent_sel in [".cf-turnstile", "#cf-turnstile", "[data-sitekey]", 'div[class*="turnstile"]']:
                try:
                    el = page.query_selector(parent_sel)
                    if el and el.is_visible():
                        box = el.bounding_box()
                        if box:
                            page.mouse.click(box["x"] + 28, box["y"] + (box["height"] / 2))
                            clicked = True
                            page.wait_for_timeout(2000)
                            break
                except Exception:
                    pass

        page.wait_for_timeout(1000)

        # Cek kembali apakah sudah solved
        status = check_turnstile_status(page)
        if status.get("solved"):
            logger.info("✨ Cloudflare Turnstile berhasil dilewati!")
            return True

        is_cf_page = "move2link.co" in page.url or "Just a moment" in page.title()
        if not is_cf_page and not status.get("has_iframe") and not status.get("has_container") and (time.time() - start_time > 12.0):
            logger.info("ℹ️ Sudah keluar dari challenge Cloudflare.")
            return True

    logger.warning("⚠️ Batas waktu tunggu Turnstile berakhir.")
    return False


def run_move2link_session(
    target_url: str = "https://move2link.co/bf8598f",
    headless: bool = False,
    proxy_data: Optional[Dict[str, Any]] = None,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    max_timeout_sec: int = 180,
) -> Dict[str, Any]:
    """
    Menjalankan alur penuh shortlink Move2link sampai mencapai URL tujuan asli.
    """
    logger.info(f"🚀 Memulai alur Move2link: {target_url}")
    logger.info(f"🖥️ Mode headless: {headless}")

    geo_profile = resolve_geo_profile(proxy_data) if proxy_data else {}
    locale = geo_profile.get("locale") or "id-ID"
    timezone_id = geo_profile.get("timezone") or "Asia/Jakarta"

    if proxy_data:
        p_info = f"{proxy_data.get('country', 'Unknown')} ({proxy_data.get('host')}:{proxy_data.get('port')})"
        logger.info(f"🌐 Proxy Aktif: {p_info} | IP: {proxy_data.get('ip_detected', 'N/A')} | Locale: {locale} | Timezone: {timezone_id}")
        _emit(event_callback, "proxy_info", proxy=p_info, locale=locale, timezone=timezone_id)
    else:
        logger.info("🌐 Menggunakan Direct Connection (Lokal)")

    camoufox_opts = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=True,
        allow_ads=True,
    )

    popups_opened: List[str] = []
    result: Dict[str, Any] = {
        "success": False,
        "initial_url": target_url,
        "final_url": "",
        "steps_completed": 0,
        "popups_handled": 0,
        "elapsed_seconds": 0.0,
        "proxy": proxy_data.get("id") or proxy_data.get("host") if proxy_data else "direct",
    }

    start_time = time.time()

    with Camoufox(**camoufox_opts) as browser:
        context_opts: Dict[str, Any] = {
            "viewport": camoufox_opts.get("viewport", {"width": 1366, "height": 768}),
            "locale": locale,
            "timezone_id": timezone_id,
        }
        if camoufox_opts.get("user_agent"):
            context_opts["user_agent"] = camoufox_opts["user_agent"]

        context = browser.new_context(**context_opts)
        main_page = context.new_page()

        # Listener tab iklan popunder otomatis: beri waktu dwell 2-3 detik lalu tutup
        def on_popup(popup: Any) -> None:
            if popup != main_page:
                p_url = popup.url or "about:blank"
                if p_url not in popups_opened:
                    popups_opened.append(p_url)
                logger.info(f"🪟 Iklan Popunder / Tab baru: {p_url[:80]}...")
                _emit(event_callback, "popup_detected", url=p_url)

        context.on("page", on_popup)

        try:
            # 1. Buka halaman Move2link
            logger.info(f"🌐 1. Membuka link shortlink: {target_url}...")
            _emit(event_callback, "step", name="GATEWAY_NAVIGATE", url=target_url)
            main_page.goto(target_url, timeout=45000, wait_until="domcontentloaded")

            # 2. Selesaikan Cloudflare Turnstile
            _emit(event_callback, "step", name="SOLVE_TURNSTILE")
            turnstile_ok = solve_cloudflare_turnstile(main_page, max_wait_sec=35.0)

            # 3. Tunggu redirect ke halaman artikel perantara (Siendu)
            logger.info("⏳ 2. Menunggu redirect ke halaman gateway artikel...")
            for _ in range(35):
                time.sleep(1)
                if "siendu.com" in main_page.url:
                    logger.info(f"🎯 Mendarat di Siendu: {main_page.url}")
                    break

            main_page.wait_for_timeout(3000)

            # 4. Loop Stepper Shortlink (Langkah 1/3, 2/3, 3/3 -> Tujuan Akhir)
            logger.info("🔄 3. Menjalankan interaksi tahapan stepper...")
            loop_start = time.time()
            steps_seen = set()

            while time.time() - loop_start < max_timeout_sec:
                time.sleep(1.2)
                curr_url = main_page.url

                # Tutup tab popup iklan secara aman di main thread tanpa greenlet error
                if len(context.pages) > 1:
                    for p in list(context.pages):
                        if p != main_page:
                            try:
                                p_url = p.url or "about:blank"
                                if p_url not in popups_opened:
                                    popups_opened.append(p_url)
                                p.close()
                                logger.info(f"🛡️ Menutup tab popup iklan: {p_url[:70]}...")
                            except Exception:
                                pass

                # Cek apakah sudah keluar dari siendu dan move2link (mencapai URL tujuan asli!)
                if (
                    "siendu.com" not in curr_url
                    and "move2link.co" not in curr_url
                    and "about:blank" not in curr_url
                ):
                    logger.info(f"🎉🎉🎉 BERHASIL SAMPAI DI URL TUJUAN ASLI: {curr_url}")
                    result["success"] = True
                    result["final_url"] = curr_url
                    _emit(event_callback, "success", final_url=curr_url)
                    break

                try:
                    # Pastikan cookie imps selalu terisi untuk validasi API backend
                    main_page.evaluate("""() => {
                        if (!document.cookie.includes('imps=')) {
                            const sampleImps = [12400, 8500, 15200];
                            document.cookie = 'imps=' + encodeURIComponent(JSON.stringify(sampleImps)) + '; path=/; domain=.siendu.com';
                        }
                    }""")

                    # A. Tutup modal promo Shopee jika ada
                    main_page.evaluate("""() => {
                        const closeBtn = document.querySelector('button[aria-label="Close"], div[aria-label="Close"]');
                        if (closeBtn && closeBtn.offsetParent !== null) closeBtn.click();
                    }""")

                    # B. Klik modal awal 'Sebelum melanjutkan' (Lanjutkan) atau modal Step 2 'GG Bro!' (Teruskan / Keep Going)
                    modal_action = main_page.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('.fixed button, [role="dialog"] button, button'));
                        const target = btns.find(b => {
                            if (!b.offsetParent) return false;
                            const t = b.innerText.trim();
                            return t.includes('Teruskan') || t.includes('Keep Going') || t.includes('Lanjutkan');
                        });
                        if (target) {
                            const txt = target.innerText.trim();
                            target.click();
                            return txt;
                        }
                        return null;
                    }""")
                    if modal_action:
                        logger.info(f"👉 Modal ditangani: mengklik '{modal_action}'")
                        time.sleep(1.5)

                    # C. Bersihkan overlay iklan vignette / blocker ("Before you go" dll.)
                    main_page.evaluate("""() => {
                        const overlays = Array.from(document.querySelectorAll('div, iframe')).filter(el => {
                            const text = el.innerText || '';
                            return text.includes('Before you go') || text.includes('Outsmart. Outrank');
                        });
                        for (const o of overlays) o.remove();
                    }""")

                    # D. Periksa status step dan tombol aktif
                    state = main_page.evaluate(r"""() => {
                        const paragraphs = Array.from(document.querySelectorAll('p')).map(p => p.innerText.trim());
                        const stepText = paragraphs.find(p => /Step:\s*\d+\s*\/\s*\d+/i.test(p)) || '';
                        const waitText = paragraphs.find(p => /Waiting\s*\d+\s*seconds/i.test(p) || p.includes('Scanning')) || '';
                        
                        const ctaKeywords = [
                            "Continue Here", "I'm not a robot", "Continue", "Open",
                            "Tap Here", "Get Link", "Go", "Continue to Destination",
                            "Download now!", "Teruskan"
                        ];
                        const btns = Array.from(document.querySelectorAll('button')).map(b => ({
                            text: b.innerText.trim(),
                            disabled: b.disabled || b.classList.contains('disabled'),
                            visible: b.offsetParent !== null
                        })).filter(b => b.visible && ctaKeywords.some(kw => b.text.includes(kw)));
                        
                        return {
                            url: window.location.href,
                            step: stepText,
                            wait: waitText,
                            buttons: btns
                        };
                    }""")

                    if state.get("step") and state.get("step") not in steps_seen:
                        steps_seen.add(state.get("step"))
                        logger.info(f"📌 Tahapan terdeteksi: {state.get('step')}")
                        _emit(event_callback, "step_progress", step=state.get("step"))

                    # Jika sedang dalam countdown timer, biarkan berjalan
                    if state.get("wait"):
                        logger.info(f"⏳ Countdown: {state.get('wait')}...")
                        time.sleep(1)
                        continue

                    # Jika tombol aksi tersedia dan tidak disabled, klik!
                    action_btns = state.get("buttons", [])
                    if action_btns:
                        target = action_btns[0]
                        if not target.get("disabled"):
                            logger.info(f"🖱️ Mengklik tombol stepper: '{target.get('text')}'...")
                            main_page.evaluate("""() => {
                                const ctaKeywords = [
                                    "Continue Here", "I'm not a robot", "Continue", "Open",
                                    "Tap Here", "Get Link", "Go", "Continue to Destination",
                                    "Download now!", "Teruskan"
                                ];
                                const btns = Array.from(document.querySelectorAll('button')).filter(b => 
                                    b.offsetParent !== null && !b.disabled && ctaKeywords.some(kw => b.innerText.includes(kw))
                                );
                                if (btns.length > 0) {
                                    btns[0].scrollIntoView({behavior: 'smooth', block: 'center'});
                                    btns[0].click();
                                }
                            }""")
                            time.sleep(2)
                    else:
                        # Scroll bertahap untuk memicu viewability
                        main_page.evaluate("window.scrollBy(0, 350)")

                except Exception as ex:
                    # Tangani navigasi redirect saat evaluate
                    if "Execution context was destroyed" in str(ex):
                        logger.info("🔄 Terdeteksi navigasi perpindahan halaman...")
                        try:
                            main_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                    else:
                        logger.debug(f"Pengecualian minor dalam loop: {ex}")

            result["steps_completed"] = len(steps_seen)
            result["popups_handled"] = len(popups_opened)
            if not result.get("final_url"):
                result["final_url"] = main_page.url

        except Exception as e:
            logger.error(f"❌ Terjadi kesalahan pada flow Move2link: {e}")
            result["error"] = str(e)
        finally:
            result["elapsed_seconds"] = round(time.time() - start_time, 2)

    return result


def parse_proxy_url(proxy_url: str) -> Dict[str, Any]:
    """Parse string URL proxy (misal http://user:pass@host:port) ke dictionary proxy standar."""
    parsed = urlparse(proxy_url)
    return {
        "id": f"custom_{parsed.hostname}_{parsed.port}",
        "proxy_url": proxy_url,
        "host": parsed.hostname,
        "port": parsed.port,
        "username": parsed.username or "",
        "password": parsed.password or "",
        "country": "Custom",
        "ip_detected": parsed.hostname,
    }


def main():
    parser = argparse.ArgumentParser(description="Move2link Full Camoufox Automation Flow")
    parser.add_argument(
        "--url",
        type=str,
        default="https://move2link.co/bf8598f",
        help="Target Move2link URL (default: https://move2link.co/bf8598f)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Jalankan browser dalam mode headless (default: GUI/headed)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Batas waktu maksimal per sesi dalam detik (default: 180s)",
    )
    parser.add_argument(
        "--use-proxy-manager",
        action="store_true",
        help="Otomatis gunakan ProxyManager untuk rotasi proxy residensial ALIVE (1 IP per 24 jam)",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="URL Proxy manual (contoh: http://user:pass@host:port)",
    )
    parser.add_argument(
        "--proxy-index",
        type=int,
        default=None,
        help="Gunakan proxy tertentu berdasarkan index di data/proxies.json",
    )
    parser.add_argument(
        "--target-name",
        type=str,
        default="move2link",
        help="Nama target untuk tracking limit 24 jam di proxies.json (default: move2link)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Jumlah sesi eksekusi berturut-turut dengan rotasi proxy (default: 1)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Lewati verifikasi test network sebelum menjalankan browser",
    )

    args = parser.parse_args()

    total_runs = max(1, args.runs)
    success_count = 0
    fail_count = 0

    print("\n" + "=" * 60)
    print("🦊 CAMOUFOX MOVE2LINK - FULL AUTOMATION SUITE")
    print(f"🔗 Target URL        : {args.url}")
    print(f"🖥️ Mode Browser      : {'Headless' if args.headless else 'GUI (Headed)'}")
    print(f"⏱️ Timeout Per Sesi  : {args.timeout}s")
    print(f"🔄 Total Sesi (Runs) : {total_runs}")
    if args.proxy:
        print(f"🌐 Proxy Mode        : Manual ({args.proxy})")
    elif args.proxy_index is not None:
        print(f"🌐 Proxy Mode        : Index #{args.proxy_index} dari data/proxies.json")
    elif args.use_proxy_manager:
        print(f"🌐 Proxy Mode        : ProxyManager (Auto-Rotate ALIVE Residential, Target: {args.target_name})")
    else:
        print("🌐 Proxy Mode        : Direct (Tanpa Proxy)")
    print("=" * 60 + "\n")

    for run_idx in range(1, total_runs + 1):
        if total_runs > 1:
            print(f"\n--- [ SESI #{run_idx} DARI {total_runs} ] ---")

        selected_proxy = None
        is_acquired = False
        caller_id = f"move2link_{run_idx}_{int(time.time())}"

        if args.proxy:
            selected_proxy = parse_proxy_url(args.proxy)
        elif args.proxy_index is not None:
            selected_proxy = get_proxy_by_index(args.proxy_index)
            if not selected_proxy:
                logger.error(f"❌ Proxy index #{args.proxy_index} tidak ditemukan di proxies.json!")
                break
        elif args.use_proxy_manager:
            logger.info(f"🔍 Mengalokasikan proxy ALIVE dari pool (Target: {args.target_name})...")
            selected_proxy = acquire_proxy(
                caller_id=caller_id,
                exclusive=True,
                verify_alive=not args.no_verify,
                target=args.target_name,
                max_uses_per_day=1,  # 1 IP per 24 jam untuk Move2link
                window_seconds=24 * 3600,
            )
            if not selected_proxy:
                logger.warning("⚠️ Tidak ada proxy ALIVE / Fresh yang tersedia di pool. Menghentikan antrian.")
                break
            is_acquired = True
            logger.info(
                f"✅ Proxy dialokasikan: {selected_proxy.get('id')} | "
                f"Lokasi: {selected_proxy.get('country')} | "
                f"IP: {selected_proxy.get('ip_detected') or selected_proxy.get('host')}"
            )

        try:
            res = run_move2link_session(
                target_url=args.url,
                headless=args.headless,
                proxy_data=selected_proxy,
                max_timeout_sec=args.timeout,
            )

            if res.get("success"):
                success_count += 1
                logger.info(f"🎉 Sesi #{run_idx} BERHASIL mencapai tujuan akhir!")
                if is_acquired and selected_proxy:
                    proxy_id = selected_proxy.get("id") or selected_proxy.get("proxy_url")
                    record_target_usage(proxy_id, target=args.target_name, window_seconds=24 * 3600)
                    logger.info(f"📝 Target usage '{args.target_name}' dicatat untuk {proxy_id} (Limit 24 jam aktif)")
            else:
                fail_count += 1
                logger.warning(f"⚠️ Sesi #{run_idx} GAGAL: {res.get('error') or 'Tidak mencapai halaman akhir'}")
                if is_acquired and selected_proxy and res.get("error"):
                    proxy_id = selected_proxy.get("id") or selected_proxy.get("proxy_url")
                    err_msg = str(res.get("error"))
                    is_proxy_err = any(k in err_msg.lower() for k in ["proxy", "timeout", "connect", "reset", "unreachable"])
                    report_failure(proxy_id, error_message=err_msg, is_proxy_error=is_proxy_err)

        finally:
            if is_acquired and selected_proxy:
                proxy_id = selected_proxy.get("id") or selected_proxy.get("proxy_url")
                release_proxy(proxy_id, caller_id=caller_id)
                logger.info(f"🔓 Proxy {proxy_id} telah dilepaskan kembali ke status IDLE.")

        if run_idx < total_runs:
            pause_sec = random.uniform(3, 7)
            logger.info(f"⏸️ Menunggu {pause_sec:.1f} detik sebelum melanjutkan ke sesi berikutnya...")
            time.sleep(pause_sec)

    print("\n" + "=" * 60)
    print("📊 HASIL AKHIR EKSEKUSI BATCH MOVE2LINK:")
    print(f"Total Dijalankan : {success_count + fail_count} / {total_runs}")
    print(f"Berhasil         : {success_count}")
    print(f"Gagal            : {fail_count}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
