#!/usr/bin/env python3
"""
automation.monetag.flow (v2 — Dynamic, High-Impression & CTR-Aware)
Dibangun ulang dari hasil observasi langsung `https://article.riztama.my.id/`:
1. Deteksi dinamis iklan Monetag yang benar-benar muncul di layar:
   - Vignette full-screen (`html > iframe` / `body > iframe`, z-index >= 1e6, kartu 355x160 di tengah)
     -> dwell 2.2-3.5s -> CTR natural (~42% klik Continue untuk High-CPM landing dwell, ~58% klik Close).
   - OnClick Popunder click-shield (`html > div` z-index >= 1e6)
     -> klik fisik lewat koordinat tombol nyata (menembus occlusion click-shield) -> tangkap tab Popunder
        (`ay267.com` / advertiser), tunggu redirect selesai, lalu dwell penuh 6-9.5s.
   - In-Page Push melayang (jika muncul di web target) -> viewability + klik sesuai CTR natural (~30%).
   - Direct Link (`uplcm.com/4/...`) -> dibuka dengan CTR natural (~45%) jika Popunder/Vignette sudah
     menghasilkan tab advertiser, atau 100% WAJIB dibuka jika belum ada 1 pun tab advertiser yang di-dwell.
2. Hemat CPU & kuota proxy residensial:
   - Memblokir tile peta non-iklan (`openstreetmap.org`) & video stream berat (`.mp4`/`.webm`/`.m3u8`).
   - Early-exit loop interaksi begitu Popunder/Vignette advertiser berhasil di-dwell.
   - Browser reuse untuk IP yang sama (multi-URL), 1 IP = 1 fingerprint C++ unik.
"""

from __future__ import annotations

import random
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from automation.engine import (
    WORKER_STARTUP_LOCK,
    build_camoufox_context_options,
    build_camoufox_kwargs,
    resolve_geo_profile,
)
from automation.monetag.humanizer import human_click, human_scroll, human_wander
from automation.session import SessionBudget, country_label
from core.proxy_manager import ProxyManager

_WORKER_BROWSERS: Dict[int, Dict[str, Any]] = {}
_WORKER_BROWSERS_LOCK = threading.Lock()

_MEDIA_EXTS = (".mp4", ".webm", ".m3u8", ".mp3", ".ogg", ".wav", ".avi", ".mov")
_BLOCKED_NON_AD_HOSTS = (
    "openstreetmap.org",
    "tile.openstreetmap.org",
)

_DEFAULT_AD_HOSTS = (
    "al5sm.com",
    "n6wxm.com",
    "ay267.com",
    "aichouphaugn.com",
    "uplcm.com",
    "quge5.com",
    "5gvci.com",
    "nap5k.com",
    "255md.com",
    "jhnwr.com",
    "ldrws.com",
    "monetag.com",
    "mndly.com",
    "simplistic-walk.com",
    "prizefamily.com",
    "hilltopads.com",
)

_DEFAULT_REDIRECT_HOSTS = (
    "ay267.com",
    "al5sm.com",
    "n6wxm.com",
    "uplcm.com",
    "quge5.com",
    "5gvci.com",
    "nap5k.com",
    "ldrws.com",
    "255md.com",
    "jhnwr.com",
    "simplistic-walk.com",
    "prizefamily.com",
)

_DEFAULT_AD_ZONES = ("12126541", "12126546", "12126548")

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

