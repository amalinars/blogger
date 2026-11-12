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
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from automation.engine import WORKER_STARTUP_LOCK, build_camoufox_kwargs, build_camoufox_context_options, resolve_geo_profile
from automation.session import SessionBudget, country_label
from automation.browser_verifier import BrowserVerifier
from automation.monetag.humanizer import human_click, human_move, human_scroll, human_wander
from core.proxy_manager import ProxyManager


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
    proxy_info = proxy_data or {}
    chain_mode = proxy_info.get("source") == "chain"
    enable_verifier = bool(config.get("run_browser_verifier", False)) or chain_mode

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
    )
    context_opts = build_camoufox_context_options(proxy_data)

    with Camoufox(**camoufox_kwargs) as browser:
        context = browser.new_context(**context_opts)
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

        log("⏳ Menunggu giliran koneksi & verifikasi proxy...", "dim")
        with WORKER_STARTUP_LOCK:
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

                    report = verifier.verify(
                        page,
                        expected_ip=exp_ip,
                        expected_country=exp_country,
                        check_ads=True,
                        expected_asn=exp_asn,
                        expected_isp=exp_isp,
                        allow_ip_rotation=allow_ip_rotation,
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
            _emit(event_callback, "session_started", worker_id=worker_id)
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
            try:
                try:
                    page.goto(target_url, wait_until="commit", timeout=45000, referer=chosen_ref)
                except Exception:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45000, referer=chosen_ref)
            except Exception as e:
                if chain_mode and _is_proxy_navigation_error(e):
                    raise MonetagProxyError(f"Navigasi target gagal lewat chain: {e}") from e
                log(f"Peringatan loading ({e}), melanjutkan interaksi...", "dim")

            # Jeda natural membaca halaman awal (1.0 - 1.8 dtk)
            time.sleep(random.uniform(1.0, 1.8))
            log("🟢 Halaman awal berhasil termuat. Giliran koneksi diserahkan ke worker berikutnya!", "bold green")

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
                    # Tunggu jika URL masih about:blank sebelum navigasi selesai
                    for _ in range(6):
                        if popup.is_closed() or (popup.url and popup.url != "about:blank"):
                            break
                        time.sleep(0.3)

                    try:
                        popup.wait_for_load_state("domcontentloaded", timeout=6000)
                    except Exception:
                        pass
                    time.sleep(0.6)
                    popup_url = str(popup.url or "")
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
        force_direct = require_ad_impression and not impression_ok
        if direct_link_url and (force_direct or random.random() < direct_link_chance):
            if force_direct:
                log(
                    "🎯 Belum ada impresi Monetag — membuka Direct Link agar iklan pasti tampil.",
                    "bold yellow",
                )
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    stage="🔗 Direct Link (Wajib)",
                    status="Jaminan impresi iklan...",
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
                    try:
                        direct_page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    direct_page.bring_to_front()
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

                direct_links_processed += 1
                log("✅ Direct Link dwell selesai dengan sukses!", "bold green")
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
        ad_verified = bool(impression_total or visible_surfaces or impression_ok)

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
        _emit(event_callback, "session_completed", worker_id=worker_id, status="PASS")

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
) -> None:
    """
    Loop worker multi-sesi untuk Monetag dengan rotasi proxy residensial.
    Kompatibel penuh dengan GUI dashboard orchestration.
    Bila `chain_provider` diberikan, proxy diambil lewat chain hop 3xK.
    """
    tag = f"[W{worker_id}]"

    def _log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"{tag} {msg}",
            style=style,
        )

    caller_prefix = f"monetag_w{worker_id}"
    _log("Browser Monetag siap — IP dirotasi tiap sesi.", "green")

    while not (stop_event and stop_event.is_set()):
        if budget.is_exhausted() or not budget.has_capacity():
            break
        if not budget.reserve():
            break

        target_name = "monetag"
        max_uses = int(config.get("max_uses_per_day", 2))
        cooldown_hrs = float(config.get("proxy_cooldown_hours", 6.0))
        caller_id = f"{caller_prefix}_{int(time.time() * 1000)}"

        if chain_provider is not None:
            proxy = chain_provider.next_proxy(
                caller_id=caller_id, log_prefix=f"[W{worker_id}] "
            )
        else:
            proxy = proxy_manager.acquire_proxy(
                caller_id=caller_id,
                exclusive=True,
                verify_alive=False,
                target=target_name,
                max_uses_per_day=max_uses,
                cooldown_seconds=cooldown_hrs * 3600,
            )

        if not proxy:
            stats = proxy_manager.get_stats()
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
        try:
            t_usage = summary_manager.get_target_usage_summary(
                usage_proxy, target=target_name, max_uses_per_day=max_uses, cooldown_seconds=cooldown_hrs * 3600
            )
        except Exception:
            t_usage = {}
        _emit(
            event_callback,
            "proxy_assigned",
            worker_id=worker_id,
            proxy_id=proxy_id,
            ip=ip,
            country=country,
            target_usage=t_usage.get("summary_text", "Hit 1/2"),
            hit_count=t_usage.get("current_hit", 1),
            timezone=expected_geo.get("timezone"),
            locale=expected_geo.get("locale"),
        )

        chain_finished = False
        try:
            res = run_monetag_session(
                worker_id=worker_id,
                proxy_data=proxy,
                config=config,
                event_callback=event_callback,
            )
            if chain_provider is not None:
                chain_provider.finish_session(
                    proxy, True, log_prefix=f"[W{worker_id}] "
                )
                chain_finished = True
            else:
                proxy_manager.record_target_hit(proxy, target=target_name)
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
            _emit(event_callback, "session_completed", worker_id=worker_id, status="FAIL")
            budget.record("FAIL")
            if proxy_id:
                budget.mark_proxy(proxy_id)
            if chain_provider is not None:
                if not chain_finished:
                    error_kind = _classify_session_error(
                        e_run, stopping=bool(stop_event and stop_event.is_set())
                    )
                    chain_provider.finish_session(
                        proxy, False, e_run, error_kind,
                        log_prefix=f"[W{worker_id}] ",
                    )
            else:
                proxy_manager.report_failure(proxy, error_message=str(e_run))
        finally:
            if chain_provider is None:
                proxy_manager.release_proxy(proxy)

        # Jeda antar-sesi worker (dipercepat agar rotasi impresi tinggi)
        time.sleep(random.uniform(0.8, 1.8))
