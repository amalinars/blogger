#!/usr/bin/env python3
"""
automation.monetag.flow
Workflow automasi penjelajahan web langsung & impresi iklan Monetag:
- Navigasi web IPRadar / target URL langsung secara natural (bukan shortlink gateway).
- Memicu impresi multi-format: OnClick / Popunder, In-Page Push, dan Vignette.
- Penanganan redirect advertiser landing page secara graceful dengan dwell viewability.
- Dwell Direct Link / Smartlink untuk yield CPM maksimal.
"""

import os
import random
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from automation.engine import WORKER_STARTUP_LOCK, build_camoufox_kwargs, build_camoufox_context_options, resolve_geo_profile
from automation.session import SessionBudget, country_label
from automation.browser_verifier import BrowserVerifier
from automation.monetag.humanizer import human_click, human_move, human_scroll, human_wander
from core.proxy_manager import ProxyManager

_WORKER_BROWSERS: Dict[int, Dict[str, Any]] = {}
_WORKER_BROWSERS_LOCK = threading.Lock()
_MEDIA_EXT_RE = (".mp4", ".webm", ".m3u8", ".mp3", ".ogg", ".wav", ".avi", ".mov")


def close_worker_browser(worker_id: int) -> None:
    """Tutup instance browser Camoufox yang di-cache untuk worker tertentu."""
    with _WORKER_BROWSERS_LOCK:
        entry = _WORKER_BROWSERS.pop(worker_id, None)
    if entry and entry.get("cm"):
        try:
            entry["cm"].__exit__(None, None, None)
        except Exception:
            pass


def _setup_monetag_media_filter(context: Any) -> None:
    """Blokir stream video/audio berat di landing page popunder tanpa menyentuh script/iframe iklan."""
    def _route_handler(route: Any) -> None:
        try:
            req = route.request
            url = (req.url or "").lower().split("?", 1)[0]
            if req.resource_type == "media" or url.endswith(_MEDIA_EXT_RE):
                route.abort()
                return
            route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    try:
        context.route("**/*", _route_handler)
    except Exception:
        pass


@contextmanager
def _monetag_browser_session(
    worker_id: int,
    proxy_key: str,
    camoufox_kwargs: Dict[str, Any],
    context_opts: Dict[str, Any],
    lightweight: bool = True,
    max_sessions: int = 8,
):
    """Reuse proses Camoufox per-worker untuk proxy yang sama dan kunci WORKER_STARTUP_LOCK hanya saat launch binary."""
    if not lightweight:
        with WORKER_STARTUP_LOCK:
            cm = Camoufox(**camoufox_kwargs)
            browser = cm.__enter__()
        context = None
        try:
            context = browser.new_context(**context_opts)
            yield browser, context
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass
        return

    with _WORKER_BROWSERS_LOCK:
        entry = _WORKER_BROWSERS.get(worker_id)
    browser = None
    if (
        entry
        and entry.get("proxy_key") == proxy_key
        and entry.get("sessions", 0) < max_sessions
        and entry.get("browser") is not None
    ):
        entry["sessions"] += 1
        browser = entry["browser"]
    else:
        close_worker_browser(worker_id)
        with WORKER_STARTUP_LOCK:
            cm = Camoufox(**camoufox_kwargs)
            browser = cm.__enter__()
        with _WORKER_BROWSERS_LOCK:
            _WORKER_BROWSERS[worker_id] = {
                "cm": cm,
                "browser": browser,
                "proxy_key": proxy_key,
                "sessions": 1,
            }

    context = None
    try:
        context = browser.new_context(**context_opts)
        _setup_monetag_media_filter(context)
        yield browser, context
    except Exception:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
            context = None
        close_worker_browser(worker_id)
        raise
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass


def _target_available(
    usage_proxy: Dict[str, Any],
    target: str,
    max_uses_per_day: int,
    cooldown_seconds: float,
    window_seconds: float = 24 * 3600,
) -> bool:
    """Cek kuota satu IP untuk satu target dari snapshot target_usage proxy."""
    data = (usage_proxy.get("target_usage") or {}).get(target) or {}
    if not isinstance(data, dict):
        return True
    count = int(data.get("count", 0) or 0)
    last_used = float(data.get("last_used") or 0)
    now = time.time()
    if last_used > 0 and (now - last_used) >= window_seconds:
        return True
    if count >= max_uses_per_day:
        return False
    if count > 0 and (now - last_used) < cooldown_seconds:
        return False
    return True


class MonetagSessionError(RuntimeError):
    """Kegagalan sesi Monetag yang perlu diklasifikasikan oleh worker chain."""


class MonetagVerificationError(MonetagSessionError):
    """IP exit/WebRTC bocor saat memakai proxy chain."""


class MonetagProxyError(MonetagSessionError):
    """Koneksi proxy/hop gagal saat navigasi."""


class MonetagNoAdError(MonetagSessionError):
    """Halaman termuat tetapi tidak ada impresi iklan Monetag yang benar-benar tampil."""


# Host tag/penyaji Monetag yang umum. Serving domain bisa berotasi, jadi deteksi
# juga memakai zone id di URL (lihat `_is_ad_request`).
_DEFAULT_AD_HOSTS = (
    "monetag.com",
    "mndly.com",
    "quge5.com",
    "5gvci.com",
    "uplcm.com",
    "al5sm.com",
    "nap5k.com",
    "n6wxm.com",
    "255md.com",
    "jhnwr.com",
    "ldrws.com",
)
_DEFAULT_AD_ZONES = ("12126541", "12126546", "12126548")