# Scan dinamis semua sinyal iklan Monetag & tombol nyata di halaman (kompatibel lintas website)
_DYNAMIC_MONETAG_SCAN_JS = """
(targetHost) => {
  const isVisible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 4 && r.height > 4;
  };

  // 1. Deteksi Vignette Full-Screen Overlay (`html > iframe` atau `body > iframe` z-index >= 1e6)
  let vignette = null;
  for (const f of document.querySelectorAll('html > iframe, body > iframe')) {
    if (!isVisible(f)) continue;
    const title = (f.getAttribute('title') || '').toLowerCase();
    if (title.includes('map')) continue;
    const st = window.getComputedStyle(f);
    const z = parseInt(st.zIndex || '0', 10);
    const r = f.getBoundingClientRect();
    if (st.position === 'fixed' && Number.isFinite(z) && z >= 1000000 && r.width >= 300 && r.height >= 300) {
      vignette = { tag: 'IFRAME', w: Math.round(r.width), h: Math.round(r.height), z };
      break;
    }
  }
  // Cek juga shadow/re-render Vignette di `html > div` yang berisi modal kartu terpusat
  if (!vignette) {
    for (const d of Array.from(document.documentElement.children)) {
      if (d.tagName !== 'DIV' || !isVisible(d)) continue;
      const st = window.getComputedStyle(d);
      const z = parseInt(st.zIndex || '0', 10);
      if (Number.isFinite(z) && z >= 1000000) {
        const txt = (d.innerText || '').toLowerCase();
        if (txt.includes('continue') && txt.includes('close')) {
          const r = d.getBoundingClientRect();
          vignette = { tag: 'DIV', w: Math.round(r.width), h: Math.round(r.height), z };
          break;
        }
      }
    }
  }

  // 2. Deteksi OnClick Popunder click-shield (`html > div` / `body > div` z-index >= 1e6, pointer-events: auto)
  let clickShield = false;
  for (const el of document.querySelectorAll('html > div, html > div > div, body > div')) {
    if (el.id === 'root' || el.id === '__next' || !isVisible(el)) continue;
    const st = window.getComputedStyle(el);
    const z = parseInt(st.zIndex || '0', 10);
    const r = el.getBoundingClientRect();
    if (Number.isFinite(z) && z >= 1000000 && st.pointerEvents !== 'none' && r.width >= 300 && r.height >= 300) {
      clickShield = true;
      break;
    }
  }

  // 3. Deteksi In-Page Push melayang di pojok layar (height 45-220px, fixed, z-index >= 1000)
  const pushCards = [];
  for (const child of Array.from(document.body.children)) {
    if (child.id === 'root' || child.id === '__next' || !isVisible(child)) continue;
    const st = window.getComputedStyle(child);
    const z = parseInt(st.zIndex || '0', 10);
    const r = child.getBoundingClientRect();
    if (st.position === 'fixed' && Number.isFinite(z) && z >= 1000 && r.height >= 45 && r.height <= 260 && r.width >= 180) {
      pushCards.push({
        x: Math.round(r.left + r.width * 0.45),
        y: Math.round(r.top + r.height * 0.50),
        w: Math.round(r.width),
        h: Math.round(r.height),
        text: (child.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60),
      });
    }
  }

  // 4. Kumpulkan koordinat tombol & link nyata yang terlihat di viewport untuk pemicu OnClick alami
  const controls = [];
  const vh = window.innerHeight || 800;
  const vw = window.innerWidth || 1280;
  for (const el of document.querySelectorAll('header nav button, main button, main a[href^="#"], header button[type="submit"]')) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.top < 10 || r.bottom > vh - 10 || r.left < 5 || r.right > vw - 5) continue;
    if (r.width < 32 || r.height < 20) continue;
    const txt = (el.innerText || el.getAttribute('title') || '').replace(/\\s+/g, ' ').trim();
    if (!txt || txt.toLowerCase().includes('dismiss') || txt.toLowerCase().includes('close')) continue;
    controls.push({
      x: Math.round(r.left + r.width * 0.5),
      y: Math.round(r.top + r.height * 0.5),
      label: txt.slice(0, 40),
    });
  }

  return {
    vignette,
    clickShield,
    pushCards,
    controls: controls.slice(0, 12),
    viewport: { w: vw, h: vh },
  };
}
"""


class MonetagSessionError(RuntimeError):
    """Kegagalan sesi Monetag yang perlu diklasifikasikan oleh worker chain."""


class MonetagVerificationError(MonetagSessionError):
    """IP exit/WebRTC bocor saat memakai proxy chain."""


class MonetagProxyError(MonetagSessionError):
    """Koneksi proxy/hop gagal saat navigasi."""


