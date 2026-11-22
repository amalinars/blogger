#!/usr/bin/env python3
"""
automation.artikle_ad.flow
Alur dinamis untuk website artikel multi-format iklan (mis. HilltopAds + Monetag Direct Link):
- Membaca struktur DOM secara dinamis tanpa hardcode judul/URL iklan:
  1. Banner 300x250 (<aside aria-label*="banner/sponsored"> atau iframe lintas-domain)
  2. In-Page Push melayang (body > div fixed z-index tinggi) — viewability + klik natural
  3. Video Slider (<video> / player melayang) — muted autoplay aktif agar VAST terhitung
  4. Popunder (jika terpasang) — otomatis tertangkap saat klik elemen alami lalu di-dwell
  5. Direct Link pada kartu artikel (main a[target="_blank"] lintas-domain / a[rel~="sponsored"])
     — memilih N artikel berbeda per sesi, menunggu redirect selesai, lalu dwell penuh.
- Mendukung mode Direct IP (testing lokal tanpa proxy) maupun Proxy / Proxy Chain.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from automation.engine import (
    WORKER_STARTUP_LOCK,
    build_camoufox_context_options,
    build_camoufox_kwargs,
)
from automation.monetag.humanizer import human_click, human_scroll, human_wander

_DEFAULT_AD_HOSTS = (
    "prizefamily.com",
    "hilltopads.com",
    "uplcm.com",
    "monetag.com",
    "quge5.com",
    "5gvci.com",
    "al5sm.com",
    "nap5k.com",
)

_DEFAULT_REDIRECT_HOSTS = (
    "uplcm.com",
    "prizefamily.com",
    "quge5.com",
    "5gvci.com",
    "al5sm.com",
    "nap5k.com",
)

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

# Scan dinamis struktur halaman: banner, in-page push, video slider, dan link artikel eksternal.
_DYNAMIC_SCAN_JS = """
(targetHost) => {
  const hostOf = (raw) => {
    try { return new URL(raw, location.href).hostname.toLowerCase(); }
    catch { return ''; }
  };
  const isVisible = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity || '1') === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 4 && rect.height > 4;
  };

  // 1. Banner slot (aside aria-label banner/sponsored atau iframe lintas-domain)
  const banners = [];
  for (const el of document.querySelectorAll('aside[aria-label*="banner" i], aside[aria-label*="sponsored" i], iframe[src]')) {
    if (!isVisible(el)) continue;
    const isIframe = el.tagName === 'IFRAME';
    const srcHost = isIframe ? hostOf(el.getAttribute('src') || '') : '';
    if (isIframe && (!srcHost || srcHost === targetHost || srcHost.endsWith('.' + targetHost))) continue;
    const r = el.getBoundingClientRect();
    banners.push({ tag: el.tagName, srcHost, w: Math.round(r.width), h: Math.round(r.height) });
  }

  // 2. In-Page Push widget (direct child of body di luar #root dengan position:fixed & z-index tinggi)
  const pushCards = [];
  for (const child of Array.from(document.body.children)) {
    if (child.id === 'root' || child.id === '__next' || !isVisible(child)) continue;
    const st = window.getComputedStyle(child);
    const z = parseInt(st.zIndex || '0', 10);
    if (st.position === 'fixed' && Number.isFinite(z) && z >= 1000) {
      // Cari kartu push individual di dalamnya (hindari tombol close)
      const candidates = Array.from(child.querySelectorAll('div, a')).filter((el) => {
        if (!isVisible(el)) return false;
        const r = el.getBoundingClientRect();
        const txt = (el.innerText || '').trim();
        return r.width >= 160 && r.height >= 45 && r.height <= 220 && txt.length >= 6;
      });
      const picked = candidates.length ? candidates : [child];
      const seenRects = [];
      for (const el of picked) {
        const r = el.getBoundingClientRect();
        const dup = seenRects.some((s) => Math.abs(s.top - r.top) < 12 && Math.abs(s.left - r.left) < 12);
        if (dup) continue;
        seenRects.push(r);
        pushCards.push({
          x: Math.round(r.left + r.width * 0.45),
          y: Math.round(r.top + r.height * 0.50),
          w: Math.round(r.width),
          h: Math.round(r.height),
          text: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 60),
        });
      }
    }
  }

  // 3. Video Slider (elemen <video> yang tampil atau container video fixed)
  const videos = [];
  for (const v of document.querySelectorAll('video')) {
    if (!isVisible(v)) continue;
    const r = v.getBoundingClientRect();
    videos.push({
      w: Math.round(r.width),
      h: Math.round(r.height),
      paused: Boolean(v.paused),
      currentTime: Number(v.currentTime || 0),
    });
  }

  // 4. Direct Link pada kartu artikel (a[rel~="sponsored"] atau main a[target="_blank"] lintas-domain)
  const articleLinksMap = new Map();
  const linkSelector = 'a[rel~="sponsored"], main a[target="_blank"][href], article a[href]';
  for (const a of document.querySelectorAll(linkSelector)) {
    if (!isVisible(a)) continue;
    const href = (a.getAttribute('href') || '').trim();
    if (!href || href.startsWith('#') || href.startsWith('javascript:')) continue;
    const h = hostOf(href);
    const isExternal = Boolean(h && h !== targetHost && !h.endsWith('.' + targetHost));
    const isSponsored = (a.getAttribute('rel') || '').toLowerCase().includes('sponsored');
    if (!isExternal && !isSponsored) continue;

    // Prioritaskan link judul (h1/h2/h3) atau tombol teks pendek ("Read", "Read Dispatch") dibanding gambar
    const text = (a.innerText || a.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
    const inHeading = Boolean(a.closest('h1, h2, h3'));
    const hasImg = Boolean(a.querySelector('img'));
    const score = (inHeading ? 3 : 0) + (!hasImg && text.length > 0 ? 2 : 0) + (text.length > 10 ? 1 : 0);
    const prev = articleLinksMap.get(href);
    if (!prev || score > prev.score) {
      articleLinksMap.set(href, {
        href,
        host: h,
        text: text.slice(0, 70),
        score,
        inHeading,
      });
    }
  }

  return {
    banners,
    pushCards,
    videos,
    articleLinks: Array.from(articleLinksMap.values()),
  };
}
"""


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


def _is_proxy_error(err: BaseException) -> bool:
    txt = str(err or "").lower()
    return any(m in txt for m in _PROXY_ERROR_MARKERS)


def _is_shutdown_error(err: BaseException) -> bool:
    txt = str(err or "").lower()
    return any(m in txt for m in _SHUTDOWN_MARKERS)


def _emit(cb: Optional[Callable[[str, Dict[str, Any]], None]], etype: str, **kwargs: Any) -> None:
    if cb:
        try:
            cb(etype, kwargs)
        except Exception:
            pass


def run_article_ad_session(
    worker_id: int,
    proxy_data: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Jalankan 1 sesi dinamis di website artikel (HilltopAds + Monetag Direct Link)."""
    target_url = str(config.get("target_url") or "https://ghasima.ai.studio/").strip()
    target_host = _host(target_url)
    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    lightweight = bool(config.get("lightweight", True))
    article_clicks_target = max(1, int(config.get("article_clicks_per_session", 2)))
    push_click_chance = float(config.get("push_click_chance", 0.40))

    banner_dwell_cfg = config.get("banner_dwell_seconds") or {"min": 3.0, "max": 5.0}
    video_dwell_cfg = config.get("video_slider_dwell_seconds") or {"min": 5.0, "max": 8.0}
    popup_dwell_cfg = config.get("popup_dwell_seconds") or {"min": 5.0, "max": 8.5}
    article_dwell_cfg = config.get("article_link_dwell_seconds") or {"min": 6.0, "max": 10.0}
    redirect_hosts = tuple(config.get("redirect_hosts") or _DEFAULT_REDIRECT_HOSTS)
    ad_hosts = {str(h).lower() for h in (config.get("ad_hosts") or _DEFAULT_AD_HOSTS)}

    session_start = time.time()
    proxy_label = (
        f"{proxy_data.get('host')}:{proxy_data.get('port')}"
        if proxy_data and proxy_data.get("host")
        else "DIRECT_IP (Local Testing)"
    )

    def log(msg: str, style: str = "white") -> None:
        if event_callback is None:
            print(f"[W{worker_id}-ArtikleAd] {msg}", flush=True)
        _emit(
            event_callback,
            "log_message",
            worker_id=worker_id,
            message=f"[W{worker_id}] {msg}",
            style=style,
            target_url=target_url,
        )

    _emit(event_callback, "session_started", worker_id=worker_id, target_url=target_url)
    _emit(event_callback, "stepper_update", worker_id=worker_id, step_key="open_web", stage="🌐 Kunjungan Web", status="Membuka web target...", target_url=target_url)
    log(f"🚀 Memulai sesi dinamis di {target_url} | koneksi: {proxy_label}", "cyan")

    # Penting untuk HilltopAds Video Slider: izinkan muted autoplay agar iklan video berputar & tercatat.
    video_friendly_prefs: Dict[str, Any] = {
        "media.autoplay.default": 0,
        "media.autoplay.blocking_policy": 0,
        "media.volume_scale": "0.0",
        "media.rdd-process.enabled": True,
    }
    if proxy_data and proxy_data.get("source") == "chain":
        video_friendly_prefs["media.peerconnection.enabled"] = False

    camoufox_kwargs = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize_enabled,
        allow_ads=True,
        extra_prefs=video_friendly_prefs,
        lightweight=lightweight,
    )
    # Pastikan pref video_friendly menang setelah POTATO_FIREFOX_PREFS diterapkan
    camoufox_kwargs["firefox_user_prefs"].update(video_friendly_prefs)
    if isinstance(camoufox_kwargs.get("env"), dict):
        camoufox_kwargs["env"].pop("MOZ_DISABLE_RDD_PROCESS", None)
    context_opts = build_camoufox_context_options(proxy_data)

    with WORKER_STARTUP_LOCK:
        cm = Camoufox(**camoufox_kwargs)
        browser = cm.__enter__()

    context = None
    ad_hits: Dict[str, int] = {}
    popups_opened: List[Any] = []
    processed_tabs = set()
    stats = {
        "worker_id": worker_id,
        "target_url": target_url,
        "proxy": proxy_label,
        "banners_viewed": 0,
        "video_slider_viewed": 0,
        "push_detected": 0,
        "push_clicked": 0,
        "popunders_dwelled": 0,
        "articles_clicked": 0,
        "article_urls_dwelled": [],
        "success": False,
    }

    try:
        context = browser.new_context(**context_opts)
        page = context.new_page()

        def on_request(req: Any) -> None:
            h = _host(str(req.url or ""))
            if not h:
                return
            for expected in ad_hosts:
                if h == expected or h.endswith("." + expected):
                    ad_hits[expected] = ad_hits.get(expected, 0) + 1
                    if ad_hits[expected] == 1:
                        log(f"📡 Ad network terdeteksi: {expected}", "magenta")
                    break

        def on_new_page(new_p: Any) -> None:
            if new_p != page and new_p not in popups_opened:
                popups_opened.append(new_p)

        context.on("request", on_request)
        context.on("page", on_new_page)
        page.on("popup", on_new_page)

        def _wait_tab_loaded(tab: Any, timeout_sec: float = 22.0) -> str:
            deadline = time.time() + timeout_sec
            while time.time() < deadline and not tab.is_closed():
                u = str(tab.url or "")
                if u and u != "about:blank":
                    break
                time.sleep(0.25)

            redir_deadline = min(deadline, time.time() + 12.0)
            while time.time() < redir_deadline and not tab.is_closed():
                u = str(tab.url or "")
                if u.lower().startswith(("about:neterror", "about:certerror", "chrome-error://")):
                    return u
                h = _host(u)
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

        def _dwell_tab(tab: Any, dwell_cfg: Dict[str, Any], label: str) -> Optional[str]:
            """Tunggu tab selesai redirect + load DOM, lalu dwell natural dan tutup."""
            processed_tabs.add(tab)
            if tab.is_closed():
                return None
            try:
                tab.bring_to_front()
            except Exception:
                pass
            final_url = _wait_tab_loaded(tab, timeout_sec=24.0)
            if not _is_valid_loaded_url(final_url):
                log(f"⚠️ [{label}] Tab gagal memuat halaman tujuan ({final_url[:50]}), ditutup.", "yellow")
                try:
                    tab.close()
                except Exception:
                    pass
                return None

            dwell = random.uniform(float(dwell_cfg.get("min", 6.0)), float(dwell_cfg.get("max", 10.0)))
            log(f"🟢 [{label}] Termuat ({_host(final_url) or final_url[:45]}) — dwell {dwell:.1f}s...", "magenta")
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
                time.sleep(0.7)
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

        def drain_popups(reason: str) -> int:
            """Tangkap dan dwell semua tab popunder (mis. HilltopAds Popunder) yang terbuka otomatis."""
            done = 0
            time.sleep(0.4)
            candidates = [
                p for p in (list(popups_opened) + list(context.pages))
                if p != page and p not in processed_tabs and not p.is_closed()
            ]
            for tab in candidates:
                final_u = _dwell_tab(tab, popup_dwell_cfg, f"Popunder/{reason}")
                if final_u:
                    stats["popunders_dwelled"] += 1
                    done += 1
            return done

        def scan_dom() -> Dict[str, Any]:
            try:
                res = page.evaluate(_DYNAMIC_SCAN_JS, target_host)
                return res if isinstance(res, dict) else {}
            except Exception:
                return {}

        # ── 1. Buka Web Utama ──
        organic_refs = [
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://t.co/",
            "https://duckduckgo.com/",
        ]
        chosen_ref = random.choice(organic_refs)
        log(f"🌐 Membuka halaman utama (Referer: {_host(chosen_ref)})...", "yellow")
        nav_ok = False
        last_err: Optional[BaseException] = None
        for attempt in range(1, 3):
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000, referer=chosen_ref)
                cur = str(page.url or "")
                if cur.startswith("about:neterror") or cur.startswith("about:certerror"):
                    raise RuntimeError(f"Halaman gagal dimuat ({cur})")
                nav_ok = True
                break
            except Exception as exc:
                last_err = exc
                if attempt == 1:
                    time.sleep(1.0)
        if not nav_ok and last_err is not None:
            if proxy_data and _is_proxy_error(last_err):
                raise RuntimeError(f"Navigasi gagal lewat proxy: {last_err}") from last_err
            raise last_err

        # Tunggu skrip iklan pihak ketiga (HilltopAds Banner, In-Page Push, Video Slider) inisialisasi
        time.sleep(random.uniform(2.5, 4.0))
        human_wander(page, duration_seconds=random.uniform(1.0, 1.8))

        # ── 2. Scroll ke Banner 300x250 & Scan Dinamis Konten/Iklan ──
        _emit(event_callback, "stepper_update", worker_id=worker_id, step_key="banner_push", stage="🖼️ Banner & Push", status="Dwell Banner & Scan DOM...", target_url=target_url)
        try:
            banner_loc = page.locator('aside[aria-label*="banner" i], aside[aria-label*="sponsored" i]').first
            if banner_loc.is_visible(timeout=2000):
                banner_loc.scroll_into_view_if_needed()
                b_dwell = random.uniform(float(banner_dwell_cfg.get("min", 3.0)), float(banner_dwell_cfg.get("max", 5.0)))
                log(f"🖼️ Slot Banner 300x250 terlihat — dwell viewability {b_dwell:.1f}s...", "cyan")
                human_wander(page, duration_seconds=b_dwell)
                stats["banners_viewed"] += 1
        except Exception:
            human_scroll(page, scroll_amount=random.randint(320, 520))

        # Interaksi ringan pada tombol non-filter untuk memicu Popunder tanpa menyembunyikan artikel lain
        try:
            nav_btns = page.locator(
                'header button:has-text("Latest"), button:has-text("Location Details")'
            )
            if nav_btns.count() > 0:
                idx = random.randint(0, nav_btns.count() - 1)
                btn = nav_btns.nth(idx)
                if btn.is_visible(timeout=1000):
                    log("👆 Klik navigasi alami (memicu Popunder jika aktif)...", "cyan")
                    human_click(page, btn)
                    time.sleep(1.2)
                    drain_popups("NavClick")
        except Exception:
            pass

        # Scan DOM secara dinamis setelah scroll & interaksi awal
        scan = scan_dom()
        banners = scan.get("banners") or []
        push_cards = scan.get("pushCards") or []
        videos = scan.get("videos") or []
        article_links = scan.get("articleLinks") or []

        if banners and stats["banners_viewed"] == 0:
            stats["banners_viewed"] = len(banners)

        log(
            f"🔎 Hasil Scan Dinamis: Banner={len(banners)} | In-Page Push={len(push_cards)} "
            f"| Video Slider={len(videos)} | Artikel Direct Link={len(article_links)}",
            "bold cyan",
        )

        # ── 3. Viewability Video Slider HilltopAds (Jika Muncul) ──
        if videos:
            v_dwell = random.uniform(float(video_dwell_cfg.get("min", 5.0)), float(video_dwell_cfg.get("max", 8.0)))
            log(f"🎬 Video Slider terdeteksi ({len(videos)} player) — dwell {v_dwell:.1f}s agar VAST tercatat...", "magenta")
            human_wander(page, duration_seconds=v_dwell)
            stats["video_slider_viewed"] = len(videos)

        # ── 4. HilltopAds In-Page Push (Viewability + Klik Natural) ──
        if push_cards:
            stats["push_detected"] = len(push_cards)
            should_click_push = random.random() < push_click_chance
            if should_click_push:
                chosen_push = random.choice(push_cards)
                log(
                    f"💬 Mengklik kartu In-Page Push HilltopAds: '{chosen_push.get('text') or 'Push Card'}'...",
                    "yellow",
                )
                try:
                    with context.expect_page(timeout=8000) as push_page_info:
                        human_click(page, (float(chosen_push["x"]), float(chosen_push["y"])))
                    push_tab = push_page_info.value
                    final_push_u = _dwell_tab(push_tab, popup_dwell_cfg, "In-Page Push")
                    if final_push_u:
                        stats["push_clicked"] += 1
                except Exception as exc_push:
                    log(f"Catatan klik In-Page Push: {str(exc_push)[:80]}", "dim")
                    drain_popups("PostPush")
            else:
                log("💬 In-Page Push terlihat — pertahankan viewability (tanpa klik demi CTR natural).", "dim")
                time.sleep(random.uniform(1.5, 2.5))

        # ── 5. Klik N Artikel Berbeda (Monetag Direct Link Tertanam di Artikel) ──
        if article_links:
            random.shuffle(article_links)
            target_count = min(article_clicks_target, len(article_links))
            log(f"📰 Menargetkan {target_count} artikel berbeda (dari {len(article_links)} tersedia) untuk diklik & dwell...", "bold yellow")

            for art in article_links:
                if stats["articles_clicked"] >= target_count:
                    break
                cur_num = stats["articles_clicked"] + 1
                href = art["href"]
                title_hint = art.get("text") or href
                _emit(
                    event_callback,
                    "stepper_update",
                    worker_id=worker_id,
                    step_key="article_1" if cur_num == 1 else "article_2",
                    stage=f"📰 Artikel #{cur_num}/{target_count}",
                    status=f"Dwell {title_hint[:32]}",
                    target_url=target_url,
                )
                log(f"👆 [Artikel #{cur_num}/{target_count}] Mengklik: {title_hint[:60]} ({art.get('host')})", "cyan")
                try:
                    # Utamakan link judul (h1/h2/h3) agar area klik lebar & aman dari overlay push kanan-bawah
                    href_esc = href.replace("\\", "\\\\").replace('"', '\\"')
                    link_loc = None
                    for sel in (
                        f'main h1 a[href="{href_esc}"], main h2 a[href="{href_esc}"], main h3 a[href="{href_esc}"]',
                        f'main a[href="{href_esc}"], article a[href="{href_esc}"]',
                        f'a[href="{href_esc}"]',
                    ):
                        cand_group = page.locator(sel)
                        for k in range(cand_group.count()):
                            cand = cand_group.nth(k)
                            if cand.is_visible(timeout=800):
                                link_loc = cand
                                break
                        if link_loc is not None:
                            break
                    if link_loc is None:
                        log(f"⚠️ [Artikel #{cur_num}] Elemen link tidak terlihat, lanjut kandidat berikut.", "yellow")
                        continue

                    try:
                        # Posisikan ke tengah viewport supaya tidak tertutup kartu In-Page Push kanan-bawah
                        link_loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
                    except Exception:
                        link_loc.scroll_into_view_if_needed()
                    time.sleep(random.uniform(0.4, 0.9))
                    if humanize_enabled:
                        human_wander(page, duration_seconds=random.uniform(0.6, 1.2))

                    art_tab = None
                    for click_try in range(2):
                        before_pages = set(context.pages)
                        try:
                            with context.expect_page(timeout=10000) as art_page_info:
                                human_click(page, link_loc)
                            art_tab = art_page_info.value
                            break
                        except Exception:
                            # Cek jika tab baru sempat terbuka tepat di luar window expect_page
                            new_tabs = [
                                p for p in context.pages
                                if p not in before_pages and p != page and p not in processed_tabs and not p.is_closed()
                            ]
                            if new_tabs:
                                art_tab = new_tabs[-1]
                                break
                            if click_try == 0:
                                drain_popups(f"InterceptArt#{cur_num}")
                                try:
                                    link_loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
                                except Exception:
                                    pass

                    if art_tab is not None:
                        final_u = _dwell_tab(art_tab, article_dwell_cfg, f"Artikel#{cur_num}")
                        if final_u:
                            stats["articles_clicked"] += 1
                            stats["article_urls_dwelled"].append(final_u)
                    else:
                        log(f"⚠️ [Artikel #{cur_num}] Tab tidak terbuka setelah 2 percobaan, lanjut kandidat berikut.", "yellow")
                    drain_popups(f"PostArt#{cur_num}")
                except Exception as exc_art:
                    log(f"⚠️ Gagal proses Artikel #{cur_num}: {str(exc_art)[:90]}", "yellow")

                if stats["articles_clicked"] < target_count:
                    time.sleep(random.uniform(1.0, 2.0))
        else:
            log("⚠️ Tidak ada link artikel eksternal (<a target='_blank'>) yang terdeteksi di <main>.", "yellow")

        # Pembersihan akhir jika masih ada popunder tertunda
        drain_popups("Final")

        stats["duration_seconds"] = round(time.time() - session_start, 1)
        stats["ad_hosts_hit"] = ad_hits
        stats["success"] = bool(
            stats["articles_clicked"] > 0
            or stats["push_clicked"] > 0
            or stats["popunders_dwelled"] > 0
            or stats["banners_viewed"] > 0
        )

        log(
            f"🎉 Sesi selesai ({stats['duration_seconds']}s) | "
            f"Artikel DirectLink={stats['articles_clicked']}/{article_clicks_target} | "
            f"Banner={stats['banners_viewed']} | PushKlik={stats['push_clicked']}/{stats['push_detected']} | "
            f"VideoSlider={stats['video_slider_viewed']} | Popunder={stats['popunders_dwelled']}",
            "bold green",
        )
        expected_imp = (
            (1 if stats["banners_viewed"] > 0 else 0)
            + (1 if stats["push_detected"] > 0 else 0)
            + (1 if stats["video_slider_viewed"] > 0 else 0)
            + int(stats["popunders_dwelled"])
            + int(stats["articles_clicked"])
        )
        metrics = {
            "banner": 1 if stats["banners_viewed"] > 0 else 0,
            "in_page_push": 1 if stats["push_detected"] > 0 else 0,
            "video_slider": 1 if stats["video_slider_viewed"] > 0 else 0,
            "popunder": int(stats["popunders_dwelled"]),
            "direct_link": int(stats["articles_clicked"]),
            "expected_impressions": expected_imp,
        }
        status_code = "PASS" if stats["success"] else "FAIL"
        _emit(
            event_callback,
            "stepper_update",
            worker_id=worker_id,
            step_key="done" if stats["success"] else "failed",
            stage="✅ LOLOS" if stats["success"] else "❌ GAGAL",
            status=f"Selesai ({stats['duration_seconds']}s)",
            target_url=target_url,
        )
        _emit(
            event_callback,
            "session_completed",
            worker_id=worker_id,
            status=status_code,
            target_url=target_url,
            duration_seconds=stats["duration_seconds"],
            metrics=metrics,
        )
        return stats
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


