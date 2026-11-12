import os
import sys
import json
import time
import random
import re
import threading
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.proxy_manager import (
    upload_to_supabase,
    get_stats,
    get_proxy_by_index,
    acquire_proxy,
    release_proxy,
    report_failure,
    record_target_hit,
)

try:
    from automation.browser_verifier import verify_browser
except ModuleNotFoundError:
    from browser_verifier import verify_browser

from automation.chain_provider import ChainProxyProvider

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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROXY_FILE = os.path.join(PROJECT_ROOT, "data", "proxies_scrape.txt")

def generate_random_email(domain=DEFAULT_DOMAIN):
    first = random.choice(FIRST_NAMES)
    last = ("." if random.random() < 0.6 else "") + random.choice(LAST_NAMES)
    digits = str(random.randint(100, 9999))
    return f"{first}{last}{digits}@{domain}"


def parse_proxy_file(path: str) -> List[Dict[str, Any]]:
    """Parse file proxy format [scheme://]user:pass@host:port (satu per baris) untuk grabber."""
    items: List[Dict[str, Any]] = []
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError as exc:
        print(f"! File proxy tidak bisa dibaca: {path} ({exc})")
        return items
    with fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            scheme = "http"
            if "://" in line:
                scheme, _, line = line.partition("://")
                scheme = scheme.strip().lower()
                if scheme not in ("http", "https", "socks5"):
                    print(f"! Baris {lineno} scheme tidak didukung: {scheme}")
                    continue
                if scheme == "https":
                    scheme = "http"
            cred, sep, hostport = line.rpartition("@")
            if sep:
                username, _, password = cred.partition(":")
            else:
                username, password = "", ""
                hostport = line
            host, _, port_s = hostport.rpartition(":")
            if not host or not port_s.isdigit():
                print(f"! Baris {lineno} format salah: {line[:60]}")
                continue
            item = {
                "id": f"file#{lineno}",
                "host": host.strip(),
                "port": int(port_s),
                "username": username.strip(),
                "password": password.strip(),
                "proxy_scheme": scheme,
                "country": "",
                "source": "file",
                "connection_type": "residential",
            }
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", host.strip()):
                item["ip_detected"] = host.strip()
            items.append(item)
    return items

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


class CloudflareBlockedError(Exception):
    """Cloudflare Turnstile menolak verifikasi berulang (indikasi kuat exit IP diblokir / reputasi rendah)."""


class ProxyStalledError(Exception):
    """Proxy macet / rate-limited / menolak koneksi — sesi harus dirotasi ke proxy lain."""


class BrowserVerificationError(Exception):
    """Preflight verifier gagal (IP mismatch/leak/fingerprint) — jangan dianggap sesi sukses."""


_PROXY_NAV_ERROR_MARKERS = (
    "NS_ERROR_PROXY_",                # termasuk NS_ERROR_PROXY_TOO_MANY_REQUESTS / AUTHENTICATION
    "ERR_PROXY_",                     # ERR_PROXY_CONNECTION_FAILED dll
    "ERR_TUNNEL_",                    # ERR_TUNNEL_CONNECTION_FAILED
    "tunnel connection failed",
    "tunneling failed",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_TIMED_OUT",
    "NS_ERROR_NET_TIMEOUT",
    "NS_ERROR_CONNECTION_REFUSED",
    "ERR_EMPTY_RESPONSE",
)


def _is_proxy_nav_error(err_text: str) -> bool:
    t = (err_text or "").lower()
    return any(m.lower() in t for m in _PROXY_NAV_ERROR_MARKERS)


_TURNSTILE_FAIL_SELECTOR = '#fail-state, .error-text, #challenge-error-title, .ctp-error, #challenge-error'
_TURNSTILE_FRAME_KEYWORDS = ("challenges.cloudflare.com", "turnstile", "captcha.gologin.com", "captcha")


def _frame_is_turnstile(frame) -> bool:
    f_url = (frame.url or "").lower()
    return any(k in f_url for k in _TURNSTILE_FRAME_KEYWORDS)


def _turnstile_token_value(page):
    """Ambil NILAI token cf-turnstile-response (top page + semua subframe). None jika belum ada."""
    for frame in page.frames:
        try:
            val = frame.evaluate("""() => {
                const el = document.querySelector(
                    'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]'
                );
                return el && el.value && el.value.length > 10 ? el.value : null;
            }""")
            if val:
                return val
        except Exception:
            continue
    return None


def _turnstile_token_present(page) -> bool:
    """Cek token cf-turnstile-response di top page DAN seluruh subframe (termasuk nested)."""
    return _turnstile_token_value(page) is not None


def _reset_turnstile_widgets(page) -> bool:
    """
    Reset widget Turnstile (window.turnstile.reset) di semua frame, atau minimal
    kosongkan nilai token lama. Dipakai saat token lama tidak dipakai form (stale) -
    token yang sudah terpakai/ditolak server tidak akan pernah diterima lagi.
    """
    for frame in page.frames:
        try:
            ok = frame.evaluate("""() => {
                try {
                    if (window.turnstile && typeof window.turnstile.reset === 'function') {
                        window.turnstile.reset();
                        return true;
                    }
                } catch (e) {}
                const inputs = document.querySelectorAll(
                    'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]'
                );
                let cleared = false;
                inputs.forEach(el => { if (el.value) { el.value = ''; cleared = true; } });
                return cleared;
            }""")
            if ok:
                return True
        except Exception:
            continue
    return False