class MonetagNoAdError(MonetagSessionError):
    """Halaman termuat tetapi tidak ada impresi iklan Monetag yang benar-benar tampil."""


def _target_available(
    usage_proxy: Dict[str, Any],
    target: str,
    max_uses_per_day: int,
    cooldown_seconds: float,
    window_seconds: float = 24 * 3600,
) -> bool:
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


def _is_valid_loaded_url(url: str) -> bool:
    raw = str(url or "").strip().lower()
    return bool(
        raw
        and raw != "about:blank"
        and not raw.startswith("about:neterror")
        and not raw.startswith("about:certerror")
        and not raw.startswith("chrome-error://")
    )


def _emit(callback: Optional[Callable[[str, Dict[str, Any]], None]], event_type: str, **kwargs: Any) -> None:
    if callback:
        try:
            callback(event_type, kwargs)
        except Exception:
            pass


def close_worker_browser(worker_id: int) -> None:
    """Tutup instance browser Camoufox yang di-cache untuk worker tertentu."""
    with _WORKER_BROWSERS_LOCK:
        entry = _WORKER_BROWSERS.pop(worker_id, None)
    if entry and entry.get("cm"):
        try:
            entry["cm"].__exit__(None, None, None)
        except Exception:
            pass


def _setup_monetag_resource_filter(context: Any) -> None:
    """Blokir stream video/audio berat & tile OpenStreetMap non-iklan agar hemat CPU & bandwidth proxy."""
    def _route_handler(route: Any) -> None:
        try:
            req = route.request
            raw_url = (req.url or "").lower()
            clean_url = raw_url.split("?", 1)[0]
            if req.resource_type == "media" or clean_url.endswith(_MEDIA_EXTS):
                route.abort()
                return
            if any(h in raw_url for h in _BLOCKED_NON_AD_HOSTS):
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
    """Reuse proses Camoufox per-worker selama IP/proxy sama (multi-URL), fresh fingerprint untuk tiap IP baru."""
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
        _setup_monetag_resource_filter(context)
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