def article_ad_worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: Optional[Any] = None,
    budget: Optional[Any] = None,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    chain_provider: Optional[Any] = None,
    reset_pool_callback: Optional[Callable[[], None]] = None,
) -> None:
    """Loop multi-sesi untuk mode Direct IP maupun Proxy/Chain."""
    max_sessions = int(config.get("max_sessions_per_run", 1))
    use_direct = bool(config.get("direct_ip", True)) and proxy_manager is None and chain_provider is None
    target_url = str(config.get("target_url") or "https://ghasima.ai.studio/")
    target_key = f"artikle_ad:{_host(target_url) or 'site'}"
    max_uses = int(config.get("max_uses_per_day", 2))
    cooldown_hours = float(config.get("proxy_cooldown_hours", 6.0))
    cooldown_secs = cooldown_hours * 3600
    done = 0
    last_wait_log = 0.0

    def _log(msg: str, style: str = "white") -> None:
        if event_callback is None:
            print(f"[W{worker_id}-ArtikleAd] {msg}", flush=True)
        else:
            _emit(
                event_callback,
                "log_message",
                worker_id=worker_id,
                message=f"[W{worker_id}] {msg}",
                style=style,
                target_url=target_url,
            )

    def _wait(seconds: float) -> None:
        if stop_event is not None:
            stop_event.wait(seconds)
        else:
            time.sleep(seconds)

    while not (stop_event and stop_event.is_set()):
        if max_sessions > 0 and done >= max_sessions:
            break
        if budget is not None and (budget.is_exhausted() or not budget.has_capacity()):
            break

        proxy = None
        if not use_direct:
            caller_id = f"artikle_w{worker_id}_{int(time.time() * 1000)}"
            try:
                if chain_provider is not None:
                    proxy = chain_provider.next_proxy(
                        caller_id=caller_id,
                        log_prefix=f"[W{worker_id}] ",
                        target=target_key,
                    )
                elif proxy_manager is not None:
                    proxy = proxy_manager.acquire_proxy(
                        caller_id=caller_id,
                        exclusive=True,
                        verify_alive=False,
                        target=target_key,
                        max_uses_per_day=max_uses,
                        cooldown_seconds=cooldown_secs,
                    )
            except Exception as exc_acq:
                _log(f"⚠️ Gagal mengalokasikan proxy: {exc_acq}", "yellow")
                _wait(5.0)
                continue

            if not proxy:
                if (
                    reset_pool_callback is not None
                    and not getattr(proxy_manager, "supabase_enabled", False)
                ):
                    reset_pool_callback()
                    _log("♻️ Pool proxy lokal habis — direset untuk rotasi ulang.", "cyan")
                    _wait(1.0)
                    continue

                miss_reason = (
                    getattr(chain_provider, "last_miss_reason", "")
                    if chain_provider is not None
                    else "pool_empty"
                )
                if miss_reason in ("", "pool_empty"):
                    now = time.time()
                    if now - last_wait_log >= 30.0:
                        _emit(
                            event_callback,
                            "stepper_update",
                            worker_id=worker_id,
                            step_key="proxy",
                            stage="⏳ Menunggu IP",
                            status=f"Semua IP cooldown ({cooldown_hours:g}j) / limit ({max_uses}x)",
                            target_url=target_url,
                        )
                        _log(
                            f"⏳ Belum ada proxy tersedia untuk {target_key} "
                            f"(semua IP sedang cooldown {cooldown_hours:g}j / limit {max_uses}x/hari / IN_USE). "
                            f"Menunggu... (tip: turunkan --cooldown atau naikkan --max-uses)",
                            "yellow",
                        )
                        last_wait_log = now
                    _wait(5.0)
                else:
                    _emit(
                        event_callback,
                        "stepper_update",
                        worker_id=worker_id,
                        step_key="proxy",
                        stage="🔄 Rotasi Proxy",
                        status="Mencari hop/IP lain...",
                        target_url=target_url,
                    )
                    _wait(1.0)
                continue

            last_wait_log = 0.0
            _emit(
                event_callback,
                "proxy_assigned",
                worker_id=worker_id,
                ip=proxy.get("expected_ip") or proxy.get("ip_detected") or proxy.get("host", "—"),
                country=proxy.get("country") or "Unknown",
                target_network="📰 ArtikleAd",
                target_url=target_url,
            )

        if budget is not None and not budget.reserve():
            if proxy and chain_provider is not None:
                chain_provider.finish_session(proxy, False, error_kind="shutdown", log_prefix=f"[W{worker_id}] ")
            elif proxy and proxy_manager is not None:
                proxy_manager.release_proxy(proxy)
            break

        try:
            res = run_article_ad_session(
                worker_id=worker_id,
                proxy_data=proxy,
                config=config,
                event_callback=event_callback,
            )
            done += 1
            if budget is not None:
                budget.record("PASS" if res.get("success") else "FAIL")
            if proxy:
                if chain_provider is not None:
                    if res.get("success"):
                        chain_provider.finish_session(proxy, True, log_prefix=f"[W{worker_id}] ")
                    else:
                        chain_provider.finish_session(
                            proxy,
                            False,
                            RuntimeError("Sesi tidak menghasilkan impresi/artikel"),
                            "no_ad",
                            log_prefix=f"[W{worker_id}] ",
                        )
                elif proxy_manager is not None:
                    if res.get("success"):
                        proxy_manager.record_target_hit(proxy, target=target_key)
                    proxy_manager.release_proxy(proxy)
        except Exception as exc:
            _log(f"❌ Error sesi: {exc}", "red")
            if event_callback is not None:
                _emit(event_callback, "stepper_update", worker_id=worker_id, step_key="failed", stage="❌ GAGAL", status=str(exc)[:40], target_url=target_url)
                _emit(event_callback, "session_completed", worker_id=worker_id, status="FAIL", target_url=target_url, error=str(exc)[:80])
            if budget is not None:
                budget.record("FAIL")
            if proxy:
                stopping = bool(stop_event and stop_event.is_set()) or _is_shutdown_error(exc)
                if chain_provider is not None:
                    error_kind = "shutdown" if stopping else ("proxy" if _is_proxy_error(exc) else "other")
                    chain_provider.finish_session(
                        proxy, False, exc, error_kind, log_prefix=f"[W{worker_id}] "
                    )
                elif proxy_manager is not None:
                    try:
                        if not stopping:
                            proxy_manager.report_failure(proxy, error_message=str(exc))
                    finally:
                        proxy_manager.release_proxy(proxy)
            if use_direct:
                break

        if max_sessions <= 0 or done < max_sessions:
            _wait(random.uniform(1.0, 2.0))
