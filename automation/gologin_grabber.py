import os
import sys
import json
import time
import random
import re
import threading
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.proxy_manager import (
    append_proxies,
    get_stats,
    get_proxy_by_index,
    acquire_proxy,
    release_proxy,
    report_failure,
)

try:
    from automation.browser_verifier import verify_browser
except ModuleNotFoundError:
    from browser_verifier import verify_browser

from camoufox.sync_api import Camoufox

FIRST_NAMES = [
    "andi", "agus", "arif", "bella", "bayu", "budi", "citra", "dian", "dewi", "dimas",
    "eka", "fajar", "farah", "gilang", "hendra", "indah", "intan", "joko", "kartika", "lina",
    "maya", "nabila", "nadia", "putri", "rahmat", "rina", "rizky", "sari", "sinta", "taufik",
    "tri", "vina", "wahyu", "wulan", "yudi", "yuni", "zahra", "adit", "salsa", "raka"
]

LAST_NAMES = [
    "santoso", "wijaya", "pratama", "hidayat", "saputra", "nugroho", "ramadhan", "permana", "setiawan", "kusuma",
    "maulana", "firmansyah", "susanto", "gunawan", "halim", "rachman", "utami", "lestari", "handayani", "oktaviani",
    "kurniawan", "hartono", "suryana", "ismail", "anggraeni", "purnama", "safitri", "wibowo", "ardianto", "cahyani"
]

DEFAULT_DOMAIN = "riztama.my.id"
DEFAULT_PASSWORD = "Jovan@1224"

def generate_random_email(domain=DEFAULT_DOMAIN):
    first = random.choice(FIRST_NAMES)
    last = ("." if random.random() < 0.6 else "") + random.choice(LAST_NAMES)
    digits = str(random.randint(100, 9999))
    return f"{first}{last}{digits}@{domain}"

def extract_proxies_from_api_data(data):
    """
    Ekstrak data proxy dari respon API GoLogin (JSON endpoint /proxy/v2).
    Format yang didapat mencakup host, port, username, password, dan country.
    """
    proxies = []
    items = []
    if isinstance(data, dict):
        if "proxies" in data and isinstance(data["proxies"], list):
            items = data["proxies"]
        elif "data" in data and isinstance(data["data"], list):
            items = data["data"]
    elif isinstance(data, list):
        items = data

    for item in items:
        if isinstance(item, dict):
            host = item.get("host")
            port = item.get("port")
            username = item.get("username", "")
            password = item.get("password", "")
            if host and port and username and password:
                country = item.get("customName") or item.get("country") or ("Residential (FloppyData)" if "geo.floppydata.com" in str(host) else "Unknown")
                connection_type = item.get("mode") or "residential"
                if connection_type == "geolocation":
                    connection_type = "residential"
                proxy_url = f"http://{username}:{password}@{host}:{port}"
                proxies.append({
                    "country": country,
                    "connection_type": connection_type,
                    "host": host,
                    "port": int(port),
                    "username": username,
                    "password": password,
                    "proxy_url": proxy_url
                })
    return proxies