def _signup_error_text(page):
    """Ambil pesan error yang tampil di form signup (validasi / email sudah dipakai / dll)."""
    try:
        return page.evaluate("""() => {
            const sels = '.ant-form-item-explain-error, .ant-form-item-explain, [role="alert"], .error-message, [class*="error" i]';
            for (const el of document.querySelectorAll(sels)) {
                const t = (el.innerText || '').trim();
                if (t && t.length > 3 && t.length < 200 && el.offsetParent !== null) return t;
            }
            return null;
        }""")
    except Exception:
        return None


def _turnstile_fail_text(page):
    """Deteksi fail-state Turnstile (verifikasi ditolak server-side)."""
    for frame in page.frames:
        if "challenges.cloudflare.com" not in (frame.url or "").lower() and "turnstile" not in (frame.url or "").lower():
            continue
        try:
            loc = frame.locator(_TURNSTILE_FAIL_SELECTOR)
            if loc.count() > 0 and loc.first.is_visible():
                return (loc.first.inner_text() or "").strip()[:120]
        except Exception:
            continue
    return None


def _click_turnstile_checkbox(page) -> bool:
    """Satu klik yang presisi ke checkbox Turnstile. Tidak pernah double-klik dalam satu siklus."""
    # 1) Klik elemen checkbox asli di dalam frame Cloudflare (JANGAN klik 'body' - meleset dari checkbox)
    for frame in page.frames:
        f_url = (frame.url or "").lower()
        if "challenges.cloudflare.com" not in f_url and "turnstile" not in f_url:
            continue
        for sel in [
            'input[type="checkbox"]',
            '.ctp-checkbox-label',
            '.ctp-checkbox-anchor',
            '#challenge-stage input',
            'span.mark',
            'label',
        ]:
            try:
                loc = frame.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=1500)
                    print(f"      👉 Checkbox Turnstile diklik via locator ({sel})")
                    return True
            except Exception:
                continue

    # 2) Fallback koordinat: cari iframe challenge di SEMUA frame (termasuk nested di dalam iframe wrapper).
    #    Prioritaskan iframe challenges.cloudflare.com yang sebenarnya sebelum wrapper generik.
    for frame in page.frames:
        try:
            for ifr_sel in [
                'iframe[src*="challenges.cloudflare.com"]',
                'iframe[src*="turnstile"]',
                'iframe[title*="Cloudflare"]',
                'iframe#captcha-iframe',
                'iframe[src*="captcha.gologin.com"]',
            ]:
                loc = frame.locator(ifr_sel)
                if loc.count() == 0:
                    continue
                box = loc.first.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    # Kotak centang berada ~28px dari kiri iframe, di tengah vertikal
                    page.mouse.click(box["x"] + 28, box["y"] + (box["height"] / 2))
                    print(f"      👉 Checkbox Turnstile diklik via koordinat ({ifr_sel})")
                    return True
        except Exception:
            continue
    return False