# Deteksi elemen iklan yang benar-benar terlihat (vignette overlay, push widget,
# atau iframe fixed ber-z-index tinggi). Tag <script data-zone> saja TIDAK cukup
# karena script bisa termuat walau tidak ada iklan yang dirender.
_AD_SURFACE_JS = """
() => {
  const adHost = /(monetag|mndly|quge5|5gvci|uplcm|al5sm|nap5k|n6wxm|255md|jhnwr|ldrws)/i;
  const zones = Array.from(document.querySelectorAll('[data-zone]'))
    .map(e => e.getAttribute('data-zone'))
    .filter(Boolean);
  const details = [];
  let count = 0;
  for (const el of document.querySelectorAll('iframe, ins, div, section, aside')) {
    const style = window.getComputedStyle(el);
    const z = parseInt(style.zIndex || '0', 10);
    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    if (!visible || !Number.isFinite(z)) continue;
    const overlayPos = style.position === 'fixed' || style.position === 'sticky';
    const src = (el.getAttribute && el.getAttribute('src')) || '';
    const idcls = `${el.id || ''} ${typeof el.className === 'string' ? el.className : ''}`;
    const tagged = !!(el.hasAttribute && el.hasAttribute('data-zone'));
    const adLike = tagged || adHost.test(src) || adHost.test(idcls) ||
      /vignette|popunder|in-?page.?push/i.test(idcls);
    // Iframe overlay ber-z-index tinggi adalah signature vignette/push Monetag,
    // meski src kosong (konten diinjeksi via srcdoc). Elemen ber-z-index ekstrem
    // (2 miliar+) juga hanya dipakai overlay iklan.
    const frameOverlay = el.tagName === 'IFRAME' && overlayPos && z >= 1000;
    const adOverlay = adLike && (overlayPos || z >= 1000);
    const extremeOverlay = z >= 2000000000 &&
      (style.position === 'fixed' || style.position === 'absolute');
    if (frameOverlay || adOverlay || extremeOverlay) {
      count += 1;
      details.push((idcls.trim() || el.tagName).slice(0, 60));
    }
  }
  return {count, zones, details};
}
"""

_PROXY_ERROR_MARKERS = (
    "err_proxy",
    "err_tunnel",
    "err_connection_refused",
    "err_connection_reset",
    "err_name_not_resolved",
    "err_timed_out",
    "ns_error_proxy",
    "ns_error_net",
    "ns_error_connection",
    "ns_error_unknown_host",
    "ns_error_unknown_proxy",
    "bad_gateway",
    "502 bad gateway",
    "unable to connect",
    "proxy connection",
    "tunnel connection",
    "timed out",
    "timeout",
)

_SHUTDOWN_MARKERS = (
    "target closed",
    "browser has been closed",
    "browser closed",
    "context closed",
    "has been closed",
    "target page, context or browser has been closed",
)


def _is_proxy_navigation_error(error: BaseException) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in _PROXY_ERROR_MARKERS)


def _looks_like_shutdown(error: BaseException) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in _SHUTDOWN_MARKERS)


def _classify_session_error(error: BaseException, stopping: bool = False) -> str:
    if isinstance(error, MonetagVerificationError):
        return "verification"
    if isinstance(error, MonetagProxyError):
        return "proxy"
    if isinstance(error, MonetagNoAdError):
        return "no_ad"
    if stopping or _looks_like_shutdown(error):
        return "shutdown"
    text = str(error or "").lower()
    if "cloudflare" in text or "turnstile" in text or "just a moment" in text:
        return "cloudflare"
    return "other"


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _emit(callback: Optional[Callable[[str, Dict[str, Any]], None]], event_type: str, **kwargs: Any) -> None:
    if callback:
        try:
            callback(event_type, kwargs)
        except Exception:
            pass