def click_top_right_x(page):
    try:
        page.keyboard.press("Escape")
        page.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll("button, svg, path, div, span, a"));
            for (const el of elements) {
                const rect = el.getBoundingClientRect();
                if (rect.top >= 0 && rect.top < 120 && rect.right > (window.innerWidth - 120) && rect.width > 5 && rect.height > 5) {
                    const btn = el.closest("button") || el;
                    btn.click();
                    return true;
                }
            }
            const modalClose = document.querySelector(".ant-modal-close, button[aria-label='Close']");
            if (modalClose) {
                modalClose.click();
                return true;
            }
            return false;
        }""")
    except Exception:
        pass


def solve_cloudflare_turnstile(page, timeout=10):
    """
    Mendeteksi dan menyelesaikan Cloudflare Turnstile CAPTCHA secara otomatis.
    Jika muncul checkbox Turnstile (di iframe atau container), klik checkbox tersebut.
    """
    def check_is_solved():
        try:
            return page.evaluate("""() => {
                const token = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
                return !!(token && token.value && token.value.length > 10);
            }""")
        except Exception:
            return False

    if check_is_solved():
        return True

    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_is_solved():
            print("   ✨ Cloudflare Turnstile berhasil diselesaikan!")
            return True

        found_turnstile = False

        # 1. Periksa seluruh frame untuk menemukan iframe Turnstile
        for frame in page.frames:
            f_url = (frame.url or "").lower()
            if "challenges.cloudflare.com" in f_url or "turnstile" in f_url or "captcha" in f_url:
                found_turnstile = True
                print("   🧩 Terdeteksi Cloudflare Turnstile! Mencoba mengklik checkbox...")

                # Selector di dalam frame Turnstile
                for sel in [
                    'input[type="checkbox"]',
                    '.ctp-checkbox-label',
                    '#challenge-stage input',
                    '#challenge-stage',
                    '#cf-stage',
                    'span.mark',
                    'label',
                    'body'
                ]:
                    try:
                        loc = frame.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            loc.first.click(timeout=1500)
                            print(f"      👉 Checkbox Turnstile diklik via locator: {sel}")
                            break
                    except Exception:
                        continue

                # Fallback koordinat dari parent frame
                try:
                    for ifr_sel in [
                        'iframe[src*="challenges.cloudflare.com"]',
                        'iframe[src*="turnstile"]',
                        'iframe#captcha-iframe',
                        'iframe[title*="Cloudflare"]',
                        'iframe[src*="captcha.gologin.com"]'
                    ]:
                        ifr = page.query_selector(ifr_sel)
                        if ifr and ifr.is_visible():
                            box = ifr.bounding_box()
                            if box:
                                # Klik di posisi kotak centang (sekitar 30px dari kiri)
                                page.mouse.click(box["x"] + 28, box["y"] + (box["height"] / 2))
                                print(f"      👉 Checkbox Turnstile diklik via koordinat ({ifr_sel})")
                                break
                except Exception:
                    pass

                # Tunggu token selesai diverifikasi
                for _ in range(8):
                    page.wait_for_timeout(500)
                    if check_is_solved():
                        print("   ✨ Cloudflare Turnstile berhasil diselesaikan!")
                        return True
                break

        # 2. Cek apakah ada container turnstile di halaman utama jika tidak terdeteksi via frame
        if not found_turnstile:
            for parent_sel in ['.cf-turnstile', '#cf-turnstile', '[data-sitekey]', 'div[class*="turnstile"]']:
                try:
                    el = page.query_selector(parent_sel)
                    if el and el.is_visible():
                        found_turnstile = True
                        print(f"   🧩 Terdeteksi container Turnstile ({parent_sel}). Mencoba klik...")
                        box = el.bounding_box()
                        if box:
                            page.mouse.click(box["x"] + 28, box["y"] + (box["height"] / 2))
                        break
                except Exception:
                    pass

        if not found_turnstile:
            # Tidak ada Turnstile yang sedang aktif
            break

        page.wait_for_timeout(600)

    return check_is_solved()


def grab_gologin_proxies(headless=False, password=DEFAULT_PASSWORD, proxy_item=None, rounds=2, expected_os="windows", skip_verifier=False):
    os.makedirs("data", exist_ok=True)
    
    print("==========================================================================")
    print("🤖 GOLOGIN PROXY TRIAL GRABBER (FAST API + VERIFIED FLOW)")
    print("==========================================================================")
    if proxy_item:
        print("🌐 KONEKSI MENGGUNAKAN PROXY MANAGEMENT:")
        print(f"   • Negara Proxy : {proxy_item.get('country', 'Unknown')}")
        print(f"   • Host Gateway : {proxy_item.get('host')}:{proxy_item.get('port')}")
        print(f"   • Exit IP      : {proxy_item.get('ip_detected') or 'Mendeteksi via Verifier...'}")
        if proxy_item.get("latency_ms"):
            print(f"   • Latency      : {proxy_item.get('latency_ms')} ms")
        print(f"   • Target Grab  : 1 Proxy untuk {rounds}x Akun GoLogin (Target: {rounds * 5} Proxy)")
    else:
        print("🌐 KONEKSI: Direct IP (Internet Lokal - Fallback)")
        print(f"   • Target Grab  : Direct IP untuk {rounds}x Akun GoLogin (Target: {rounds * 5} Proxy)")
    print(f"🖥️ Mode Headless : {headless}")
    print("==========================================================================\n")

    camoufox_opts = {
        "headless": headless,
        "os": expected_os,
        "humanize": False,
        "i_know_what_im_doing": True,
        "firefox_user_prefs": {
            "dom.webdriver.enabled": False,
            "marionette.enabled": False,
        },
    }
    expected_ip = None
    expected_country = None
    if proxy_item:
        camoufox_opts["proxy"] = {
            "server": f"http://{proxy_item['host']}:{proxy_item['port']}",
            "username": proxy_item["username"],
            "password": proxy_item["password"]
        }
        try:
            from camoufox.geolocation import geoip_allowed
            geoip_allowed()
            camoufox_opts["geoip"] = True
        except Exception:
            camoufox_opts["geoip"] = False
        host = proxy_item.get("host", "")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            expected_ip = host
        is_rotating = (
            proxy_item.get("connection_type") == "residential"
            or "floppydata" in str(host).lower()
        )
        expected_country = None if is_rotating else proxy_item.get("country")

    all_captured_proxies = []

    with Camoufox(**camoufox_opts) as browser:
        for round_idx in range(1, rounds + 1):
            email = generate_random_email()
            print(f"\n--------------------------------------------------------------------------")
            print(f"🚀 [PUTARAN {round_idx}/{rounds}] Memulai Pendaftaran Akun GoLogin #{round_idx}")
            print(f"   📧 Email: {email}")
            print(f"--------------------------------------------------------------------------")

            context = browser.new_context()
            page = context.new_page()
            captured_in_round = []

            try:
                # -----------------------------------------------------------
                # TAHAP 0: PRE-FLIGHT VERIFIER (LAYER 1 GATEKEEPER)
                # -----------------------------------------------------------
                if not skip_verifier:
                    print(f"🛡️ [{round_idx}/{rounds} - Step 0/4] Memverifikasi Keamanan Browser via Core Verifier...")
                    verification = verify_browser(
                        page,
                        expected_ip=expected_ip,
                        expected_os=expected_os,
                        expected_country=expected_country,
                        check_ads=False,
                        strict_mode=False
                    )

                    if not verification.is_safe:
                        print("\n❌ BROWSER TIDAK LOLOS VERIFIKASI KEAMANAN:")
                        for iss in verification.issues:
                            print(f"   • {iss}")
                        print("🚫 Sesi pendaftaran GoLogin dibatalkan demi keamanan!\n")
                        break

                    actual = verification.actual_state
                    print(f"   ✅ Lolos Audit Keamanan! (Score: {verification.score}/100 | Exit IP: {actual.get('ip')} | Negara: {actual.get('country')})\n")
                else:
                    print(f"⏩ [{round_idx}/{rounds} - Step 0/4] Skip Pre-Flight Verifier (Mode Direct Colab)")

                # Intercept semua response API dari api.gologin.com
                captured_from_api = []
                seen_proxy_urls = set()

                def on_response(response):
                    try:
                        url = response.url
                        if "api.gologin.com/proxy" in url.lower() and response.request.resource_type in ["fetch", "xhr"]:
                            content_type = response.headers.get("content-type", "")
                            if "json" in content_type:
                                data = response.json()
                                extracted = extract_proxies_from_api_data(data)
                                if extracted:
                                    for item in extracted:
                                        if item["proxy_url"] not in seen_proxy_urls:
                                            seen_proxy_urls.add(item["proxy_url"])
                                            captured_from_api.append(item)
                    except Exception:
                        pass

                page.on("response", on_response)

                # -----------------------------------------------------------
                # TAHAP 1: INPUT EMAIL & KLIK 'TRY 7 DAYS FOR FREE'
                # -----------------------------------------------------------
                print("▶️ [Step 1/4] Membuka https://app.gologin.com/sign_up ...", flush=True)
                nav_ok = False
                for nav_try in range(1, 3):
                    try:
                        page.goto("https://app.gologin.com/sign_up", wait_until="domcontentloaded", timeout=45000)
                        nav_ok = True
                        break
                    except Exception as e_nav:
                        if nav_try == 2:
                            raise
                        print(f"   ⚠️ Proxy lambat ({e_nav}), mencoba ulang navigasi...", flush=True)
                        time.sleep(2)

                print("   ✍️ Menunggu form pendaftaran GoLogin & Turnstile...", flush=True)
                # Cek jika ada Turnstile yang muncul di awal sebelum form dirender
                solve_cloudflare_turnstile(page, timeout=6)

                # Selector fleksibel: GoLogin menggunakan <input name="email" placeholder="Your email"> (tanpa type="text")
                email_sel = 'input[name="email"], input[placeholder*="email" i], input[type="email"], input[placeholder*="mail" i], input[type="text"]'
                page.wait_for_selector(email_sel, timeout=45000)
                page.fill(email_sel, email)
                
                cb = page.query_selector('input[type="checkbox"]')
                if cb and not cb.is_checked():
                    cb.click()
                    
                print("   🚀 Klik 'Try 7 days for Free'...", flush=True)
                page.click('button:has-text("Try 7 days for Free")')
                solve_cloudflare_turnstile(page, timeout=8)

                # -----------------------------------------------------------
                # TAHAP 2: INPUT DUA PASSWORD & CREATE ACCOUNT
                # -----------------------------------------------------------
                print("▶️ [Step 2/4] Mengisi Password & Create Account...", flush=True)
                page.wait_for_selector('input[type="password"]', timeout=30000)
                
                pwd_inputs = page.query_selector_all('input[type="password"]')
                for p in pwd_inputs:
                    p.fill(password)

                page.wait_for_timeout(400)
                # Cek apakah ada Cloudflare Turnstile sebelum tombol diklik
                solve_cloudflare_turnstile(page, timeout=6)

                page.click('button:has-text("Create an account")')
                print("   🚀 Tombol 'Create an account' diklik!", flush=True)
                # Cek kembali jika Turnstile muncul sesaat setelah klik
                solve_cloudflare_turnstile(page, timeout=8)

                # -----------------------------------------------------------
                # TAHAP 3: BYPASS ONBOARDING (LANGSUNG MENUJU /PROXY)
                # -----------------------------------------------------------
                print("▶️ [Step 3/4] Menunggu autentikasi & melewati onboarding...")
                for sec in range(35):
                    page.wait_for_timeout(1000)
                    cur_url = page.url
                    if "/quiz" in cur_url or "/download" in cur_url or "/profileList" in cur_url or "/home" in cur_url or "/proxy" in cur_url:
                        print(f"   ⚡ Berhasil autentikasi ({cur_url}), langsung lompat ke /proxy...", flush=True)
                        try:
                            page.goto("https://app.gologin.com/proxy", wait_until="domcontentloaded", timeout=45000)
                        except Exception as e_nav_proxy:
                            print(f"   ⚠️ Proxy lambat saat buka /proxy ({e_nav_proxy}), melanjutkan...", flush=True)
                        break

                    # Jika masih tertahan di /sign_up, periksa apakah Cloudflare Turnstile muncul
                    if "/sign_up" in cur_url and sec % 3 == 0:
                        solve_cloudflare_turnstile(page, timeout=3)
                        try:
                            create_btn = page.query_selector('button:has-text("Create an account")')
                            if create_btn and create_btn.is_visible():
                                create_btn.click()
                                print("   🔄 Re-klik 'Create an account' setelah verifikasi Turnstile...")
                        except Exception:
                            pass

                # -----------------------------------------------------------
                # TAHAP 4: GRAB LIST PROXY DI HALAMAN /PROXY (DENGAN TUNGGU UI)
                # -----------------------------------------------------------
                print("▶️ [Step 4/4] Membuka halaman /proxy dan menunggu UI tabel dimuat penuh...", flush=True)
                if "/proxy" not in page.url:
                    try:
                        page.goto("https://app.gologin.com/proxy", wait_until="domcontentloaded", timeout=45000)
                    except Exception as e_nav_proxy2:
                        print(f"   ⚠️ Proxy lambat ({e_nav_proxy2}), melanjutkan...", flush=True)

                # 1. Tunggu sampai tabel UI / baris proxy benar-benar muncul di layar
                print("   ⏳ Menunggu tabel proxy ter-render di UI browser...")
                ui_rows_count = 0
                for _ in range(15):
                    try:
                        ui_rows_count = page.evaluate("""() => {
                            const rows = document.querySelectorAll('.ant-table-row, tr[data-row-key], .proxy-item');
                            return rows ? rows.length : 0;
                        }""")
                        if ui_rows_count > 0:
                            break
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)

                if ui_rows_count > 0:
                    print(f"   🖥️ Terdeteksi {ui_rows_count} baris proxy di tabel UI!")

                # 2. Tunggu respon network API stabil (target minimal 5 proxy atau stabil)
                print("   🔍 Mengumpulkan list proxy dari network API & direct fetch...")
                for _ in range(10):
                    page.wait_for_timeout(600)
                    if len(captured_from_api) >= 5:
                        break

                # 3. Direct API fetch dengan token untuk memastikan seluruh 5 proxy terambil
                try:
                    api_data = page.evaluate("""async () => {
                        try {
                            const token = localStorage.getItem('@gologin:access_token') || localStorage.getItem('token') || localStorage.getItem('accessToken');
                            if (!token) return null;
                            const res = await fetch('https://api.gologin.com/proxy/v2?page=1&perPage=50', {
                                headers: {
                                    'Authorization': 'Bearer ' + token
                                }
                            });
                            if (res.ok) {
                                return await res.json();
                            }
                        } catch(e) {}
                        return null;
                    }""")
                    if api_data:
                        extracted = extract_proxies_from_api_data(api_data)
                        for item in extracted:
                            if item["proxy_url"] not in seen_proxy_urls:
                                seen_proxy_urls.add(item["proxy_url"])
                                captured_from_api.append(item)
                except Exception:
                    pass

                # 4. Trigger UI Copy proxy jika tombol copy tersedia di halaman
                try:
                    page.evaluate("""() => {
                        const selectAll = document.querySelector('input[aria-label="Select all"]');
                        if (selectAll && !selectAll.checked) {
                            const wrapper = selectAll.closest(".ant-checkbox") || selectAll.parentElement;
                            if (wrapper) wrapper.click();
                        }
                    }""")
                    page.wait_for_timeout(400)
                    page.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll("span, button"));
                        const copyBtn = btns.find(el => /^copy proxy$/i.test((el.innerText || "").trim()));
                        if (copyBtn) copyBtn.click();
                    }""")
                except Exception:
                    pass

                for _ in range(6):
                    page.wait_for_timeout(500)
                    if len(captured_from_api) >= 5:
                        break

                captured_in_round = list(captured_from_api)
                print(f"   ⚡ Berhasil menangkap total {len(captured_in_round)} proxy dari akun GoLogin ini!")

                # 5. Beri jeda 5 detik agar user bisa melihat langsung tabel di layar
                print("👀 Menampilkan halaman proxy selama 5 detik agar Anda dapat memeriksa tabel di browser...")
                page.wait_for_timeout(5000)

                if captured_in_round:
                    all_captured_proxies.extend(captured_in_round)
                    print(f"✅ Putaran #{round_idx} sukses! Mendapatkan {len(captured_in_round)} proxy.")
                else:
                    print(f"❌ Putaran #{round_idx} gagal mendapatkan proxy.")
                    page.screenshot(path=f"data/gologin_grab_error_round_{round_idx}.png")
            except Exception as e_round:
                try:
                    os.makedirs("data", exist_ok=True)
                    err_path = f"data/gologin_grab_error_round_{round_idx}.png"
                    page.screenshot(path=err_path)
                    print(f"   📸 Screenshot error disimpan ke: {err_path}")
                except Exception:
                    pass
                raise e_round
            finally:
                context.close()

            # Jeda antar putaran jika masih ada putaran berikutnya
            if round_idx < rounds and captured_in_round:
                print("⏳ Menunggu jeda 3 detik sebelum putaran pendaftaran berikutnya...")
                time.sleep(3)

    # Simpan hasil akumulasi seluruh putaran ke Proxy Management
    if all_captured_proxies:
        added_count = append_proxies(all_captured_proxies)
        stats = get_stats()

        print("\n==========================================================================")
        print("🎯 SELESAI SELURUH PUTARAN GRAB!")
        print(f"   - Total proxy baru didapat : {len(all_captured_proxies)}")
        print(f"   - Proxy baru ditambahkan   : {added_count}")
        print(f"   - Total proxy di database  : {stats['total']}")
        print(f"   - Posisi Cursor Rotasi     : Index #{stats['cursor']}")
        print("💾 Tersimpan persisten melalui Proxy Management (data/proxies.json)")
        print("==========================================================================")

    return all_captured_proxies


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GoLogin Trial Proxy Grabber with Verifier Gatekeeper")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless")
    parser.add_argument("-c", "--concurrency", "--workers", dest="concurrency", type=int, default=1, help="Jumlah concurrent workers/browser yang berjalan bersamaan (default: 1)")
    parser.add_argument("-r", "--rounds", type=int, default=2, help="Jumlah putaran grab per proxy (default: 2 putaran = 10 proxy)")
    parser.add_argument("-t", "--target", "--target-proxies", dest="target_proxies", type=int, default=100, help="Target total proxy baru yang dikumpulkan sebelum berhenti (default: 100)")
    parser.add_argument("--proxy-index", type=int, default=None, help="Gunakan proxy index tertentu saja dari Proxy Management")
    parser.add_argument("--direct", action="store_true", help="Paksa menggunakan Direct IP (Internet Lokal) tanpa proxy")
    parser.add_argument("--skip-verifier", action="store_true", help="Lewati preflight audit (berguna untuk direct IP datacenter Colab)")
    args = parser.parse_args()

    concurrency = max(1, args.concurrency)
    stop_event = threading.Event()
    stats_lock = threading.Lock()
    state = {
        "total_added": 0,
        "target": args.target_proxies,
    }

    print("==========================================================================")
    print("🌾 GOLOGIN PROXY HARVESTER (AUTO-ROTATING SESSION)")
    print(f"🎯 Target Proxy Baru : {args.target_proxies} Proxy")
    print(f"⚡ Concurrency       : {concurrency} Worker(s)")
    print(f"🔄 Rasio Grab        : 1 Proxy untuk {args.rounds}x Grab Akun GoLogin (~{args.rounds * 5} proxy)")
    print(f"🖥️ Mode Headless     : {args.headless}")
    print("==========================================================================\n")

    def _worker_job(worker_id: int):
        proxy_run_count = 0
        while not stop_event.is_set():
            with stats_lock:
                if state["total_added"] >= state["target"]:
                    break

            proxy_run_count += 1
            caller_id = f"gologin_grabber_w{worker_id}_{int(time.time() * 1000)}"
            selected_proxy = None
            is_acquired = False

            if args.direct:
                print(f"🌐 [W{worker_id} - Sesi #{proxy_run_count}] Menggunakan Direct IP (Internet Lokal)...")
                selected_proxy = None
            elif args.proxy_index is not None:
                selected_proxy = get_proxy_by_index(args.proxy_index)
                if not selected_proxy:
                    print(f"⚠️ [W{worker_id}] Proxy index {args.proxy_index} tidak ditemukan di Proxy Management.")
                    break
            else:
                selected_proxy = acquire_proxy(caller_id=caller_id)
                if selected_proxy:
                    is_acquired = True
                    print(f"\n🔍 [W{worker_id} - Sesi #{proxy_run_count}] Acquire proxy: {selected_proxy.get('country')} ({selected_proxy.get('host')}:{selected_proxy.get('port')})")
                else:
                    print(f"⚠️ [W{worker_id}] Seluruh proxy di pool sedang digunakan atau DEAD. Menunggu 3 detik...")
                    time.sleep(3.0)
                    continue

            new_proxies = []
            try:
                new_proxies = grab_gologin_proxies(
                    headless=args.headless,
                    proxy_item=selected_proxy,
                    rounds=args.rounds,
                    skip_verifier=args.skip_verifier,
                )
                with stats_lock:
                    state["total_added"] += len(new_proxies)
                    total_now = state["total_added"]
                print("\n" + "=" * 60)
                print(f"📈 [W{worker_id}] PROGRESS HARVEST: +{len(new_proxies)} proxy baru! Total: {total_now}/{args.target_proxies}")
                print("=" * 60)
            except Exception as e:
                print(f"⚠️ [W{worker_id}] Terjadi error saat grab pada sesi #{proxy_run_count}: {e}")
                if is_acquired and selected_proxy:
                    is_proxy_err = any(k.lower() in str(e).lower() for k in ["proxy", "timeout", "connection", "reset"])
                    report_failure(selected_proxy.get("id") or selected_proxy.get("proxy_url"), error_message=str(e), is_proxy_error=is_proxy_err)
            finally:
                if is_acquired and selected_proxy:
                    release_proxy(selected_proxy.get("id") or selected_proxy.get("proxy_url"), caller_id=caller_id)
                    print(f"🔓 [W{worker_id}] Proxy {selected_proxy.get('id')} telah dilepaskan kembali ke status IDLE.")

            if args.proxy_index is not None:
                break

            time.sleep(2.0)

    threads = []
    for wid in range(1, concurrency + 1):
        t = threading.Thread(target=_worker_job, args=(wid,), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(1.0)

    try:
        while any(t.is_alive() for t in threads) and not stop_event.is_set():
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop_event.set()
        print("\n\n🛑 Sesi dihentikan oleh pengguna (Ctrl+C).")

    for t in threads:
        t.join(timeout=3.0)

    print("\n" + "=" * 60)
    print(f"📊 Total proxy baru yang berhasil terkumpul: {state['total_added']} proxy.")
    print("💾 Seluruh proxy yang didapat telah aman tersimpan di data/proxies.json.")
    print("=" * 60)