def solve_cloudflare_turnstile(page, timeout=25, max_clicks=4):
    """
    Mendeteksi dan menyelesaikan Cloudflare Turnstile CAPTCHA secara otomatis.

    Aturan penting agar challenge tidak di-reset terus-menerus:
    - Hanya SATU klik per siklus; tunggu verifikasi selesai (6 detik) sebelum klik lagi.
      State klik/pacing disimpan di objek page sehingga aman walau fungsi dipanggil
      berulang kali dari loop luar (mis. Step 3 yang memanggil tiap 1 detik).
    - Klik hanya saat checkbox tersedia; jangan klik saat widget sedang spinner/verifying.
    - Token diperiksa di semua frame, bukan hanya top page.
    - Fail fast: jika Cloudflare menolak verifikasi berulang (fail-state) atau klik
      melebihi batas, raise CloudflareBlockedError (biasanya IP datacenter diblokir).
    """
    # State persisten per-page: pacing antar klik & penghitung gagal lintas pemanggilan
    state = getattr(page, "_turnstile_state", None)
    if state is None:
        state = {"clicks": 0, "last_click_ts": 0.0, "fail_hits": 0}
        page._turnstile_state = state
    clicks = state["clicks"]
    last_click_ts = state["last_click_ts"]
    fail_hits = state["fail_hits"]
    start_time = time.time()

    def _final_wait(seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if _turnstile_token_present(page):
                print("   ✨ Cloudflare Turnstile berhasil diselesaikan!")
                return True
            page.wait_for_timeout(500)
        return _turnstile_token_present(page)

    while time.time() - start_time < timeout:
        if _turnstile_token_present(page):
            print("   ✨ Cloudflare Turnstile berhasil diselesaikan!")
            state.update({"clicks": 0, "last_click_ts": 0.0, "fail_hits": 0})
            return True

        fail_text = _turnstile_fail_text(page)
        if fail_text:
            fail_hits += 1
            state["fail_hits"] = fail_hits
            print(f"   ⛔ Cloudflare menolak verifikasi Turnstile: '{fail_text}'")
            if fail_hits >= 2:
                raise CloudflareBlockedError(f"Turnstile fail-state: {fail_text}")

        if not any(_frame_is_turnstile(f) for f in page.frames):
            # Tidak ada Turnstile aktif
            return _turnstile_token_present(page)

        if clicks >= max_clicks:
            # Sudah mentok batas klik: beri satu kesempatan verifikasi terakhir, lalu menyerah
            solved = _final_wait(6.0)
            if solved:
                state.update({"clicks": 0, "last_click_ts": 0.0, "fail_hits": 0})
                return True
            raise CloudflareBlockedError(
                f"Turnstile tidak terpecahkan setelah {clicks}x klik "
                "(IP exit kemungkinan diblokir/dipercaya rendah oleh Cloudflare)"
            )

        # Pace klik: minimal jeda 6 detik antar klik (klik terlalu cepat = reset challenge)
        if (time.time() - last_click_ts) >= 6.0:
            if _click_turnstile_checkbox(page):
                clicks += 1
                last_click_ts = time.time()
                state.update({"clicks": clicks, "last_click_ts": last_click_ts})

        page.wait_for_timeout(500)

    return _turnstile_token_present(page)


_browser_launch_lock = threading.Lock()

def grab_gologin_proxies(headless=False, password=DEFAULT_PASSWORD, proxy_item=None, rounds=2, expected_os="windows", skip_verifier=False):
    os.makedirs("data", exist_ok=True)
    
    print("==========================================================================")
    print("🤖 GOLOGIN PROXY TRIAL GRABBER (FAST API + VERIFIED FLOW)")
    print("==========================================================================")
    if proxy_item:
        print("🌐 KONEKSI MENGGUNAKAN PROXY MANAGEMENT:")
        print(f"   • Negara Proxy : {proxy_item.get('country', 'Unknown')}")
        print(f"   • Host Gateway : {proxy_item.get('host')}:{proxy_item.get('port')}")
        print(f"   • Exit IP      : {proxy_item.get('expected_ip') or proxy_item.get('ip_detected') or 'Mendeteksi via Verifier...'}")
        if proxy_item.get("source") == "chain":
            print(f"   • Hop 3xK      : {proxy_item.get('hop_ip')}:{proxy_item.get('hop_port')}")
            print(f"   • Residential  : {proxy_item.get('residential_host')} (id {proxy_item.get('residential_id')})")
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
        "humanize": True,  # Gerakan mouse manusiawi - Turnstile menilai behavioral signals
        "block_webrtc": True,
        "i_know_what_im_doing": True,
        "firefox_user_prefs": {
            "dom.webdriver.enabled": False,
            "marionette.enabled": False,
            "dom.ipc.processCount": 1,
            "browser.sessionstore.resume_from_crash": False,
            "browser.cache.disk.enable": False,
            "media.autoplay.default": 5,
            "media.autoplay.blocking_policy": 2,
        },
    }
    expected_ip = None
    expected_country = None
    expected_asn = None
    expected_isp = None
    allow_ip_rotation = False
    if proxy_item:
        is_chain = (
            proxy_item.get("source") == "chain"
            or bool(proxy_item.get("expected_ip"))
        )
        is_rotating = (
            is_chain
            or bool(proxy_item.get("allow_ip_rotation"))
            or proxy_item.get("connection_type") == "residential"
            or "floppydata" in str(proxy_item.get("host", "")).lower()
        )
        if is_rotating:
            allow_ip_rotation = True
            expected_asn = proxy_item.get("expected_asn") or None
            expected_isp = proxy_item.get("expected_isp") or None
        proxy_scheme = str(proxy_item.get("proxy_scheme") or "http").lower()
        if proxy_scheme not in ("http", "socks5"):
            proxy_scheme = "http"
        proxy_config = {
            "server": f"{proxy_scheme}://{proxy_item['host']}:{proxy_item['port']}",
        }
        # Bridge lokal tidak memakai auth. Proxy langsung tetap memakai kredensial.
        if not is_chain and (proxy_item.get("username") or proxy_item.get("password")):
            proxy_config["username"] = proxy_item.get("username") or ""
            proxy_config["password"] = proxy_item.get("password") or ""
        camoufox_opts["proxy"] = proxy_config
        detected_ip = (
            proxy_item.get("expected_ip")
            or proxy_item.get("ip_detected")
            or proxy_item.get("ip")
        )
        if detected_ip and re.match(r"^\d+\.\d+\.\d+\.\d+$", str(detected_ip)):
            try:
                from camoufox.geolocation import geoip_allowed, load_geoip_config, get_mmdb_path
                geoip_allowed()
                cfg = load_geoip_config()
                ipv4 = get_mmdb_path('ipv4', cfg)
                combined = get_mmdb_path('combined', cfg) if 'combined' in cfg.get('urls', {}) else None
                if (ipv4 and ipv4.exists()) or (combined and combined.exists()):
                    camoufox_opts["geoip"] = str(detected_ip)
                else:
                    camoufox_opts["geoip"] = False
            except Exception:
                camoufox_opts["geoip"] = False
        else:
            camoufox_opts["geoip"] = False

        if proxy_item.get("expected_ip"):
            expected_ip = str(proxy_item["expected_ip"])
        else:
            host = proxy_item.get("host", "")
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
                expected_ip = host

        if is_chain:
            if proxy_item.get("verify_country"):
                expected_country = (
                    proxy_item.get("country")
                    or proxy_item.get("country_code")
                    or None
                )
        else:
            expected_country = None if is_rotating else proxy_item.get("country")

    all_captured_proxies = []

    camoufox_cm = Camoufox(**camoufox_opts)
    with _browser_launch_lock:
        browser = camoufox_cm.__enter__()
        time.sleep(1.2)
    try:
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
                        strict_mode=False,
                        expected_asn=expected_asn,
                        expected_isp=expected_isp,
                        allow_ip_rotation=allow_ip_rotation,
                    )

                    if not verification.is_safe:
                        print("\n❌ BROWSER TIDAK LOLOS VERIFIKASI KEAMANAN:")
                        for iss in verification.issues:
                            print(f"   • {iss}")
                        raise BrowserVerificationError(
                            "; ".join(str(iss) for iss in verification.issues)[:500]
                        )

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
                email_sel = 'input[name="email"], input[placeholder*="email" i], input[type="email"], input[placeholder*="mail" i], input[type="text"]'

                email_found = False
                for attempt in range(1, 4):
                    try:
                        if attempt > 1:
                            print(f"   🔄 [Percobaan {attempt}/3] Reload sign_up (mengatasi koneksi/proxy macet)...", flush=True)
                            page.goto("https://app.gologin.com/sign_up", wait_until="domcontentloaded", timeout=35000)
                        else:
                            page.wait_for_timeout(random.randint(400, 1500))
                            page.goto("https://app.gologin.com/sign_up", wait_until="domcontentloaded", timeout=40000)
                    except Exception as e_nav:
                        if _is_proxy_nav_error(str(e_nav)):
                            # Proxy rate-limited / macet — jangan buang waktu retry di proxy yang sama
                            raise ProxyStalledError(f"Proxy tidak bisa dipakai: {str(e_nav)[:160]}") from e_nav
                        print(f"   ⚠️ Navigasi lambat ({e_nav}), memeriksa form...", flush=True)
                        page.wait_for_timeout(random.randint(1000, 2500))

                    print("   ✍️ Menunggu form pendaftaran GoLogin & Turnstile...", flush=True)
                    solve_cloudflare_turnstile(page, timeout=5)

                    try:
                        page.wait_for_selector(email_sel, timeout=12000)
                        email_found = True
                        break
                    except Exception:
                        solve_cloudflare_turnstile(page, timeout=5)
                        if page.query_selector(email_sel):
                            email_found = True
                            break
                        print("   ⏳ Form belum ter-render (halaman blank/stalled). Mengulang load...", flush=True)

                if not email_found:
                    page.wait_for_selector(email_sel, timeout=25000)

                page.wait_for_timeout(random.randint(300, 900))
                # Ketik email dengan jeda antar karakter (bukan instant fill) -
                # sinyal pengetikan manusiawi membantu skor Turnstile
                page.locator(email_sel).first.press_sequentially(email, delay=random.randint(35, 85))
                
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

                pwd_loc = page.locator('input[type="password"]')
                for i in range(pwd_loc.count()):
                    pwd_loc.nth(i).press_sequentially(password, delay=random.randint(25, 60))
                    page.wait_for_timeout(random.randint(150, 400))

                page.wait_for_timeout(400)
                # Cek apakah ada Cloudflare Turnstile sebelum tombol diklik
                solve_cloudflare_turnstile(page, timeout=6)

                # Token dari step sebelumnya bisa stale (sudah terpakai) - reset agar
                # widget men-generate token segar untuk submit ini
                if _turnstile_token_value(page):
                    _reset_turnstile_widgets(page)
                    page.wait_for_timeout(800)
                    solve_cloudflare_turnstile(page, timeout=6)

                page.click('button:has-text("Create an account")')
                print("   🚀 Tombol 'Create an account' diklik!", flush=True)
                # Cek kembali jika Turnstile muncul sesaat setelah klik
                solve_cloudflare_turnstile(page, timeout=8)

                # -----------------------------------------------------------
                # TAHAP 3: BYPASS ONBOARDING (LANGSUNG MENUJU /PROXY)
                # -----------------------------------------------------------
                print("▶️ [Step 3/4] Menunggu autentikasi & melewati onboarding...", flush=True)
                create_clicks = 0
                last_token_seen = None
                last_submit_ts = 0.0
                last_reset_ts = 0.0
                stuck_on_signup = False
                form_error_hits = 0
                step3_started = time.time()
                step3_deadline = step3_started + 60.0
                last_progress_log = step3_started
                while time.time() < step3_deadline:
                    page.wait_for_timeout(1000)
                    cur_url = page.url
                    if "/quiz" in cur_url or "/download" in cur_url or "/profileList" in cur_url or "/home" in cur_url or "/proxy" in cur_url:
                        print(f"   ⚡ Berhasil autentikasi ({cur_url}), langsung lompat ke /proxy...", flush=True)
                        try:
                            page.goto("https://app.gologin.com/proxy", wait_until="domcontentloaded", timeout=45000)
                        except Exception as e_nav_proxy:
                            if _is_proxy_nav_error(str(e_nav_proxy)):
                                raise ProxyStalledError(f"Proxy tidak bisa dipakai: {str(e_nav_proxy)[:160]}") from e_nav_proxy
                            print(f"   ⚠️ Proxy lambat saat buka /proxy ({e_nav_proxy}), melanjutkan...", flush=True)
                        stuck_on_signup = False
                        break

                    stuck_on_signup = "/sign_up" in cur_url
                    if not stuck_on_signup:
                        continue  # URL transisi (mis. loading) - tunggu

                    form_err = _signup_error_text(page)
                    if form_err:
                        form_error_hits += 1
                        if form_error_hits >= 2:
                            raise CloudflareBlockedError(
                                f"Signup ditolak GoLogin: {form_err} "
                                f"(exit IP {expected_ip or '?'}) - rotasi residential."
                            )
                    else:
                        form_error_hits = 0

                    token_now = _turnstile_token_value(page)

                    # Sudah terlalu banyak percobaan submit → fail fast dengan info error form
                    if create_clicks >= 4:
                        form_err = _signup_error_text(page)
                        raise CloudflareBlockedError(
                            f"Signup gagal: {create_clicks}x submit tidak kunjung lolos "
                            f"({'pesan form: ' + form_err if form_err else 'tanpa pesan error di form'}) "
                            "- token Turnstile ditolak server (exit IP direputasi rendah?)"
                        )

                    if not token_now:
                        has_turnstile = any(_frame_is_turnstile(f) for f in page.frames)
                        if not has_turnstile:
                            has_turnstile = bool(page.query_selector(
                                'iframe[src*="challenges.cloudflare.com"], '
                                'iframe[src*="turnstile"], iframe[src*="captcha"]'
                            ))
                        if has_turnstile:
                            # Belum ada token - selesaikan Turnstile (fail fast jika diblokir)
                            solve_cloudflare_turnstile(page, timeout=6)
                            token_now = _turnstile_token_value(page)
                        elif (time.time() - step3_started) >= 15.0:
                            raise CloudflareBlockedError(
                                "Form signup tidak menghasilkan token Turnstile dan tidak ada "
                                f"widget CAPTCHA; exit IP {expected_ip or '?'} kemungkinan ditolak."
                            )

                    if token_now and token_now != last_token_seen:
                        # Token BARU tersedia → klik Create maks 1x per token
                        try:
                            create_btn = page.query_selector('button:has-text("Create an account")')
                            if create_btn and create_btn.is_visible():
                                create_btn.click()
                                print(f"   🔄 Klik 'Create an account' #{create_clicks + 1} (token Turnstile baru tersedia)...")
                        except Exception:
                            pass
                        create_clicks += 1
                        last_token_seen = token_now
                        last_submit_ts = time.time()
                    elif token_now:
                        # Token SAMA tapi form tidak navigasi → token stale/terpakai:
                        # reset widget agar challenge baru di-generate
                        if (time.time() - last_submit_ts) >= 12.0 and (time.time() - last_reset_ts) >= 5.0:
                            _reset_turnstile_widgets(page)
                            last_reset_ts = time.time()
                            last_token_seen = None
                            print("   ♻️ Reset widget Turnstile (token lama tidak dipakai form)...")

                    if time.time() - last_progress_log >= 10.0:
                        last_progress_log = time.time()
                        print(
                            f"   ⏳ Masih menunggu autentikasi (URL={cur_url}, "
                            f"token={'ada' if token_now else 'belum'}, klik={create_clicks})...",
                            flush=True,
                        )

                if stuck_on_signup:
                    raise CloudflareBlockedError(
                        "Registrasi tetap tertahan di /sign_up (Turnstile tidak kunjung lolos) - "
                        "exit IP kemungkinan diblokir Cloudflare"
                    )

                # -----------------------------------------------------------
                # TAHAP 4: GRAB LIST PROXY DI HALAMAN /PROXY (DENGAN TUNGGU UI)
                # -----------------------------------------------------------
                print("▶️ [Step 4/4] Membuka halaman /proxy dan menunggu UI tabel dimuat penuh...", flush=True)
                if "/proxy" not in page.url:
                    try:
                        page.goto("https://app.gologin.com/proxy", wait_until="domcontentloaded", timeout=45000)
                    except Exception as e_nav_proxy2:
                        if _is_proxy_nav_error(str(e_nav_proxy2)):
                            raise ProxyStalledError(f"Proxy tidak bisa dipakai: {str(e_nav_proxy2)[:160]}") from e_nav_proxy2
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
                    uploaded_count = upload_to_supabase(captured_in_round)
                    print(f"✅ Putaran #{round_idx} sukses! Mendapatkan {len(captured_in_round)} proxy (☁️ {uploaded_count} terupload langsung ke Supabase).")
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
    finally:
        try:
            camoufox_cm.__exit__(None, None, None)
        except Exception:
            pass

    # Selesai seluruh putaran grab (seluruh proxy langsung tersimpan di Supabase)
    if all_captured_proxies:
        print("\n==========================================================================")
        print("🎯 SELESAI SELURUH PUTARAN GRAB!")
        print(f"   - Total proxy baru didapat : {len(all_captured_proxies)}")
        print("☁️ Tersimpan langsung ke database Supabase (proxxies.proxy_list)")
        print("==========================================================================")

    return all_captured_proxies