def run_monetag_session(
    worker_id: int,
    proxy_data: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan 1 sesi automasi Monetag secara utuh dan humanized.
    """
    raw_target_url = config.get("target_url", "https://article.riztama.my.id/")
    parsed = urlparse(raw_target_url)
    target_host = (parsed.netloc or "article.riztama.my.id").lower()

    clean_path = parsed.path.rstrip('/')
    if clean_path == "/m":
        target_url = f"{parsed.scheme or 'https'}://{target_host}/"
    else:
        target_url = raw_target_url
    direct_link_url = config.get("direct_link_url", "https://uplcm.com/4/12124796")
    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    lightweight = bool(config.get("lightweight", True))
    proxy_info = proxy_data or {}
    chain_mode = proxy_info.get("source") == "chain"
    enable_verifier = bool(config.get("run_browser_verifier", False))

    traffic_mode = config.get("traffic_mode", "fast_impression")
    is_deep = (traffic_mode == "deep_browse")

    if is_deep:
        popunder_dwell_cfg = config.get("dwell_popup_seconds", {}) or {"min": 8.0, "max": 14.0}
        direct_link_dwell_cfg = config.get("dwell_direct_link_seconds", {}) or {"min": 10.0, "max": 16.0}
        interaction_count_range = (3, 5)
    else:
        popunder_dwell_cfg = config.get("dwell_popup_seconds", {}) or {"min": 5.0, "max": 8.5}
        direct_link_dwell_cfg = config.get("dwell_direct_link_seconds", {}) or {"min": 6.0, "max": 10.0}
        interaction_count_range = (2, 3)

    direct_link_chance = float(config.get("direct_link_chance", 0.50))
    require_ad_impression = bool(config.get("require_ad_impression", True))
    ad_wait_seconds = float(config.get("ad_wait_seconds", 8.0))
    ad_fallback_seconds = float(config.get("ad_fallback_seconds", 6.0))

    session_start = time.time()
    popups_opened: List[Any] = []
    direct_links_processed = 0
    popunders_processed = 0

    if not proxy_info.get("host") or not proxy_info.get("port"):
        raise ValueError("Proxy residensial wajib aktif! Koneksi langsung (Direct IP VPS) diblokir demi keamanan akun.")
    proxy_label = f"{proxy_info.get('host')}:{proxy_info.get('port')}"

    def log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"[W{worker_id}] {msg}",
            style=style,
            target_url=target_url,
        )

    log(f"Memulai sesi Monetag dengan proxy: {proxy_label}", "cyan")
    if chain_mode:
        log(
            f"🔎 Exit chain: {proxy_info.get('expected_ip')} "
            f"| {proxy_info.get('expected_isp') or '?'} / {proxy_info.get('expected_asn') or '?'} "
            f"| residential={proxy_info.get('residential_endpoint') or '?'} "
            f"| hosting={proxy_info.get('exit_hosting')}",
            "dim",
        )

    camoufox_kwargs = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize_enabled,
        allow_ads=True,
        extra_prefs={"media.peerconnection.enabled": False} if chain_mode else None,
        lightweight=lightweight,
    )
    context_opts = build_camoufox_context_options(proxy_data)
    proxy_key = f"{proxy_label}|{proxy_info.get('expected_ip') or proxy_info.get('ip_detected') or ''}"

    with _monetag_browser_session(
        worker_id=worker_id,
        proxy_key=proxy_key,
        camoufox_kwargs=camoufox_kwargs,
        context_opts=context_opts,
        lightweight=lightweight,
    ) as (browser, context):
        page = context.new_page()

        target_domain = target_host.split(":")[0]

        # ── Monitoring request & impresi iklan Monetag ──
        ad_hosts = {str(h).lower() for h in (config.get("ad_hosts") or [])}
        ad_hosts.update(_DEFAULT_AD_HOSTS)
        ad_zones = {str(z) for z in (config.get("ad_zones") or _DEFAULT_AD_ZONES)}
        ad_hits: Dict[str, int] = {}
        impression_hits: Dict[str, int] = {}
        ad_hits_lock = threading.Lock()

        def _is_ad_request(url: str) -> Optional[str]:
            host = _host(url)
            if host:
                for expected in ad_hosts:
                    if host == expected or host.endswith("." + expected):
                        return expected
            low = str(url or "").lower()
            for zone in ad_zones:
                if zone in low:
                    return f"zone:{zone}"
            return None

        def _is_impression_request(url: str) -> bool:
            # Request script (tag.min.js/vignette.min.js) hanya menandakan tag aktif,
            # belum tentu ada iklan yang dirender. Endpoint serving/impression
            # (mis. /5/<zone>, /500/<zone>, /impression/<zone>) adalah bukti impresi.
            path = str(url or "").split("?", 1)[0].lower()
            if path.endswith(".js"):
                return False
            return _is_ad_request(url) is not None

        def on_request(request: Any) -> None:
            url = str(request.url or "")
            matched = _is_ad_request(url)
            if not matched:
                return
            is_impression = _is_impression_request(url)
            with ad_hits_lock:
                ad_hits[matched] = ad_hits.get(matched, 0) + 1
                first_hit = ad_hits[matched] == 1
                first_impression = False
                if is_impression:
                    impression_hits[matched] = impression_hits.get(matched, 0) + 1
                    first_impression = impression_hits[matched] == 1
            if first_hit:
                log(f"📡 Request iklan Monetag: {matched}", "magenta")
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="🎯 Iklan Monetag",
                    status=f"Request iklan: {matched}",
                )
            if first_impression:
                log(f"🎯 Impresi iklan Monetag terkirim: {matched}", "bold magenta")
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="🎯 Iklan Monetag",
                    status=f"Impresi terkirim: {matched}",
                )

        context.on("request", on_request)

        direct_page: Optional[Any] = None

        # Listener deteksi pembukaan popup / tab iklan baru
        def on_popup(popup_page: Any) -> None:
            if popup_page == page or popup_page in popups_opened or (direct_page and popup_page == direct_page):
                return
            popups_opened.append(popup_page)
            p_url = str(popup_page.url or "")
            log(f"📑 Tab iklan baru terdeteksi: {p_url[:65]}...", "magenta")
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="📑 Tab Iklan",
                status=f"Popunder terbuka: {_host(p_url)}",
            )

        context.on("page", on_popup)
        page.on("popup", on_popup)

        ad_surface_state: Dict[str, Any] = {"count": 0, "zones": [], "details": []}
        ad_surface_logged = {"done": False}

        def _visible_ad_surfaces() -> Dict[str, Any]:
            try:
                info = page.evaluate(_AD_SURFACE_JS)
                return info if isinstance(info, dict) else {}
            except Exception:
                return {}

        def _ad_impression_seen() -> bool:
            """True jika ada bukti impresi nyata: request serving, popup iklan, atau overlay terlihat."""
            with ad_hits_lock:
                if impression_hits:
                    return True
            for popup_page in list(popups_opened):
                try:
                    if popup_page.is_closed():
                        continue
                    p_url = str(popup_page.url or "")
                except Exception:
                    continue
                if p_url and p_url != "about:blank" and target_domain not in p_url:
                    return True
            info = _visible_ad_surfaces()
            if info.get("count", 0) > 0:
                ad_surface_state.update(info)
                if not ad_surface_logged["done"]:
                    ad_surface_logged["done"] = True
                    log(
                        f"🖼️ Elemen iklan terlihat di halaman: {info.get('count')} "
                        f"(zone={info.get('zones')})",
                        "bold magenta",
                    )
                return True
            return False

        def _wait_for_ad_impression(timeout: float) -> bool:
            deadline = time.time() + max(0.0, timeout)
            while time.time() < deadline:
                if _ad_impression_seen():
                    return True
                time.sleep(0.35)
            return _ad_impression_seen()

        # ── Pre-flight Browser Audit (Optional Verifier) ──
        if enable_verifier:
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="🛡️ Audit IP",
                status="Cek IP, WebRTC & stealth...",
            )
            try:
                page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
                verifier = BrowserVerifier(strict_mode=False)
                if chain_mode:
                    exp_ip = proxy_info.get("expected_ip") or proxy_info.get("ip_detected")
                    exp_country = None
                    exp_asn = proxy_info.get("expected_asn")
                    exp_isp = proxy_info.get("expected_isp")
                    allow_ip_rotation = True
                    forbidden_ip = proxy_info.get("hop_ip")
                else:
                    is_rotating = (
                        proxy_info.get("connection_type") == "residential"
                        or "floppydata" in str(proxy_info.get("host", "")).lower()
                    )
                    exp_ip = None if is_rotating else (proxy_info.get("ip_detected") or proxy_info.get("host"))
                    exp_country = None if is_rotating else proxy_info.get("country")
                    exp_asn = None
                    exp_isp = None
                    allow_ip_rotation = False
                    forbidden_ip = None

                report = verifier.verify(
                    page,
                    expected_ip=exp_ip,
                    expected_country=exp_country,
                    check_ads=True,
                    expected_asn=exp_asn,
                    expected_isp=exp_isp,
                    allow_ip_rotation=allow_ip_rotation,
                    forbidden_ip=forbidden_ip,
                )
                actual = report.actual_state
                _emit(
                    event_callback,
                    "verifier_report",
                    worker_id=worker_id,
                    score=report.score,
                    is_safe=report.is_safe,
                    detected_ip=actual.get("ip"),
                    detected_country=country_label(actual.get("country")),
                    isp=actual.get("isp"),
                    bot_detected=bool(actual.get("webdriver")),
                    webrtc_leak=bool(actual.get("webrtc_leak")),
                    ads_allowed=bool(actual.get("ads_allowed", True)),
                )
                if chain_mode:
                    leaked = report.match_results.get("ip_matched") is False
                    webrtc_leak = report.match_results.get("no_webrtc_leak") is False
                    if leaked or webrtc_leak:
                        issues = "; ".join(report.issues[:3]) or "IP exit tidak sesuai"
                        raise MonetagVerificationError(issues)
            except MonetagVerificationError:
                raise
            except Exception as e_ver:
                log(f"Catatan verifier: {str(e_ver)[:90]}", "dim")

        # ── 1. Kunjungi Halaman Target (MultiTag Web) ──
        _emit(
            event_callback,
            "session_started",
            worker_id=worker_id,
            target_url=target_url,
        )
        _emit(
            event_callback,
            "stepper_update",
            stage="🌐 Kunjungan Web",
            status="Membuka web target...",
        )
        organic_referers = [
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://t.co/",
            "https://duckduckgo.com/",
            "https://news.ycombinator.com/",
        ]
        chosen_ref = random.choice(organic_referers)
        log(f"Membuka halaman target (Referer: {_host(chosen_ref)}): {target_url}", "bold yellow")
        nav_ok = False
        last_nav_err: Optional[BaseException] = None
        for nav_attempt in range(1, 3):
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000, referer=chosen_ref)
                curr_u = str(page.url or "")
                if curr_u.startswith("about:neterror") or curr_u.startswith("about:certerror"):
                    raise MonetagProxyError(f"Halaman gagal dimuat ({curr_u})")
                nav_ok = True
                break
            except Exception as e:
                last_nav_err = e
                if nav_attempt == 1:
                    log(f"Percobaan #1 buka target gagal ({str(e).splitlines()[0][:80]}), mencoba ulang...", "yellow")
                    time.sleep(1.0)
        if not nav_ok and last_nav_err is not None:
            if _is_proxy_navigation_error(last_nav_err) or isinstance(last_nav_err, MonetagProxyError):
                raise MonetagProxyError(f"Navigasi target gagal lewat proxy: {last_nav_err}") from last_nav_err
            log(f"Peringatan loading ({last_nav_err}), melanjutkan interaksi...", "dim")

        # Jeda natural membaca halaman awal (1.0 - 1.8 dtk)
        time.sleep(random.uniform(1.0, 1.8))
        log("🟢 Halaman awal berhasil termuat!", "bold green")

        # ── 2. Perilaku Membaca Natural (Scroll & Mouse Wander) ──
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="📜 Scroll & Viewability",
            status="Scroll halaman & inisialisasi tag...",
        )
        log("Membaca konten & scrolling cepat untuk memicu tag Monetag...", "cyan")
        vp = page.viewport_size or {"width": 1366, "height": 768}
        human_wander(page, duration_seconds=random.uniform(1.2, 2.2))
        human_scroll(page, scroll_amount=random.randint(280, 520))

        # Pastikan tag Monetag benar-benar tampil sebelum lanjut interaksi.
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="🎯 Tunggu Iklan",
            status="Menunggu impresi Monetag tampil...",
        )
        log("⏳ Menunggu tag & impresi Monetag muncul...", "cyan")
        if _wait_for_ad_impression(ad_wait_seconds):
            log("✅ Iklan Monetag tampil — impresi terkonfirmasi.", "bold green")
        else:
            log(
                "⚠️ Belum ada impresi Monetag; akan dipaksa lewat interaksi & Direct Link.",
                "yellow",
            )

        def get_target_page() -> Any:
            """Mencari tab yang memuat target web utama."""
            for p in context.pages:
                if not p.is_closed() and target_domain in str(p.url):
                    return p
            return page

        def get_adv_pages() -> List[Any]:
            """Mencari semua tab yang BUKAN target gateway (tab iklan/popunder/advertiser)."""
            advs = []
            for p in context.pages:
                if not p.is_closed() and p != page and target_domain not in str(p.url):
                    advs.append(p)
            return advs

        processed_popups = set()

        def _wait_tab_loaded(tab: Any, wait_redirect_hosts: tuple = ("uplcm.com",), timeout_sec: float = 22.0) -> str:
            """Tunggu tab baru keluar dari about:blank, melewati redirector, dan selesai memuat DOM sebelum dwell."""
            deadline = time.time() + timeout_sec
            # 1. Tunggu keluar dari about:blank
            while time.time() < deadline and not tab.is_closed():
                u = str(tab.url or "")
                if u and u != "about:blank":
                    break
                time.sleep(0.25)

            # 2. Jika masih di host redirector (mis. uplcm.com), tunggu redirect ke halaman advertiser
            if wait_redirect_hosts:
                redir_deadline = min(deadline, time.time() + 12.0)
                while time.time() < redir_deadline and not tab.is_closed():
                    u = str(tab.url or "")
                    h = _host(u)
                    if h and not any(rh in h for rh in wait_redirect_hosts):
                        break
                    time.sleep(0.35)

            # 3. Tunggu DOM halaman akhir benar-benar termuat (bukan masih muter di about:blank)
            rem_ms = int(max(3000.0, (deadline - time.time()) * 1000))
            try:
                tab.wait_for_load_state("domcontentloaded", timeout=rem_ms)
            except Exception:
                pass
            while time.time() < deadline and not tab.is_closed():
                try:
                    state = tab.evaluate("() => document.readyState")
                    u = str(tab.url or "")
                    if u and u != "about:blank" and state in ("interactive", "complete"):
                        break
                except Exception:
                    pass
                time.sleep(0.35)
            return str(tab.url or "")

        def _is_valid_loaded_url(u: str) -> bool:
            raw = str(u or "").strip().lower()
            return bool(
                raw
                and raw != "about:blank"
                and not raw.startswith("about:neterror")
                and not raw.startswith("about:certerror")
                and not raw.startswith("chrome-error://")
            )

        def drain_popups(tag_name: str = "Popunder") -> int:
            nonlocal popunders_processed
            count = 0
            time.sleep(0.4)

            # Gabungkan tab dari on_popup dan tab dari context.pages yang bukan gateway
            candidate_tabs: List[Any] = []
            for p in list(popups_opened) + get_adv_pages():
                if p not in candidate_tabs and not p.is_closed() and p != get_target_page() and (not direct_page or p != direct_page):
                    candidate_tabs.append(p)


            for idx, popup in enumerate(candidate_tabs):
                if popup in processed_popups or popup.is_closed():
                    continue
                processed_popups.add(popup)
                try:
                    popup.bring_to_front()
                    popup_url = _wait_tab_loaded(popup, wait_redirect_hosts=("uplcm.com", "quge5.com", "5gvci.com"), timeout_sec=18.0)
                    if not _is_valid_loaded_url(popup_url):
                        log(f"⚠️ Tab iklan gagal memuat halaman tujuan ({popup_url[:50]}), dilewati.", "yellow")
                        try:
                            popup.close()
                        except Exception:
                            pass
                        continue
                    time.sleep(0.5)
                    dwell_time = random.uniform(
                        float(popunder_dwell_cfg.get("min", 5.0)),
                        float(popunder_dwell_cfg.get("max", 8.5)),
                    )
                    _emit(
                        event_callback,
                        "stepper_update",
                        worker_id=worker_id,
                        stage="📑 Popunder Dwell",
                        status=f"Dwell tab iklan ({dwell_time:.1f}s)...",
                    )
                    log(f"📑 Melakukan dwell di tab iklan ({count+1}): {_host(popup_url)} ({dwell_time:.1f}s)", "magenta")

                    end_dwell = time.time() + dwell_time
                    has_interacted = False
                    while time.time() < end_dwell and not popup.is_closed():
                        if humanize_enabled:
                            human_wander(popup, duration_seconds=random.uniform(0.8, 1.4))
                            human_scroll(popup, scroll_amount=random.randint(200, 450), pause_range=(0.15, 0.3))
                            if not has_interacted and random.random() < 0.50:
                                try:
                                    vp_adv = popup.viewport_size or {"width": 1280, "height": 800}
                                    neut_x = random.randint(120, vp_adv["width"] - 120)
                                    neut_y = random.randint(180, vp_adv["height"] - 220)
                                    popup.mouse.click(neut_x, neut_y)
                                    has_interacted = True
                                except Exception:
                                    pass
                        time.sleep(0.8)

                    log(f"✅ Selesai dwell iklan {tag_name} ({_host(popup_url)}). Menutup tab...", "green")
                    try:
                        popup.close()
                    except Exception:
                        pass
                    popunders_processed += 1
                    count += 1
                except Exception as ex:
                    log(f"Peringatan proses popup: {ex}", "dim")

            # Kembalikan fokus ke tab web target
            main_p = get_target_page()
            if main_p and not main_p.is_closed():
                try:
                    main_p.bring_to_front()
                except Exception:
                    pass
            return count

        # ── 3. Interaksi Halaman Alami & Memicu Impresi Monetag ──
        _emit(
            event_callback,
            "stepper_update",
            stage="🎯 Interaksi Halaman",
            status="Interaksi natural & trigger OnClick...",
        )
        log("Memulai interaksi halaman untuk memicu OnClick, In-Page Push & Vignette...", "bold yellow")

        # Fungsi penanganan redirect tab utama ke landing page advertiser
        def check_and_handle_redirect() -> bool:
            nonlocal popunders_processed
            curr_url = str(page.url or "")
            if curr_url and target_domain not in curr_url and curr_url != "about:blank":
                log(f"🔄 Tab utama ter-redirect ke advertiser: {_host(curr_url)}", "yellow")
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="🔄 Advertiser Dwell",
                    status=f"Dwell landing page ({_host(curr_url)})...",
                )
                try:
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=12000)
                    except Exception:
                        pass
                    dwell_time = random.uniform(
                        float(popunder_dwell_cfg.get("min", 5.0)),
                        float(popunder_dwell_cfg.get("max", 8.5)),
                    )
                    log(f"⏳ Dwell cepat di halaman redirect advertiser selama {dwell_time:.1f}s...", "magenta")
                    end_time = time.time() + dwell_time
                    while time.time() < end_time and not page.is_closed():
                        if humanize_enabled:
                            human_wander(page, duration_seconds=random.uniform(0.8, 1.4))
                            human_scroll(page, scroll_amount=random.randint(200, 420), pause_range=(0.15, 0.3))
                        time.sleep(0.8)

                    popunders_processed += 1
                    log(f"✅ Selesai dwell impresi advertiser ({_host(curr_url)}).", "green")
                    # Navigasi kembali ke web target
                    try:
                        log(f"🔙 Kembali ke halaman target: {target_url}", "cyan")
                        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(2.0)
                    except Exception:
                        pass
                    return True
                except Exception as ex_red:
                    log(f"Catatan redirect advertiser: {ex_red}", "dim")
            return False

        # Cek In-Page Push Impression
        try:
            push_el = page.locator("div[class*='push' i], div[id*='push' i], iframe[src*='push' i], ins[data-zone='12126546']").first
            if push_el.is_visible(timeout=2000):
                log("💬 In-Page Push Monetag terdeteksi — mempertahankan viewability...", "yellow")
                human_wander(page, duration_seconds=random.uniform(2.0, 3.5))
        except Exception:
            pass

        # Target interaksi natural pada halaman
        interaction_selectors = [
            "button:has-text('IP Address Lookup')",
            "button:has-text('Speed Test')",
            "button:has-text('IP Whois Lookup')",
            "button:has-text('DNS Records')",
            "button:has-text('Privacy & Leak Test')",
            "button:has-text('Lookup')",
            "input[type='text']",
            "button:has-text('Run Privacy Audit')",
            "button:has-text('Start Speed Test')",
            "main",
            "header",
        ]

        # Lakukan interaksi cepat untuk trigger OnClick
        num_interactions = random.randint(*interaction_count_range)
        for i_idx in range(num_interactions):
            gw = get_target_page()
            if gw.is_closed():
                break

            # Cek apakah tab utama sudah ter-redirect ke advertiser
            if check_and_handle_redirect():
                drain_popups(f"Post Redirect #{i_idx + 1}")
                continue

            # Pilih elemen interaksi
            chosen_sel = random.choice(interaction_selectors)
            try:
                elem = gw.locator(chosen_sel).first
                if elem.is_visible(timeout=1200):
                    elem.scroll_into_view_if_needed()
                    time.sleep(random.uniform(0.2, 0.5))
                    if humanize_enabled:
                        human_wander(gw, duration_seconds=random.uniform(0.6, 1.2))
                    log(f"👆 [Interaksi #{i_idx + 1}] Klik elemen natural: {chosen_sel}", "cyan")
                    human_click(gw, elem)
                    time.sleep(random.uniform(0.8, 1.5))
                else:
                    # Klik area netral
                    vp_curr = gw.viewport_size or {"width": 1366, "height": 768}
                    click_x = random.randint(150, vp_curr["width"] - 150)
                    click_y = random.randint(150, vp_curr["height"] - 200)
                    log(f"👆 [Interaksi #{i_idx + 1}] Klik area netral viewport ({click_x}, {click_y})", "cyan")
                    gw.mouse.click(click_x, click_y)
                    time.sleep(random.uniform(0.8, 1.5))
            except Exception as e_click:
                log(f"Catatan klik #{i_idx + 1}: {e_click}", "dim")

            # Periksa apakah klik memicu redirect atau popunder
            check_and_handle_redirect()
            drain_popups(f"Interaksi #{i_idx + 1}")

        # ── 4. Cek & Dwell Overlay Vignette Banner ──
        gw = get_target_page()
        if gw and not gw.is_closed():
            try:
                overlay = _visible_ad_surfaces()
                if overlay.get("count", 0) > 0:
                    ad_surface_state.update(overlay)
                    _emit(
                        event_callback,
                        "stepper_update",
                        worker_id=worker_id,
                        stage="🖼️ Overlay Iklan",
                        status="Dwell overlay iklan (vignette/push)...",
                    )
                    log(
                        f"🖼️ Overlay iklan terlihat ({overlay.get('count')} elemen). "
                        "Dwell untuk validasi impresi...",
                        "yellow",
                    )
                    # Dwell 2.0 - 3.5 detik agar Monetag merekam impresi penuh
                    time.sleep(random.uniform(2.0, 3.5))
                    close_btn = gw.locator(
                        "button[aria-label*='close' i], .vignette-close, "
                        "[class*='close' i], [id*='close' i], svg.close-icon"
                    ).first
                    if close_btn.is_visible(timeout=800):
                        human_click(gw, close_btn)
                        time.sleep(0.8)
                    drain_popups("Post Vignette")
            except Exception:
                pass

        # ── 6. Direct Link Monetag (Cuan Tertinggi) ──
        impression_ok = _ad_impression_seen()
        force_direct = (require_ad_impression and not impression_ok) or (popunders_processed == 0)
        if direct_link_url and (force_direct or random.random() < direct_link_chance):
            if force_direct:
                reason_msg = (
                    "Belum ada Popunder terbuka di sesi ini"
                    if popunders_processed == 0
                    else "Belum ada impresi Monetag"
                )
                log(
                    f"🎯 {reason_msg} — wajib membuka & dwell Direct Link agar cuan maksimal.",
                    "bold yellow",
                )
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="🔗 Direct Link (Wajib)",
                    status="Jaminan impresi landing page...",
                )
            direct_dwell = random.uniform(
                float(direct_link_dwell_cfg.get("min", 6.0)),
                float(direct_link_dwell_cfg.get("max", 10.0)),
            )
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="🔗 Direct Link Dwell",
                status=f"Dwell Smartlink ({direct_dwell:.1f}s)...",
            )
            log(f"🔗 Membuka Direct Link Monetag di tab baru & dwell {direct_dwell:.1f}s...", "cyan")
            direct_page = None
            try:
                gw = get_target_page()
                try:
                    with context.expect_page(timeout=10000) as new_page_info:
                        gw.evaluate(
                            """(url) => {
                                const a = document.createElement('a');
                                a.href = url;
                                a.target = '_blank';
                                a.rel = 'noopener noreferrer';
                                document.body.appendChild(a);
                                a.click();
                                a.remove();
                            }""",
                            direct_link_url,
                        )
                    direct_page = new_page_info.value
                except Exception:
                    direct_page = context.new_page()
                    direct_page.goto(direct_link_url, wait_until="domcontentloaded", timeout=45000)

                if direct_page:
                    direct_page.bring_to_front()
                    log("⏳ Menunggu redirect & loading halaman Direct Link selesai sebelum hitung dwell...", "cyan")
                    final_dl_url = _wait_tab_loaded(
                        direct_page,
                        wait_redirect_hosts=("uplcm.com", "quge5.com", "5gvci.com", "al5sm.com", "nap5k.com"),
                        timeout_sec=25.0,
                    )
                    if not _is_valid_loaded_url(final_dl_url):
                        log("🔄 Percobaan #1 Direct Link belum termuat penuh, mencoba reload Direct Link...", "yellow")
                        try:
                            direct_page.goto(direct_link_url, wait_until="domcontentloaded", timeout=35000)
                        except Exception:
                            pass
                        final_dl_url = _wait_tab_loaded(
                            direct_page,
                            wait_redirect_hosts=("uplcm.com", "quge5.com", "5gvci.com", "al5sm.com", "nap5k.com"),
                            timeout_sec=20.0,
                        )
                    if _is_valid_loaded_url(final_dl_url):
                        log(f"🟢 Direct Link berhasil termuat ({_host(final_dl_url) or final_dl_url[:45]}), memulai dwell {direct_dwell:.1f}s...", "magenta")
                        end_dl = time.time() + direct_dwell
                        has_dl_interacted = False
                        while time.time() < end_dl and not direct_page.is_closed():
                            if humanize_enabled:
                                human_wander(direct_page, duration_seconds=random.uniform(1.0, 1.8))
                                human_scroll(direct_page, scroll_amount=random.randint(180, 420), pause_range=(0.2, 0.4))
                                if not has_dl_interacted and random.random() < 0.40:
                                    try:
                                        vp_dl = direct_page.viewport_size or {"width": 1280, "height": 800}
                                        neut_x = random.randint(120, vp_dl["width"] - 120)
                                        neut_y = random.randint(180, vp_dl["height"] - 220)
                                        direct_page.mouse.click(neut_x, neut_y)
                                        has_dl_interacted = True
                                    except Exception:
                                        pass
                            time.sleep(1.2)
                        direct_links_processed += 1
                        log("✅ Direct Link dwell selesai dengan sukses!", "bold green")
                    else:
                        log(f"⚠️ Direct Link gagal memuat halaman advertiser ({final_dl_url[:50]}).", "yellow")
                    try:
                        direct_page.close()
                    except Exception:
                        pass
                    gw = get_target_page()
                    if gw and not gw.is_closed():
                        try:
                            gw.bring_to_front()
                        except Exception:
                            pass
            except Exception as e_dl:
                log(f"Peringatan proses Direct Link: {e_dl}", "dim")

            # Kuras popunder yang mungkin terbuka saat klik direct link
            drain_popups("Post Direct Link")
        elif direct_link_url:
            log(f"ℹ️ Sesi ini fokus impresi MultiTag (Direct Link dilewati demi CTR organik ~{int(direct_link_chance * 100)}%).", "dim")

        # Pembersihan akhir untuk popunder yang tertunda
        drain_popups("Final Cleanup")

        # Verifikasi akhir: pastikan ada impresi yang benar-benar tampil.
        impression_ok = _ad_impression_seen()
        if require_ad_impression and not impression_ok:
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="🎯 Verifikasi Iklan",
                status="Menunggu impresi Monetag tampil...",
            )
            log("⏳ Menunggu impresi Monetag terakhir sebelum menutup sesi...", "cyan")
            impression_ok = _wait_for_ad_impression(ad_fallback_seconds)

        ad_summary = dict(ad_hits)
        ad_total = sum(ad_summary.values())
        with ad_hits_lock:
            impression_summary = dict(impression_hits)
        impression_total = sum(impression_summary.values())
        visible_surfaces = int(ad_surface_state.get("count", 0) or 0)
        landing_dwelled = (popunders_processed > 0) or (direct_links_processed > 0)
        ad_verified = bool(landing_dwelled or visible_surfaces > 0)

        if ad_total:
            hosts_text = ", ".join(
                f"{host}({count})" for host, count in sorted(ad_summary.items())
            )
            log(
                f"✅ Iklan Monetag termuat: {ad_total} request dari "
                f"{len(ad_summary)} host — {hosts_text}",
                "bold green",
            )
        else:
            log(
                "⚠️ Tidak ada request iklan Monetag terdeteksi. "
                "Cek target/ad_hosts, mode headless, atau blokir dari advertiser.",
                "yellow",
            )

        if ad_verified:
            log(
                f"🎯 Impresi Monetag terverifikasi: {impression_total} request serving, "
                f"{visible_surfaces} elemen iklan terlihat.",
                "bold green",
            )
        else:
            log(
                "❌ Tidak ada impresi Monetag yang tampil "
                "(script tag termuat tetapi iklan tidak dirender).",
                "bold red",
            )

        if require_ad_impression and not ad_verified:
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="❌ TANPA IKLAN",
                status="Rotasi proxy & ulangi sesi...",
            )
            raise MonetagNoAdError(
                "Tidak ada impresi iklan Monetag yang tampil. "
                "Proxy/geo kemungkinan diblokir advertiser; sesi diulang dengan IP lain."
            )

        duration = round(time.time() - session_start, 1)
        log(f"🎉 Sesi Monetag selesai dalam {duration}s! (Popunders: {popunders_processed}, DirectLinks: {direct_links_processed})", "bold green")

        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            stage="✅ LOLOS",
            status=f"Selesai ({duration}s)",
        )
        _emit(
            event_callback,
            "session_completed",
            worker_id=worker_id,
            status="PASS",
            target_url=target_url,
        )

        return {
            "worker_id": worker_id,
            "success": True,
            "duration_seconds": duration,
            "popunders_processed": popunders_processed,
            "direct_links_processed": direct_links_processed,
            "ad_requests_total": ad_total,
            "ad_impressions_total": impression_total,
            "ad_hosts_hit": ad_summary,
            "ad_surfaces_visible": visible_surfaces,
            "ad_verified": ad_verified,
            "exit_ip": proxy_info.get("expected_ip"),
            "exit_isp": proxy_info.get("expected_isp"),
            "exit_asn": proxy_info.get("expected_asn"),
            "residential_endpoint": proxy_info.get("residential_endpoint"),
            "proxy": proxy_label,
        }


def monetag_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    budget: SessionBudget,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    reset_pool_callback: Optional[Callable[[], None]] = None,
    chain_provider: Optional[Any] = None,
    post_session: Optional[Callable[[int, Dict[str, Any], Dict[str, Any]], None]] = None,
) -> None:
    """
    Loop worker multi-sesi untuk Monetag dengan rotasi proxy residensial.
    Kompatibel penuh dengan GUI dashboard orchestration.
    Bila `chain_provider` diberikan, proxy diambil lewat chain hop 3xK.
    """
    tag = f"[W{worker_id}]"
    config = dict(config)
    target_urls = list(config.get("target_urls") or [])
    batch_urls = [u for u in (config.get("site_urls") or []) if u]
    # Offset per worker: W1 mulai URL pertama, W2 URL kedua, dst.
    session_index = max(0, worker_id - 1)

    def _log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"{tag} {msg}",
            style=style,
        )

    def _target_key(url: str) -> str:
        parsed = urlparse(str(url or ""))
        host = (parsed.hostname or "").lower()
        return f"monetag:{host}" if host else "monetag"

    caller_prefix = f"monetag_w{worker_id}"
    _log("Browser Monetag siap — 1 IP dipakai untuk semua URL, lalu rotasi.", "green")

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break

        if batch_urls:
            urls_this = batch_urls
        else:
            if target_urls:
                config["target_url"] = target_urls[session_index % len(target_urls)]
                session_index += 1
            urls_this = [config.get("target_url") or ""]

        max_uses = int(config.get("max_uses_per_day", 2))
        cooldown_secs = float(config.get("proxy_cooldown_hours", 6.0)) * 3600
        lease_seconds = int(config.get("proxy_lease_seconds") or max(600, 600 * len(urls_this)))

        proxy = None
        for url in urls_this:
            caller_id = f"{caller_prefix}_{int(time.time() * 1000)}"
            target_name = _target_key(url)
            if chain_provider is not None:
                proxy = chain_provider.next_proxy(
                    caller_id=caller_id,
                    log_prefix=f"[W{worker_id}] ",
                    target=target_name,
                    lease_seconds=lease_seconds,
                )
            else:
                proxy = proxy_manager.acquire_proxy(
                    caller_id=caller_id,
                    exclusive=True,
                    verify_alive=False,
                    target=target_name,
                    max_uses_per_day=max_uses,
                    cooldown_seconds=cooldown_secs,
                    lease_seconds=lease_seconds,
                )
            if proxy:
                break

        if not proxy:
            # Hanya jalankan reset pool lokal jika TIDAK menggunakan database Supabase
            if getattr(budget, "unlimited", False) and reset_pool_callback and not getattr(proxy_manager, "supabase_enabled", False):
                reset_pool_callback()
                _log("Pool IP habis — direset untuk rotasi ulang.", "cyan")
                time.sleep(1.0)
                continue

            _log("Menunggu IP yang tersedia / selesai masa cooldown 6 jam...", "dim")
            time.sleep(5.0)
            continue

        proxy_id = proxy.get("id") or proxy.get("proxy_url")
        ip = proxy.get("expected_ip") or proxy.get("ip_detected") or proxy.get("host", "?")
        country = country_label(proxy.get("country"))
        expected_geo = resolve_geo_profile(proxy)

        # Surfaced to GUI table
        usage_proxy = proxy.get("_residential") or proxy
        summary_manager = chain_provider.pm if chain_provider is not None else proxy_manager
        released = False
        ran_any = False

        for url in urls_this:
            if stop_event and stop_event.is_set():
                break
            if budget.is_exhausted() or not budget.has_capacity():
                break

            target_name = _target_key(url)
            if not _target_available(usage_proxy, target_name, max_uses, cooldown_secs):
                _log(f"⏭️ {url} masih limit/cooldown untuk IP ini — lanjut URL berikutnya", "dim")
                continue
            if not budget.reserve():
                break
            ran_any = True

            try:
                t_usage = summary_manager.get_target_usage_summary(
                    usage_proxy, target=target_name, max_uses_per_day=max_uses, cooldown_seconds=cooldown_secs
                )
            except Exception:
                t_usage = {}
            _emit(
                event_callback,
                "proxy_assigned",
                worker_id=worker_id,
                target_url=url,
                proxy_id=proxy_id,
                ip=ip,
                country=country,
                target_usage=t_usage.get("summary_text", "Hit 1/2"),
                hit_count=t_usage.get("current_hit", 1),
                timezone=expected_geo.get("timezone"),
                locale=expected_geo.get("locale"),
            )

            session_config = dict(config)
            session_config["target_url"] = url
            try:
                run_monetag_session(
                    worker_id=worker_id,
                    proxy_data=proxy,
                    config=session_config,
                    event_callback=event_callback,
                )
                # Flow lanjutan memakai IP/proxy yang sama (mis. Smartlink)
                if post_session is not None:
                    post_session(worker_id, proxy, session_config)
                summary_manager.record_target_hit(usage_proxy, target=target_name)
                budget.record("PASS")
                if proxy_id:
                    budget.mark_proxy(proxy_id)
            except Exception as e_run:
                _log(f"❌ Error sesi Monetag: {e_run}", "bold red")
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="❌ GAGAL",
                    status=str(e_run)[:40],
                )
                _emit(
                    event_callback,
                    "session_completed",
                    worker_id=worker_id,
                    status="FAIL",
                    target_url=url,
                )
                budget.record("FAIL")
                if proxy_id:
                    budget.mark_proxy(proxy_id)
                if chain_provider is not None:
                    error_kind = _classify_session_error(
                        e_run, stopping=bool(stop_event and stop_event.is_set())
                    )
                    chain_provider.finish_session(
                        proxy, False, e_run, error_kind,
                        log_prefix=f"[W{worker_id}] ",
                    )
                else:
                    try:
                        proxy_manager.report_failure(proxy, error_message=str(e_run))
                    finally:
                        proxy_manager.release_proxy(proxy)
                released = True
                break

            time.sleep(random.uniform(0.8, 1.8))

        if not released:
            if chain_provider is not None:
                close_worker_browser(worker_id)
                chain_provider.finish_session(
                    proxy, False, error_kind="batch",
                    log_prefix=f"[W{worker_id}] ",
                )
            else:
                proxy_manager.release_proxy(proxy)
            if not ran_any:
                time.sleep(1.0)

        # Jeda antar-sesi worker (dipercepat agar rotasi impresi tinggi)
        time.sleep(random.uniform(0.8, 1.8))

    close_worker_browser(worker_id)