def run_monetag_session(
    worker_id: int,
    proxy_data: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Jalankan 1 sesi Monetag dinamis (Vignette CTR + OnClick Popunder + In-Page Push + Direct Link)."""
    raw_target_url = str(config.get("target_url") or "https://article.riztama.my.id/").strip()
    parsed = urlparse(raw_target_url)
    target_host = (parsed.netloc or "article.riztama.my.id").lower()
    target_domain = target_host.split(":")[0]
    target_url = f"{parsed.scheme or 'https'}://{target_host}/" if parsed.path.rstrip("/") == "/m" else raw_target_url

    direct_link_url = str(config.get("direct_link_url") or "https://uplcm.com/4/12124796").strip()
    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    lightweight = bool(config.get("lightweight", True))
    require_ad_impression = bool(config.get("require_ad_impression", True))

    # Pengaturan CTR natural per format iklan
    vignette_continue_ctr = float(config.get("vignette_continue_ctr", 0.42))
    in_page_push_ctr = float(config.get("in_page_push_ctr", 0.30))
    direct_link_ctr = float(config.get("direct_link_ctr", config.get("direct_link_chance", 0.45)))

    vignette_dwell_cfg = config.get("dwell_vignette_card_seconds") or {"min": 2.2, "max": 3.5}
    popup_dwell_cfg = config.get("dwell_popup_seconds") or {"min": 6.0, "max": 9.5}
    direct_dwell_cfg = config.get("dwell_direct_link_seconds") or {"min": 6.5, "max": 10.5}

    ad_hosts = {str(h).lower() for h in (config.get("ad_hosts") or _DEFAULT_AD_HOSTS)}
    ad_hosts.update(_DEFAULT_AD_HOSTS)
    ad_zones = {str(z) for z in (config.get("ad_zones") or _DEFAULT_AD_ZONES)}
    redirect_hosts = tuple(config.get("redirect_hosts") or _DEFAULT_REDIRECT_HOSTS)

    proxy_info = proxy_data or {}
    chain_mode = proxy_info.get("source") == "chain"
    allow_direct_ip = bool(config.get("allow_direct_ip", False))
    if not allow_direct_ip and (not proxy_info.get("host") or not proxy_info.get("port")):
        raise ValueError("Proxy residensial wajib aktif! Koneksi langsung (Direct IP VPS) diblokir demi keamanan akun.")

    proxy_label = (
        f"{proxy_info.get('host')}:{proxy_info.get('port')}"
        if proxy_info.get("host") and proxy_info.get("port")
        else "DIRECT_IP (Local Testing)"
    )

    session_start = time.time()
    stats: Dict[str, Any] = {
        "worker_id": worker_id,
        "success": False,
        "vignettes_viewed": 0,
        "vignettes_clicked": 0,
        "popunders_processed": 0,
        "push_viewed": 0,
        "push_clicked": 0,
        "direct_links_processed": 0,
        "proxy": proxy_label,
    }

    def log(msg: str, style: str = "white") -> None:
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"[W{worker_id}] {msg}",
            style=style,
            target_url=target_url,
        )

    log(f"🚀 Memulai sesi Monetag v2 (Dinamis) via {proxy_label}", "cyan")
    if chain_mode:
        log(
            f"🔎 Exit chain: {proxy_info.get('expected_ip')} | "
            f"{proxy_info.get('expected_isp') or '?'} / {proxy_info.get('expected_asn') or '?'}",
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
    ) as (_browser, context):
        page = context.new_page()

        ad_hits: Dict[str, int] = {}
        ad_hits_lock = threading.Lock()
        popups_opened: List[Any] = []
        processed_tabs = set()

        def on_request(req: Any) -> None:
            url = str(req.url or "")
            h = _host(url)
            matched = None
            if h:
                for expected in ad_hosts:
                    if h == expected or h.endswith("." + expected):
                        matched = expected
                        break
            if not matched:
                low = url.lower()
                for zone in ad_zones:
                    if zone in low:
                        matched = f"zone:{zone}"
                        break
            if not matched:
                return
            with ad_hits_lock:
                ad_hits[matched] = ad_hits.get(matched, 0) + 1
                first = ad_hits[matched] == 1
            if first:
                log(f"📡 Sinyal Monetag aktif: {matched}", "magenta")

        def on_new_page(new_p: Any) -> None:
            if new_p != page and new_p not in popups_opened:
                popups_opened.append(new_p)

        context.on("request", on_request)
        context.on("page", on_new_page)
        page.on("popup", on_new_page)

        def scan_page() -> Dict[str, Any]:
            try:
                res = page.evaluate(_DYNAMIC_MONETAG_SCAN_JS, target_domain)
                return res if isinstance(res, dict) else {}
            except Exception:
                return {}

        def _wait_tab_loaded(tab: Any, timeout_sec: float = 24.0) -> str:
            """Tunggu tab baru keluar dari about:blank, selesai melewati redirector Monetag, dan DOM termuat."""
            deadline = time.time() + timeout_sec
            while time.time() < deadline and not tab.is_closed():
                u = str(tab.url or "")
                if u and u != "about:blank":
                    break
                time.sleep(0.25)

            redir_deadline = min(deadline, time.time() + 12.0)
            while time.time() < redir_deadline and not tab.is_closed():
                h = _host(str(tab.url or ""))
                if h and not any(rh in h for rh in redirect_hosts):
                    break
                time.sleep(0.35)

            rem_ms = int(max(3000.0, (deadline - time.time()) * 1000))
            try:
                tab.wait_for_load_state("domcontentloaded", timeout=rem_ms)
            except Exception:
                pass
            while time.time() < deadline and not tab.is_closed():
                try:
                    st = tab.evaluate("() => document.readyState")
                    u = str(tab.url or "")
                    if u and u != "about:blank" and st in ("interactive", "complete"):
                        break
                except Exception:
                    pass
                time.sleep(0.35)
            return str(tab.url or "")

        def _dwell_advertiser_tab(tab: Any, dwell_cfg: Dict[str, Any], label: str) -> Optional[str]:
            """Dwell penuh di halaman pengiklan (advertiser) sampai selesai redirect & interaksi alami."""
            processed_tabs.add(tab)
            if tab.is_closed():
                return None
            try:
                tab.bring_to_front()
            except Exception:
                pass
            final_url = _wait_tab_loaded(tab, timeout_sec=24.0)
            if not _is_valid_loaded_url(final_url):
                log(f"⚠️ [{label}] Tab iklan gagal termuat ({final_url[:45]}), ditutup.", "yellow")
                try:
                    tab.close()
                except Exception:
                    pass
                return None

            dwell = random.uniform(float(dwell_cfg.get("min", 6.0)), float(dwell_cfg.get("max", 9.5)))
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage=f"📑 Dwell {label}",
                status=f"{_host(final_url)} ({dwell:.1f}s)",
            )
            log(f"🟢 [{label}] Landing page termuat ({_host(final_url) or final_url[:45]}) — dwell {dwell:.1f}s...", "magenta")
            end_t = time.time() + dwell
            clicked_once = False
            while time.time() < end_t and not tab.is_closed():
                if humanize_enabled:
                    human_wander(tab, duration_seconds=random.uniform(0.9, 1.5))
                    human_scroll(tab, scroll_amount=random.randint(180, 420), pause_range=(0.15, 0.3))
                    if not clicked_once and random.random() < 0.35:
                        try:
                            vp = tab.viewport_size or {"width": 1280, "height": 800}
                            tab.mouse.click(
                                random.randint(120, vp["width"] - 120),
                                random.randint(180, vp["height"] - 220),
                            )
                            clicked_once = True
                        except Exception:
                            pass
                time.sleep(0.6)
            try:
                tab.close()
            except Exception:
                pass
            if not page.is_closed():
                try:
                    page.bring_to_front()
                except Exception:
                    pass
            return final_url

        def drain_popups(tag: str) -> int:
            """Tangkap dan dwell semua tab advertiser/popunder baru yang terbuka."""
            done = 0
            time.sleep(0.45)
            candidates = [
                p for p in (list(popups_opened) + list(context.pages))
                if p != page and p not in processed_tabs and not p.is_closed()
            ]
            for tab in candidates:
                final_u = _dwell_advertiser_tab(tab, popup_dwell_cfg, f"Popunder/{tag}")
                if final_u:
                    stats["popunders_processed"] += 1
                    done += 1
            return done

        def check_main_tab_redirect() -> bool:
            """Jika tab utama ter-redirect ke pengiklan (mis. dari Vignette Continue), dwell lalu kembali."""
            if page.is_closed():
                return False
            curr_u = str(page.url or "")
            if curr_u and curr_u != "about:blank" and target_domain not in _host(curr_u):
                final_u = _wait_tab_loaded(page, timeout_sec=18.0)
                if _is_valid_loaded_url(final_u):
                    dwell = random.uniform(float(popup_dwell_cfg.get("min", 6.0)), float(popup_dwell_cfg.get("max", 9.5)))
                    log(f"🔄 Tab utama redirect ke advertiser ({_host(final_u)}) — dwell {dwell:.1f}s...", "magenta")
                    end_t = time.time() + dwell
                    while time.time() < end_t and not page.is_closed():
                        if humanize_enabled:
                            human_wander(page, duration_seconds=random.uniform(0.9, 1.5))
                            human_scroll(page, scroll_amount=random.randint(180, 380), pause_range=(0.15, 0.3))
                        time.sleep(0.6)
                    stats["popunders_processed"] += 1
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(1.0)
                except Exception:
                    pass
                return True
            return False

        def handle_vignette_if_visible() -> bool:
            """Tangani Vignette full-screen (`html > iframe`, kartu 355x160 di tengah) pakai koordinat akurat."""
            st = scan_page()
            vig = st.get("vignette")
            if not vig:
                return False

            stats["vignettes_viewed"] += 1
            want_continue = random.random() < vignette_continue_ctr
            v_dwell = random.uniform(
                float(vignette_dwell_cfg.get("min", 2.2)),
                float(vignette_dwell_cfg.get("max", 3.5)),
            )
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="🖼️ Vignette Banner",
                status=f"Dwell {v_dwell:.1f}s -> {'Continue' if want_continue else 'Close'}",
            )
            log(
                f"🖼️ Vignette full-screen ({vig.get('tag')}) terdeteksi — dwell {v_dwell:.1f}s lalu "
                f"{'klik Continue (CTR)' if want_continue else 'klik Close'}...",
                "bold yellow",
            )
            time.sleep(v_dwell)

            # Koordinat presisi kartu modal Vignette Monetag (355x160 terpusat di viewport):
            # Continue = pusat + (+60, +40), Close = pusat + (-104, +40)
            vp = st.get("viewport") or page.viewport_size or {"w": 1366, "h": 768}
            vw = float(vp.get("w") or vp.get("width") or 1366)
            vh = float(vp.get("h") or vp.get("height") or 768)
            dx = random.uniform(45.0, 80.0) if want_continue else random.uniform(-125.0, -85.0)
            dy = random.uniform(32.0, 48.0)
            target_x = max(10.0, min(vw - 10.0, (vw / 2.0) + dx))
            target_y = max(10.0, min(vh - 10.0, (vh / 2.0) + dy))

            human_click(page, (target_x, target_y))
            time.sleep(1.0)

            got_tab = drain_popups("VignetteContinue" if want_continue else "VignetteClose")
            got_redir = check_main_tab_redirect()
            if want_continue and (got_tab > 0 or got_redir):
                stats["vignettes_clicked"] += 1
            return True

        # ── 1. Buka Halaman Target ──
        _emit(event_callback, "session_started", worker_id=worker_id, target_url=target_url)
        _emit(event_callback, "stepper_update", worker_id=worker_id, stage="🌐 Kunjungan Web", status="Membuka web target...")
        chosen_ref = random.choice([
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://t.co/",
            "https://duckduckgo.com/",
        ])
        log(f"🌐 Membuka {target_url} (Referer: {_host(chosen_ref)})", "bold yellow")

        nav_ok = False
        last_nav_err: Optional[BaseException] = None
        for attempt in range(1, 3):
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000, referer=chosen_ref)
                cur = str(page.url or "")
                if cur.startswith("about:neterror") or cur.startswith("about:certerror"):
                    raise MonetagProxyError(f"Halaman gagal dimuat ({cur})")
                nav_ok = True
                break
            except Exception as exc:
                last_nav_err = exc
                if attempt == 1:
                    log(f"🔄 Retry #1 buka target ({str(exc).splitlines()[0][:70]})...", "yellow")
                    time.sleep(0.8)
        if not nav_ok and last_nav_err is not None:
            if _is_proxy_navigation_error(last_nav_err) or isinstance(last_nav_err, MonetagProxyError):
                raise MonetagProxyError(f"Navigasi target gagal lewat proxy: {last_nav_err}") from last_nav_err
            raise last_nav_err

        # ── 2. Scroll Alami & Tunggu Tag Monetag Injeksi (Vignette + OnClick Shield) ──
        time.sleep(random.uniform(2.0, 3.0))
        human_scroll(page, scroll_amount=random.randint(320, 480))
        human_wander(page, duration_seconds=random.uniform(1.0, 1.8))

        # ── 3. Tangani Vignette Full-Screen Lebih Dulu (Jika Muncul) ──
        handle_vignette_if_visible()

        # ── 4. Pemicu OnClick Popunder via Koordinat Tombol Nyata (Menembus Click-Shield) ──
        for click_i in range(1, 3):
            if stats["popunders_processed"] >= 1:
                log("⚡ Advertiser Popunder/Vignette sudah sukses di-dwell — lanjut tahap akhir (hemat CPU).", "green")
                break
            if page.is_closed():
                break

            handle_vignette_if_visible()
            if stats["popunders_processed"] >= 1:
                break

            st = scan_page()
            controls = st.get("controls") or []
            if controls:
                picked = random.choice(controls)
                log(
                    f"👆 [OnClick #{click_i}] Klik koordinat '{picked['label']}' "
                    f"({picked['x']}, {picked['y']}) | shield={'ON' if st.get('clickShield') else 'OFF'}",
                    "cyan",
                )
                human_click(page, (float(picked["x"]), float(picked["y"])))
            else:
                vp = page.viewport_size or {"width": 1366, "height": 768}
                rx = random.uniform(220.0, max(300.0, vp["width"] - 220.0))
                ry = random.uniform(180.0, max(260.0, vp["height"] - 220.0))
                log(f"👆 [OnClick #{click_i}] Klik area netral ({int(rx)}, {int(ry)})", "cyan")
                human_click(page, (rx, ry))

            time.sleep(0.9)
            check_main_tab_redirect()
            drain_popups(f"OnClick#{click_i}")

        # ── 5. Bonus In-Page Push (Jika Ada di Web Target) ──
        st_push = scan_page()
        push_cards = st_push.get("pushCards") or []
        if push_cards:
            stats["push_viewed"] = len(push_cards)
            if random.random() < in_page_push_ctr:
                card = random.choice(push_cards)
                log(f"💬 Klik In-Page Push ({card.get('text') or 'Push'})...", "yellow")
                try:
                    with context.expect_page(timeout=8000) as p_info:
                        human_click(page, (float(card["x"]), float(card["y"])))
                    if _dwell_advertiser_tab(p_info.value, popup_dwell_cfg, "In-Page Push"):
                        stats["push_clicked"] += 1
                except Exception:
                    drain_popups("PostPush")
            else:
                log("💬 In-Page Push tampil — jaga viewability (CTR natural).", "dim")
                time.sleep(random.uniform(1.2, 2.0))

        # ── 6. Direct Link Monetag (CTR Natural ~45%, atau 100% WAJIB jika belum ada tab advertiser) ──
        advertiser_tabs_dwelled = stats["popunders_processed"] + stats["push_clicked"]
        force_direct = advertiser_tabs_dwelled == 0
        if direct_link_url and (force_direct or random.random() < direct_link_ctr):
            if force_direct:
                log("🎯 Belum ada tab advertiser terbuka — 100% WAJIB buka & dwell Direct Link.", "bold yellow")
            else:
                log("🔗 Membuka Direct Link Monetag tambahan (CTR natural)...", "cyan")

            direct_page = None
            try:
                try:
                    with context.expect_page(timeout=10000) as new_p:
                        page.evaluate(
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
                    direct_page = new_p.value
                except Exception:
                    direct_page = context.new_page()
                    direct_page.goto(direct_link_url, wait_until="domcontentloaded", timeout=40000)

                if direct_page is not None:
                    final_dl = _dwell_advertiser_tab(direct_page, direct_dwell_cfg, "DirectLink")
                    if not final_dl:
                        # Auto-reload 1x jika Direct Link sempat macet di about:blank / neterror
                        log("🔄 Reload 1x Direct Link...", "yellow")
                        retry_p = context.new_page()
                        try:
                            retry_p.goto(direct_link_url, wait_until="domcontentloaded", timeout=35000)
                        except Exception:
                            pass
                        final_dl = _dwell_advertiser_tab(retry_p, direct_dwell_cfg, "DirectLink-Retry")
                    if final_dl:
                        stats["direct_links_processed"] += 1
            except Exception as exc_dl:
                log(f"⚠️ Catatan Direct Link: {str(exc_dl)[:80]}", "dim")
            drain_popups("PostDirect")
        elif direct_link_url:
            log(f"ℹ️ Direct Link dilewati demi CTR organik ({int(direct_link_ctr * 100)}%).", "dim")

        # Cleanup akhir
        drain_popups("Final")

        total_landing_dwelled = (
            stats["popunders_processed"] + stats["direct_links_processed"] + stats["push_clicked"]
        )
        ad_verified = bool(total_landing_dwelled > 0 or stats["vignettes_viewed"] > 0)

        if require_ad_impression and not ad_verified:
            _emit(
                event_callback,
                "stepper_update",
                worker_id=worker_id,
                stage="❌ TANPA IKLAN",
                status="Tidak ada iklan termuat — rotasi IP...",
            )
            raise MonetagNoAdError("Tidak ada impresi Vignette/Popunder/Direct Link yang berhasil termuat.")

        duration = round(time.time() - session_start, 1)
        stats["success"] = True
        stats["duration_seconds"] = duration
        stats["ad_hosts_hit"] = dict(ad_hits)
        stats["ad_verified"] = ad_verified

        log(
            f"🎉 Sesi Monetag selesai ({duration}s) | Vignette={stats['vignettes_viewed']}(klik:{stats['vignettes_clicked']}) "
            f"| Popunder={stats['popunders_processed']} | DirectLink={stats['direct_links_processed']} "
            f"| Push={stats['push_clicked']}/{stats['push_viewed']}",
            "bold green",
        )
        _emit(event_callback, "stepper_update", worker_id=worker_id, stage="✅ LOLOS", status=f"Selesai ({duration}s)")
        _emit(event_callback, "session_completed", worker_id=worker_id, status="PASS", target_url=target_url)
        return stats


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
    """Loop worker multi-sesi Monetag (kompatibel penuh dengan run_bot.py, GUI, dan unit test)."""
    tag = f"[W{worker_id}]"
    config = dict(config)
    target_urls = list(config.get("target_urls") or [])
    batch_urls = [u for u in (config.get("site_urls") or []) if u]
    session_index = max(0, worker_id - 1)

    def _log(msg: str, style: str = "white") -> None:
        _emit(event_callback, "log_message", worker_id=worker_id, message=f"{tag} {msg}", style=style)

    def _target_key(url: str) -> str:
        host = _host(url)
        return f"monetag:{host}" if host else "monetag"

    caller_prefix = f"monetag_w{worker_id}"
    _log("Worker Monetag v2 siap — dinamis, CTR terukur, hemat CPU.", "green")

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
            if getattr(budget, "unlimited", False) and reset_pool_callback and not getattr(proxy_manager, "supabase_enabled", False):
                reset_pool_callback()
                _log("Pool IP habis — direset untuk rotasi ulang.", "cyan")
                time.sleep(1.0)
                continue
            _log("Menunggu IP tersedia / selesai cooldown...", "dim")
            time.sleep(5.0)
            continue

        proxy_id = proxy.get("id") or proxy.get("proxy_url")
        ip = proxy.get("expected_ip") or proxy.get("ip_detected") or proxy.get("host", "?")
        country = country_label(proxy.get("country"))
        expected_geo = resolve_geo_profile(proxy)
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
                if post_session is not None:
                    post_session(worker_id, proxy, session_config)
                summary_manager.record_target_hit(usage_proxy, target=target_name)
                budget.record("PASS")
                if proxy_id:
                    budget.mark_proxy(proxy_id)
            except Exception as e_run:
                _log(f"❌ Error sesi Monetag: {e_run}", "bold red")
                _emit(event_callback, "stepper_update", worker_id=worker_id, stage="❌ GAGAL", status=str(e_run)[:40])
                _emit(event_callback, "session_completed", worker_id=worker_id, status="FAIL", target_url=url)
                budget.record("FAIL")
                if proxy_id:
                    budget.mark_proxy(proxy_id)
                if chain_provider is not None:
                    error_kind = _classify_session_error(
                        e_run, stopping=bool(stop_event and stop_event.is_set())
                    )
                    chain_provider.finish_session(
                        proxy, False, e_run, error_kind, log_prefix=f"[W{worker_id}] ",
                    )
                else:
                    try:
                        proxy_manager.report_failure(proxy, error_message=str(e_run))
                    finally:
                        proxy_manager.release_proxy(proxy)
                released = True
                break

            time.sleep(random.uniform(0.6, 1.4))

        if not released:
            if chain_provider is not None:
                close_worker_browser(worker_id)
                chain_provider.finish_session(proxy, False, error_kind="batch", log_prefix=f"[W{worker_id}] ")
            else:
                proxy_manager.release_proxy(proxy)
            if not ran_any:
                time.sleep(1.0)

        time.sleep(random.uniform(0.6, 1.4))

    close_worker_browser(worker_id)