def run_gologin_harvest_job(
    target_proxies: int = 50,
    concurrency: int = 1,
    rounds: int = 1,
    headless: bool = True,
    direct: bool = False,
    skip_verifier: bool = False,
    proxy_index: Optional[int] = None,
    proxy_file: Optional[str] = DEFAULT_PROXY_FILE,
    proxy_provider: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    chain_provider: Optional[ChainProxyProvider] = None,
    stop_event: Optional[threading.Event] = None,
    on_log: Optional[Callable[[str, str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    unlimited: bool = False,
) -> int:
    """
    Menjalankan background multi-threaded harvester GoLogin trial proxies.
    Dapat dipanggil oleh CLI maupun GUI (PySide6).
    """
    if stop_event is None:
        stop_event = threading.Event()

    def _log(msg: str, style: str = "white"):
        if on_log:
            on_log(msg, style)
        else:
            print(msg, flush=True)

    concurrency = max(1, concurrency)
    is_unlimited = unlimited or (target_proxies <= 0)
    stats_lock = threading.Lock()
    state = {
        "total_added": 0,
        "target": 0 if is_unlimited else target_proxies,
    }

    target_desc = "Tanpa Batas (∞ Looping Continuous)" if is_unlimited else f"{target_proxies} Proxy"
    _log("=" * 65, "cyan")
    _log("🌾 GOLOGIN PROXY HARVESTER (AUTO-ROTATING SESSION)", "bold cyan")
    _log(f"🎯 Target Proxy Baru : {target_desc} | Concurrency: {concurrency} Worker(s)", "white")
    _log(f"🔄 Rasio Grab        : 1 Proxy untuk {rounds}x Grab Akun GoLogin (~{rounds * 5} proxy)", "white")
    _log(f"🖥️ Mode Headless     : {headless}", "white")

    file_items: Optional[List[Dict[str, Any]]] = None
    file_lock = threading.Lock()
    file_idx = [0]
    if proxy_file and proxy_provider is None and chain_provider is None:
        file_items = parse_proxy_file(proxy_file)
        if not file_items:
            _log(f"⚠️ File proxy '{proxy_file}' kosong/tidak ada/format salah. Fallback ke pool Proxy Management.", "yellow")
            file_items = None
        else:
            _log(f"📄 Sumber Proxy      : File {proxy_file} ({len(file_items)} proxy, round-robin)", "white")

    _log("=" * 65, "cyan")

    def _worker_job(worker_id: int):
        proxy_run_count = 0
        while not stop_event.is_set():
            if not is_unlimited:
                with stats_lock:
                    if state["total_added"] >= state["target"]:
                        break

            proxy_run_count += 1
            caller_id = f"gologin_grabber_w{worker_id}_{int(time.time() * 1000)}"
            selected_proxy = None
            is_acquired = False
            chain_session = False
            session_success = False
            session_error: Optional[BaseException] = None
            error_kind = "other"

            if direct:
                _log(f"🌐 [W{worker_id} - Sesi #{proxy_run_count}] Menggunakan Direct IP (Internet Lokal)...", "cyan")
                selected_proxy = None
            elif chain_provider is not None:
                _log(f"🌐 [W{worker_id} - Sesi #{proxy_run_count}] Menyiapkan chain: hop 3xK acak -> residential Supabase...", "cyan")
                selected_proxy = chain_provider.next_proxy()
                if not selected_proxy:
                    if stop_event.is_set():
                        break
                    _log(f"⚠️ [W{worker_id}] Belum ada chain hop/residential yang valid, menunggu 2 detik...", "yellow")
                    time.sleep(2.0)
                    continue
                chain_session = True
                _log(
                    f"🔗 [W{worker_id} - Sesi #{proxy_run_count}] Chain siap: "
                    f"hop {selected_proxy.get('hop_ip')}:{selected_proxy.get('hop_port')} -> "
                    f"residential {selected_proxy.get('residential_host')} "
                    f"(id {selected_proxy.get('residential_id')}) -> "
                    f"exit {selected_proxy.get('expected_ip')} "
                    f"[{selected_proxy.get('country') or '?'} | {selected_proxy.get('latency_ms') or '?'}ms]",
                    "green",
                )
            elif proxy_provider is not None:
                _log(f"🛰️ [W{worker_id} - Sesi #{proxy_run_count}] Mencari 1 proxy Geonode yang hidup & stabil...", "cyan")
                selected_proxy = proxy_provider()
                if not selected_proxy:
                    if stop_event.is_set():
                        break
                    _log(f"⚠️ [W{worker_id}] Belum ada proxy stabil dari Geonode, menunggu 2 detik...", "yellow")
                    time.sleep(2.0)
                    continue
                _log(
                    f"🛰️ [W{worker_id} - Sesi #{proxy_run_count}] Pakai proxy Geonode: "
                    f"{selected_proxy['host']}:{selected_proxy['port']} "
                    f"[{selected_proxy.get('country') or '?'} | {selected_proxy.get('latency_ms') or '?'}ms]",
                    "green",
                )
            elif file_items is not None:
                with file_lock:
                    selected_proxy = file_items[file_idx[0] % len(file_items)]
                    file_idx[0] += 1
                _log(f"📄 [W{worker_id} - Sesi #{proxy_run_count}] Proxy dari file: {selected_proxy['host']}:{selected_proxy['port']} (source=file, bukan pool)", "cyan")
            elif proxy_index is not None:
                selected_proxy = get_proxy_by_index(proxy_index)
                if not selected_proxy:
                    _log(f"⚠️ [W{worker_id}] Proxy index {proxy_index} tidak ditemukan di Proxy Management.", "yellow")
                    break
            else:
                selected_proxy = acquire_proxy(
                    caller_id=caller_id,
                    target="gologin",
                    verify_alive=True,
                    channel="gologin",
                )
                if selected_proxy:
                    is_acquired = True
                    src = "Supabase" if selected_proxy.get("source") == "supabase_rpc" else "Lokal"
                    _log(f"🔍 [W{worker_id} - Sesi #{proxy_run_count}] Acquire proxy: {selected_proxy.get('country')} ({selected_proxy.get('host')}:{selected_proxy.get('port')}) [{src}]", "green")
                else:
                    _log(f"⚠️ [W{worker_id}] Seluruh proxy di pool sedang digunakan atau DEAD. Menunggu 3 detik...", "yellow")
                    time.sleep(3.0)
                    continue

            new_proxies = []
            try:
                new_proxies = grab_gologin_proxies(
                    headless=headless,
                    proxy_item=selected_proxy,
                    rounds=rounds,
                    skip_verifier=skip_verifier,
                )
                session_success = True
                if is_acquired and selected_proxy and not stop_event.is_set():
                    record_target_hit(selected_proxy, target="gologin", channel="gologin")
                with stats_lock:
                    state["total_added"] += len(new_proxies)
                    total_now = state["total_added"]
                target_str = "∞" if is_unlimited else str(state["target"])
                _log(f"📈 [W{worker_id}] PROGRESS HARVEST: +{len(new_proxies)} proxy baru! Total: {total_now}/{target_str}", "bold green")
                if on_progress:
                    on_progress(total_now, 0 if is_unlimited else state["target"])
            except Exception as e:
                session_error = e
                err_text = str(e)
                is_shutdown = stop_event.is_set() or any(
                    hint in err_text.lower()
                    for hint in (
                        "target page, context or browser has been closed",
                        "targetclosed",
                        "browser has been closed",
                        "page has been closed",
                        "operation was canceled",
                        "operation cancelled",
                    )
                )
                if is_shutdown:
                    error_kind = "shutdown"
                    _log(f"⏹️ [W{worker_id}] Sesi dihentikan — health proxy tidak diubah.", "yellow")
                else:
                    is_cf_block = isinstance(e, CloudflareBlockedError)
                    is_stalled = isinstance(e, ProxyStalledError)
                    is_verification = isinstance(e, BrowserVerificationError)
                    if is_cf_block:
                        error_kind = "cloudflare"
                        _log(
                            f"🚫 [W{worker_id}] Cloudflare memblokir exit IP {selected_proxy.get('expected_ip') if selected_proxy else ''} "
                            f"(sesi #{proxy_run_count}): {e} — rotasi ke proxy berikutnya.",
                            "red",
                        )
                    elif is_stalled:
                        error_kind = "stalled"
                        _log(
                            f"🔌 [W{worker_id}] Proxy {selected_proxy.get('host') if selected_proxy else ''} macet/rate-limited "
                            f"(sesi #{proxy_run_count}) — rotasi ke proxy berikutnya.",
                            "yellow",
                        )
                    elif is_verification:
                        error_kind = "verification"
                        _log(
                            f"🛡️ [W{worker_id}] Verifikasi browser gagal (exit IP/leak) "
                            f"(sesi #{proxy_run_count}): {e} — rotasi ke proxy berikutnya.",
                            "red",
                        )
                    else:
                        error_kind = "network" if any(
                            k.lower() in err_text.lower()
                            for k in ["proxy", "timeout", "connection", "reset", "tunnel"]
                        ) else "other"
                        _log(f"⚠️ [W{worker_id}] Terjadi error saat grab pada sesi #{proxy_run_count}: {e}", "red")
                    if is_acquired and selected_proxy:
                        is_proxy_err = is_cf_block or is_stalled or any(
                            k.lower() in err_text.lower() for k in ["proxy", "timeout", "connection", "reset"]
                        )
                        report_failure(
                            selected_proxy,
                            error_message=err_text,
                            is_proxy_error=is_proxy_err,
                            channel="gologin",
                        )
                    elif is_cf_block and selected_proxy and selected_proxy.get("source") == "file":
                        _log(
                            f"   💡 Proxy file {selected_proxy.get('host')}:{selected_proxy.get('port')} tampaknya diblokir "
                            "Cloudflare (IP datacenter). Pertimbangkan untuk menghapus/menggantinya dari daftar.",
                            "yellow",
                        )
            finally:
                if chain_session and selected_proxy and chain_provider is not None:
                    try:
                        chain_provider.finish_session(
                            selected_proxy,
                            success=session_success,
                            error=session_error,
                            error_kind=error_kind,
                        )
                        _log(f"🔓 [W{worker_id}] Chain selesai; lease residential dilepas dan bridge ditutup.", "dim")
                    except Exception as finish_exc:
                        _log(f"⚠️ [W{worker_id}] Gagal finalisasi chain: {finish_exc}", "yellow")
                elif is_acquired and selected_proxy:
                    release_proxy(selected_proxy, caller_id=caller_id, channel="gologin")
                    _log(f"🔓 [W{worker_id}] Proxy {selected_proxy.get('id')} telah dilepaskan kembali ke status IDLE.", "dim")

            if proxy_index is not None:
                break

            time.sleep(2.0 + (worker_id * 0.5))

    threads = []
    for wid in range(1, concurrency + 1):
        t = threading.Thread(target=_worker_job, args=(wid,), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(4.0)

    try:
        while any(t.is_alive() for t in threads) and not stop_event.is_set():
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop_event.set()
        _log("\n🛑 Sesi dihentikan oleh pengguna (Ctrl+C).", "yellow")

    for t in threads:
        t.join(timeout=3.0)

    _log("=" * 65, "cyan")
    _log(f"📊 Total proxy baru yang berhasil terkumpul: {state['total_added']} proxy.", "bold green")
    _log("☁️ Seluruh proxy yang didapat telah langsung diupload ke database Supabase (proxxies.proxy_list).", "bold green")
    _log("=" * 65, "cyan")
    return state["total_added"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GoLogin Trial Proxy Grabber with Verifier Gatekeeper")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless")
    parser.add_argument("-c", "--concurrency", "--workers", dest="concurrency", type=int, default=1, help="Jumlah concurrent workers/browser yang berjalan bersamaan (default: 1)")
    parser.add_argument("-r", "--rounds", type=int, default=2, help="Jumlah putaran grab per proxy (default: 2 putaran = 10 proxy)")
    parser.add_argument("-t", "--target", "--target-proxies", dest="target_proxies", type=int, default=100, help="Target total proxy baru yang dikumpulkan sebelum berhenti (default: 100)")
    parser.add_argument("-u", "--unlimited", action="store_true", help="Jalankan secara terus-menerus tanpa batas (unlimited continuous looping)")
    parser.add_argument("--proxy-index", type=int, default=None, help="Gunakan proxy index tertentu saja dari Proxy Management")
    parser.add_argument("--proxy-file", default=None, help="Override file hop 3xK (default: DB hop_proxy_list, fallback data/proxies_scrape.txt)")
    parser.add_argument("--use-pool", action="store_true", help="Paksa pakai pool Proxy Management saja (tanpa chain)")
    parser.add_argument("--direct", action="store_true", help="Paksa menggunakan Direct IP (Internet Lokal) tanpa proxy")
    parser.add_argument("--skip-verifier", action="store_true", help="Lewati preflight audit (tidak disarankan di mode chain)")
    parser.add_argument("--no-chain", action="store_true", help="Mode lama: pakai isi proxy file langsung tanpa chain residential")

    c = parser.add_argument_group("Proxy chain (default)")
    c.add_argument("--chain-test", action="store_true", help="Tes acquire + probe chain lalu keluar tanpa membuka browser")
    c.add_argument("--hop-tries", type=int, default=3, help="Jumlah hop 3xK acak yang dicoba per sesi (default: 3)")
    c.add_argument("--chain-timeout", type=float, default=15.0, help="Timeout probe/chain dalam detik (default: 15)")
    c.add_argument("--cooldown-seconds", type=int, default=900, help="Durasi COOLDOWN residential (default: 900 detik)")
    c.add_argument("--dead-confirm-hops", type=int, default=2, help="Jumlah hop berbeda yang harus gagal connect ke residential sebelum dihitung DEAD (default: 2)")
    c.add_argument("--chain-verbose", action="store_true", help="Tampilkan detail CONNECT antar hop")

    args = parser.parse_args()

    proxy_file = args.proxy_file or DEFAULT_PROXY_FILE
    proxy_provider = None
    chain_provider = None

    if args.chain_test:
        provider = ChainProxyProvider(
            scrape_file=args.proxy_file or DEFAULT_PROXY_FILE,
            hop_tries=args.hop_tries,
            timeout=args.chain_timeout,
            cooldown_seconds=args.cooldown_seconds,
            dead_confirm_hops=args.dead_confirm_hops,
            verbose=args.chain_verbose,
        )
        item = provider.next_proxy()
        if not item:
            print("Chain test gagal: tidak ada hop/residential yang valid.")
            sys.exit(1)
        print("Chain test OK:")
        print(f"  hop         : {item.get('hop_ip')}:{item.get('hop_port')}")
        print(f"  residential : {item.get('residential_host')} (id {item.get('residential_id')})")
        print(f"  exit ip     : {item.get('expected_ip')} [{item.get('country') or '?'}]")
        print(f"  latency     : {item.get('latency_ms')} ms")
        provider.finish_session(item, success=False, error_kind="test")
        sys.exit(0)

    if args.direct:
        proxy_file = None
    elif args.use_pool:
        proxy_file = None
    elif args.no_chain:
        proxy_file = args.proxy_file or DEFAULT_PROXY_FILE
        print("Mode lama: proxy file langsung tanpa chain residential.")
    else:
        proxy_file = None
        chain_provider = ChainProxyProvider(
            scrape_file=args.proxy_file or DEFAULT_PROXY_FILE,
            hop_tries=args.hop_tries,
            timeout=args.chain_timeout,
            cooldown_seconds=args.cooldown_seconds,
            dead_confirm_hops=args.dead_confirm_hops,
            verbose=args.chain_verbose,
        )
        print(
            "Mode CHAIN default: hop 3xK acak -> residential FloppyData Supabase -> target. "
            f"Hop file: {args.proxy_file or DEFAULT_PROXY_FILE}"
        )

    run_gologin_harvest_job(
        target_proxies=0 if args.unlimited else args.target_proxies,
        concurrency=args.concurrency,
        rounds=args.rounds,
        headless=args.headless,
        direct=args.direct,
        skip_verifier=args.skip_verifier,
        proxy_index=args.proxy_index,
        proxy_file=proxy_file,
        proxy_provider=proxy_provider,
        chain_provider=chain_provider,
        unlimited=args.unlimited,
    )
