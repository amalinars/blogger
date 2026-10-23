#!/usr/bin/env python3
"""
automation.youtube.bot
YouTube Organic Search & Engagement Worker using Camoufox Anti-Detect Browser.

Spesifikasi & Alur Kerja:
1. Search Organik: Ketik 'horrornologi' pada kolom pencarian YouTube dengan jeda ketikan manusiawi.
2. Balanced Strategy (50/50):
   - Strategi A (50%): Klik langsung video dari channel 'horrornologi' di hasil pencarian.
   - Strategi B (50%): Klik kartu channel 'horrornologi', masuk ke tab 'Videos', dan klik video TERBARU (Index 0).
3. Dynamic Watch Duration (~50% Durasi Asli):
   - Otomatis membaca durasi asli video dari YouTube player API.
   - Menonton sekitar 45% - 65% dari total durasi secara dinamis (tidak statis/tetap).
4. Deteksi Iklan Real-time:
   - Mendeteksi saat iklan YouTube muncul (iklan_muncul).
   - Mendeteksi saat iklan selesai / tayang normal kembali (iklan_selesai).
   - Menunggu jeda reaksi manusiawi (2-4 detik) sebelum menekan tombol Skip Ad jika tombol muncul.
5. Resolusi Terendah (prioritas 144p):
   - Dipaksa via YouTube Player API (setPlaybackQualityRange) + verifikasi aktual, dengan fallback ke menu Gear player.
   - Dipertahankan otomatis setelah iklan selesai untuk menghemat kuota proksi residensial dan efisiensi CPU/RAM.
6. Core Modules:
   - Camoufox Anti-Detect Engine (Stealth Firefox).
   - core.proxy_manager.ProxyManager (Rotasi kursor persisten & thread-safe).
   - automation.browser_verifier.BrowserVerifier (Audit pre-flight anti-leak & proxy audit).
"""

import os
import sys
import json
import time
import random
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from playwright.sync_api import Page, ElementHandle

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.proxy_manager import ProxyManager
from automation.browser_verifier import BrowserVerifier
from automation.youtube.camoufox_engine import create_camoufox_session, get_random_viewport

CONFIG_FILE = CURRENT_DIR / "config.json"

COUNTRY_FLAGS = {
    "united states": "🇺🇸", "usa": "🇺🇸", "us": "🇺🇸",
    "united kingdom": "🇬🇧", "uk": "🇬🇧", "gb": "🇬🇧",
    "canada": "🇨🇦", "ca": "🇨🇦",
    "australia": "🇦🇺", "au": "🇦🇺",
    "france": "🇫🇷", "fr": "🇫🇷",
    "germany": "🇩🇪", "de": "🇩🇪",
    "japan": "🇯🇵", "jp": "🇯🇵",
    "singapore": "🇸🇬", "sg": "🇸🇬",
    "indonesia": "🇮🇩", "id": "🇮🇩",
    "netherlands": "🇳🇱", "nl": "🇳🇱",
}

def get_country_badge(country_name: str) -> str:
    clean = (country_name or "").strip().lower()
    for k, flag in COUNTRY_FLAGS.items():
        if k in clean:
            return f"{flag} {country_name}"
    return f"🌍 {country_name or 'Global'}"


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "search_keyword": "horrornologi",
        "target_channel": "horrornologi",
        "dynamic_watch_ratio": {"min_ratio": 0.30, "max_ratio": 0.60},
        "fallback_watch_seconds": {"min": 240, "max": 420},
        "max_watch_cap_seconds": 900,
        "flow_balance": {"direct_search_video_weight": 0.0, "channel_latest_video_weight": 1.0},
        "resolution": "144p",
        "humanize": True,
        "headless": True,
        "run_browser_verifier": True,
        "ad_skip_delay_seconds": {"min": 2.0, "max": 4.5},
        "concurrency": 2,
        "unlimited": True,
        "session_cooldown_seconds": {"min": 4.0, "max": 8.0}
    }


def format_time(seconds: float) -> str:
    s = max(0, int(seconds))
    m = s // 60
    sec = s % 60
    h = m // 60
    if h > 0:
        return f"{h:02d}:{m % 60:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def emit_log(
    message: str,
    tag: str = "[YT]",
    style: str = "white",
    event_callback=None,
    worker_id: int = 1,
):
    """Kirim log ke TUI jika ada callback, atau print jika dijalankan mandiri tanpa TUI."""
    if event_callback:
        event_callback("log_message", {
            "worker_id": worker_id,
            "message": f"{tag} {message}",
            "style": style
        })
    else:
        print(f"{tag} {message}")


def handle_consent_dialog(page: Page, tag: str = "[YT]"):
    """Menangani popup GDPR Consent / Lightbox overlay di YouTube."""
    try:
        page.evaluate("""
            () => {
                const lightbox = document.querySelector('ytd-consent-bump-v2-lightbox');
                if (lightbox) {
                    const btn = lightbox.querySelector("button[aria-label*='Reject all'], button[aria-label*='Accept all'], button[aria-label*='Tout refuser'], button[aria-label*='Tout accepter'], button[aria-label*='Alle ablehnen'], button[aria-label*='Tolak'], button[aria-label*='Setuju']")
                             || Array.from(lightbox.querySelectorAll('button')).find(b => /Reject all|Accept all|Tout refuser|Tout accepter|Alle ablehnen|I agree/i.test(b.innerText || ''));
                    if (btn) {
                        btn.click();
                    } else {
                        lightbox.remove();
                    }
                }
                const backdrops = document.querySelectorAll('tp-yt-iron-overlay-backdrop');
                backdrops.forEach(b => b.remove());
            }
        """)
    except Exception:
        pass


def safe_click(page: Page, element: Any, tag: str = "[YT]", timeout: int = 6000) -> bool:
    """Klik elemen secara aman dengan penanganan overlay consent."""
    if not element:
        return False
    handle_consent_dialog(page, tag=tag)
    try:
        element.scroll_into_view_if_needed(timeout=3000)
        time.sleep(random.uniform(0.3, 0.6))
        element.click(timeout=timeout)
        return True
    except Exception:
        handle_consent_dialog(page, tag=tag)
        try:
            element.click(force=True, timeout=3000)
            return True
        except Exception:
            return False


def type_naturally(page: Page, element: Any, text: str):
    """Mengetik karakter demi karakter dengan variasi delay menyerupai ketikan manusia asli."""
    for char in text:
        element.type(char, delay=random.randint(60, 150))
        if random.random() < 0.12:
            time.sleep(random.uniform(0.1, 0.25))


def execute_search_flow(
    page: Page,
    keyword: str,
    target_channel: str,
    config: Dict[str, Any],
    tag: str = "[YT]",
    event_callback=None,
    worker_id: int = 1,
) -> Tuple[bool, str, str, Optional[float]]:
    """
    Eksekusi alur pencarian organik YouTube.
    Prioritas utama: masuk ke channel target dan klik video TERBARU (Index 0).
    Mengembalikan: (success: bool, flow_type: str, video_title: str, initial_badge_duration: Optional[float])
    """
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Membuka Beranda YouTube..."})

    try:
        page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        emit_log(f"Notice navigasi YouTube: {e}", tag=tag, style="dim", event_callback=event_callback, worker_id=worker_id)

    time.sleep(random.uniform(2.0, 3.5))
    handle_consent_dialog(page, tag=tag)

    # 1. Cari kolom input search
    search_input = None
    try:
        search_input = page.wait_for_selector(
            "input#search, input[name='search_query'], input.ytd-searchbox",
            timeout=8000
        )
    except Exception:
        search_input = page.query_selector("input#search, input[name='search_query'], input.ytd-searchbox")

    if not search_input:
        btn_icon = page.query_selector("button#search-button-narrow, button[aria-label='Search YouTube']")
        if btn_icon:
            btn_icon.click()
            time.sleep(1.0)
            search_input = page.query_selector("input#search, input[name='search_query']")

    if not search_input:
        emit_log("Input search tidak ditemukan, navigasi via URL...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": f"Mencari: '{keyword}' (Direct URL)"})
        page.goto(f"https://www.youtube.com/results?search_query={keyword}", wait_until="domcontentloaded", timeout=30000)
    else:
        emit_log(f"Mengetik query pencarian: '{keyword}'...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": f"🔍 Mengetik: '{keyword}'..."})
        safe_click(page, search_input, tag=tag)
        time.sleep(random.uniform(0.4, 0.8))
        type_naturally(page, search_input, keyword)
        time.sleep(random.uniform(0.5, 1.0))
        page.keyboard.press("Enter")

    # Tunggu hasil pencarian muncul
    try:
        page.wait_for_selector("ytd-section-list-renderer, ytd-item-section-renderer, #contents", timeout=20000)
    except Exception:
        pass
    time.sleep(random.uniform(2.5, 4.0))
    handle_consent_dialog(page, tag=tag)

    # 2. Tentukan Strategi
    direct_weight = config.get("flow_balance", {}).get("direct_search_video_weight", 0.0)
    roll = random.random()
    choose_direct_search = roll < direct_weight

    chosen_flow = "Direct Search Video" if choose_direct_search else "Channel Latest Video (Index 0)"
    emit_log(f"Strategi Terpilih: {chosen_flow}", tag=tag, style="magenta", event_callback=event_callback, worker_id=worker_id)
    if event_callback:
        event_callback("strategy_selected", {"worker_id": worker_id, "flow_type": chosen_flow})

    # STRATEGI 1: DIRECT VIDEO DARI HASIL PENCARIAN (JIKA DIAKTIFKAN)
    if choose_direct_search:
        video_found, video_title = _pick_video_from_search_results(page, target_channel, tag=tag, event_callback=event_callback, worker_id=worker_id)
        if video_found:
            return True, "Direct Search Video", video_title, None

        emit_log(f"Video '{target_channel}' di search tidak ditemukan. Fallback ke Channel...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": "Fallback: Masuk Channel..."})

    # STRATEGI 2 (DEFAULT): MASUK CHANNEL DULU -> KLIK VIDEO TERBARU (INDEX 0)
    channel_opened = _open_channel_page(page, target_channel, tag=tag, event_callback=event_callback, worker_id=worker_id)
    if channel_opened:
        video_found, video_title, dur_badge = _pick_latest_video_index_0(page, tag=tag, event_callback=event_callback, worker_id=worker_id)
        if video_found:
            return True, "Channel Latest Video (Index 0)", video_title, dur_badge

    # Fallback darurat
    emit_log("Fallback darurat pencarian link video watch...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
    any_video = page.query_selector("a#video-title-link, a#video-title, a[href*='/watch?v=']")
    if any_video:
        title = any_video.get_attribute("title") or any_video.inner_text().strip() or "YouTube Video"
        safe_click(page, any_video, tag=tag)
        time.sleep(random.uniform(2.5, 4.0))
        return True, "Fallback Video", title, None

    return False, "Failed", "", None


def _pick_video_from_search_results(
    page: Page,
    target_channel: str,
    tag: str = "[YT]",
    event_callback=None,
    worker_id: int = 1,
) -> Tuple[bool, str]:
    """Mencari video renderer di hasil search yang berasal dari channel target_channel."""
    emit_log(f"Memindai video hasil pencarian untuk '{target_channel}'...", tag=tag, style="cyan", event_callback=event_callback, worker_id=worker_id)
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": f"Memindai Video '{target_channel}'..."})

    try:
        page.evaluate("window.scrollBy(0, 350);")
    except Exception:
        pass
    time.sleep(1.5)

    renderers = page.query_selector_all("ytd-video-renderer")
    matching_videos = []

    for rend in renderers[:20]:
        try:
            ch_elem = rend.query_selector("ytd-channel-name, div#channel-info, a.yt-simple-endpoint[href*='@']")
            ch_text = (ch_elem.inner_text().lower() if ch_elem else "")
            ch_href = (ch_elem.query_selector("a").get_attribute("href") if ch_elem and ch_elem.query_selector("a") else "")

            if target_channel.lower() in ch_text or f"/@{target_channel.lower()}" in (ch_href or "").lower():
                title_elem = rend.query_selector("a#video-title, a#video-title-link")
                if title_elem:
                    title = title_elem.get_attribute("title") or title_elem.inner_text().strip()
                    matching_videos.append((title_elem, title))
        except Exception:
            continue

    if matching_videos:
        chosen_elem, chosen_title = random.choice(matching_videos[:5])
        emit_log(f"🎬 Video Direct Search: '{chosen_title}'", tag=tag, style="green", event_callback=event_callback, worker_id=worker_id)
        if event_callback:
            event_callback("video_picked", {
                "worker_id": worker_id,
                "title": chosen_title,
                "flow_type": "Direct Search Video",
                "status": f"Direct: {chosen_title[:32]}..."
            })
        clicked = safe_click(page, chosen_elem, tag=tag)
        time.sleep(random.uniform(3.0, 5.0))
        return clicked, chosen_title

    return False, ""


def _open_channel_page(
    page: Page,
    target_channel: str,
    tag: str = "[YT]",
    event_callback=None,
    worker_id: int = 1,
) -> bool:
    """Mencari kartu channel pada hasil search dan masuk ke dalam channel (tab Videos)."""
    emit_log(f"Mencari link channel '{target_channel}'...", tag=tag, style="cyan", event_callback=event_callback, worker_id=worker_id)
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": f"Mencari Channel '{target_channel}'..."})

    channel_selectors = [
        f"ytd-channel-renderer a[href*='{target_channel.lower()}']",
        f"a#main-link[href*='{target_channel.lower()}']",
        f"ytd-channel-renderer a#avatar-section",
        f"ytd-channel-name:has-text('{target_channel}') a",
        f"a[href*='/@{target_channel.lower()}']",
    ]

    channel_elem = None
    for sel in channel_selectors:
        elem = page.query_selector(sel)
        if elem and elem.is_visible():
            channel_elem = elem
            break

    if channel_elem:
        emit_log(f"Mengklik kartu channel '{target_channel}'...", tag=tag, style="cyan", event_callback=event_callback, worker_id=worker_id)
        safe_click(page, channel_elem, tag=tag)
        time.sleep(random.uniform(2.5, 4.0))
    else:
        emit_log(f"Akses langsung URL /@{target_channel}/videos...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
        page.goto(f"https://www.youtube.com/@{target_channel}/videos", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(2.5, 4.0))

    try:
        videos_tab = page.query_selector(
            "yt-tab-shape[tab-title*='Video'], "
            "tp-yt-paper-tab:has-text('Videos'), "
            "tp-yt-paper-tab:has-text('Video'), "
            "a[href*='/videos']"
        )
        if videos_tab and videos_tab.is_visible():
            safe_click(page, videos_tab, tag=tag)
            time.sleep(random.uniform(2.0, 3.5))
    except Exception:
        pass

    return True


def parse_iso_duration(pt_str: str) -> float:
    """Mengubah format ISO 8601 durasi YouTube (contoh: 'PT14M54S' atau 'PT1H2M3S') ke detik float."""
    if not pt_str or not pt_str.startswith("PT"):
        return 0.0
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", pt_str)
    if not match:
        return 0.0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return float(h * 3600 + m * 60 + s)


def is_ad_active(page: Page) -> bool:
    """Mendeteksi apakah saat ini sedang ada tayangan iklan aktif di player."""
    try:
        return bool(page.evaluate("""() => {
            const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
            if (player && (player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting'))) {
                return true;
            }
            const adOverlay = document.querySelector('.ytp-ad-player-overlay, .ytp-ad-text');
            return !!adOverlay;
        }"""))
    except Exception:
        return False


def _pick_latest_video_index_0(
    page: Page,
    tag: str = "[YT]",
    event_callback=None,
    worker_id: int = 1,
) -> Tuple[bool, str, Optional[float]]:
    """
    Mengambil video paling terbaru / teratas (INDEX 0) di tab Videos channel.
    Mendukung komponen modern YouTube (ytLockupMetadataViewModelTitle / ytd-rich-item-renderer).
    Mengembalikan: (success, video_title, initial_badge_duration)
    """
    emit_log("Memilih video TERBARU (Index 0)...", tag=tag, style="cyan", event_callback=event_callback, worker_id=worker_id)
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Memilih Video Terbaru (Index 0)..."})

    time.sleep(random.uniform(1.5, 2.5))
    try:
        page.evaluate("window.scrollBy(0, 250);")
    except Exception:
        pass
    time.sleep(1.0)

    try:
        video_info = page.evaluate("""() => {
            const items = Array.from(document.querySelectorAll('ytd-rich-item-renderer, ytd-rich-grid-media, ytd-grid-video-renderer, ytd-video-renderer'));
            for (const item of items) {
                const link = item.querySelector('a.ytLockupMetadataViewModelTitle, a#video-title-link, a#video-title, a[href*="/watch?v="]');
                if (!link) continue;
                const href = link.getAttribute('href');
                if (!href || !href.includes('/watch?v=')) continue;
                
                let title = link.getAttribute('title') || link.innerText.trim();
                if (!title || title.length < 3) {
                    const titleEl = item.querySelector('h3, #video-title, .ytLockupMetadataViewModelTitle');
                    if (titleEl) title = titleEl.innerText.trim();
                }
                
                let dur = '';
                const timeSpan = item.querySelector('span.badge-shape-wiz__text, ytd-thumbnail-overlay-time-status-renderer span, .ytLockupViewModelContentImage');
                if (timeSpan) {
                    dur = timeSpan.innerText.trim() || timeSpan.getAttribute('title') || '';
                }
                return { href, title: title || 'Latest Video', dur };
            }
            return null;
        }""")
    except Exception:
        video_info = None

    if video_info and video_info.get("href"):
        chosen_title = video_info["title"]
        dur_sec = parse_time_str(video_info.get("dur", ""))
        dur_label = f" ({format_time(dur_sec)})" if dur_sec else ""
        emit_log(f"🎬 Video Terbaru [Index 0]: '{chosen_title}'{dur_label}", tag=tag, style="green", event_callback=event_callback, worker_id=worker_id)
        if event_callback:
            event_callback("video_picked", {
                "worker_id": worker_id,
                "title": chosen_title,
                "flow_type": "Channel Latest Video (Index 0)",
                "status": f"Latest[0]: {chosen_title[:30]}..."
            })

        link_elem = page.query_selector("a.ytLockupMetadataViewModelTitle, ytd-rich-item-renderer a[href*='/watch?v='], a#video-title-link, a#video-title")
        if link_elem:
            clicked = safe_click(page, link_elem, tag=tag)
            if clicked:
                time.sleep(random.uniform(3.0, 5.0))
                return True, chosen_title, dur_sec

        target_url = video_info["href"] if video_info["href"].startswith("http") else f"https://www.youtube.com{video_info['href']}"
        page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(random.uniform(3.0, 5.0))
        return True, chosen_title, dur_sec

    return False, "", None


def parse_time_str(time_str: str) -> Optional[float]:
    """Mengubah format 'MM:SS' atau 'HH:MM:SS' ke detik float."""
    try:
        parts = [int(p) for p in time_str.strip().split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        elif len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return None


def check_page_offline_or_error(page: Page) -> bool:
    """
    Mendeteksi apakah halaman YouTube menampilkan status offline / error koneksi / proxy putus.
    Mendukung deteksi multibahasa (Prancis, Inggris, Jerman, Indonesia, Spanyol, dll).
    """
    try:
        return bool(page.evaluate("""
            () => {
                // 1. Cek title
                const title = document.title || '';
                if (/error|offline|tidak ada koneksi/i.test(title)) return true;

                // 2. Cek teks body untuk pola offline YouTube
                const bodyText = document.body ? document.body.innerText : '';
                const offlinePatterns = [
                    "Connect to the internet",
                    "You're offline",
                    "No internet",
                    "Connectez-vous à Internet",
                    "Vous n'êtes pas connecté",
                    "Keine Internetverbindung",
                    "Tidak ada koneksi",
                    "Sin conexión a internet",
                    "Conéctate a Internet",
                    "net::ERR_"
                ];
                for (const pat of offlinePatterns) {
                    if (bodyText.includes(pat)) return true;
                }

                // 3. Cek tombol retry / reload offline YouTube
                const retryBtn = document.querySelector('button[aria-label*="Réessayer"], button[aria-label*="Try again"], button#retry-button, yt-button-renderer#retry-button');
                if (retryBtn) return true;

                // 4. Cek elemen astronot offline khas YouTube
                const offlineImg = document.querySelector('ytd-offline-promo-renderer, ytd-backstage-error-renderer');
                if (offlineImg) return true;

                // 5. Cek video error
                const v = document.querySelector('video');
                if (v && v.error && v.error.code !== 0) return true;

                return false;
            }
        """))
    except Exception:
        return False


def _lowest_quality_state(page: Page, apply: bool = False) -> Dict[str, Any]:
    """
    Membaca level kualitas yang tersedia dan (opsional) memaksa player ke level terendah
    lewat YouTube Player API. Mengembalikan status, target, dan kualitas aktual.
    """
    try:
        return page.evaluate("""(apply) => {
            const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
            if (!player) return { status: 'no_player' };

            const heights = { tiny: 144, small: 240, medium: 360, large: 480, hd720: 720, hd1080: 1080, hd1440: 1440, hd2160: 2160, highres: 4320 };
            const heightOf = (q) => {
                if (!q) return 99999;
                if (heights[q]) return heights[q];
                const m = String(q).match(/(\\d{3,4})/);
                return m ? parseInt(m[1], 10) : 99999;
            };

            let levels = [];
            try { levels = player.getAvailableQualityLevels ? (player.getAvailableQualityLevels() || []) : []; } catch (e) {}
            levels = levels.filter(q => q && q !== 'auto');

            let current = null;
            try { current = player.getPlaybackQuality ? player.getPlaybackQuality() : null; } catch (e) {}
            let label = null;
            try { label = player.getPlaybackQualityLabel ? player.getPlaybackQualityLabel() : null; } catch (e) {}

            const video = document.querySelector('#movie_player video, video');
            const height = video ? (video.videoHeight || 0) : 0;

            let target = null;
            for (const q of levels) {
                if (!target || heightOf(q) < heightOf(target)) target = q;
            }
            const targetHeight = target ? heightOf(target) : 0;
            const currentHeight = current ? heightOf(current) : 0;
            const isLowest = current === 'tiny'
                || (targetHeight > 0 && currentHeight > 0 && currentHeight <= targetHeight)
                || /144p/i.test(label || '')
                || (height > 0 && targetHeight > 0 && height <= targetHeight)
                || (height > 0 && !target && height <= 144);

            if (isLowest) {
                return { status: 'already', current, label, height, target, levels };
            }
            if (!apply) {
                return { status: target ? 'not_lowest' : 'no_levels', current, label, height, target, levels };
            }
            if (!target) {
                return { status: 'no_levels', current, label, height, target, levels };
            }

            let applied = false;
            try {
                if (typeof player.setPlaybackQualityRange === 'function') {
                    player.setPlaybackQualityRange(target, target);
                    applied = true;
                }
            } catch (e) {}
            try {
                if (typeof player.setPlaybackQuality === 'function') {
                    player.setPlaybackQuality(target);
                    applied = true;
                }
            } catch (e) {}

            return { status: applied ? 'applied' : 'no_api', current, label, height, target, levels };
        }""", apply)
    except Exception:
        return {"status": "error"}


def _wait_for_lowest_quality(page: Page, attempts: int = 4, delay: float = 0.7) -> Dict[str, Any]:
    """Menunggu player benar-benar berpindah ke resolusi terendah setelah perintah dikirim."""
    state = _lowest_quality_state(page)
    for _ in range(max(0, attempts - 1)):
        if state.get("status") == "already":
            break
        time.sleep(delay)
        state = _lowest_quality_state(page)
    return state


def _force_lowest_quality_ui(page: Page) -> bool:
    """Fallback: pilih resolusi 'p' terkecil lewat menu gear Player YouTube."""
    try:
        try:
            page.hover("#movie_player")
        except Exception:
            pass
        time.sleep(0.2)

        settings_btn = page.query_selector("button.ytp-settings-button")
        if not settings_btn:
            return False

        menu = page.query_selector(".ytp-popup.ytp-settings-menu")
        if not menu or not menu.is_visible():
            settings_btn.click()
            time.sleep(0.45)

        if is_ad_active(page):
            return False

        clicked_quality = page.evaluate("""() => {
            const menu = document.querySelector('.ytp-popup.ytp-settings-menu');
            if (!menu) return false;
            const items = Array.from(menu.querySelectorAll('.ytp-menuitem'));
            const q = items.find(el => {
                const t = el.innerText || '';
                return /quality|kualitas|kalite|qualit|calidad|qualidade|qualità|qualität|качество|品質|화질|الجودة|गुणवत्ता|คุณภาพ|chất lượng/i.test(t)
                    || /(\\d{3,4})\\s*p/i.test(t);
            });
            if (!q) return false;
            q.click();
            return true;
        }""")
        if not clicked_quality:
            return False
        time.sleep(0.45)

        def _choose_lowest() -> str:
            return page.evaluate("""() => {
                const menu = document.querySelector('.ytp-popup.ytp-settings-menu');
                if (!menu) return 'no_menu';
                const items = Array.from(menu.querySelectorAll('.ytp-menuitem'));
                let best = null;
                for (const el of items) {
                    const m = (el.innerText || '').match(/(\\d{3,4})\\s*p/i);
                    if (!m) continue;
                    const h = parseInt(m[1], 10);
                    if (!best || h < best.h) best = { el, h };
                }
                if (best) {
                    best.el.click();
                    return 'clicked';
                }
                const adv = items.find(el => /advanced|lanjutan|avancé|erweitert|avanzad|opções avançadas/i.test(el.innerText || ''));
                if (adv) {
                    adv.click();
                    return 'advanced';
                }
                return 'not_found';
            }""")

        result = _choose_lowest()
        if result == "advanced":
            time.sleep(0.45)
            result = _choose_lowest()
        return result == "clicked"
    except Exception:
        return False
    finally:
        try:
            btn = page.query_selector("button.ytp-settings-button")
            menu = page.query_selector(".ytp-popup.ytp-settings-menu")
            if btn and menu and menu.is_visible():
                btn.click()
        except Exception:
            pass


def set_playback_quality_144p(page: Page, tag: str = "[YT]", event_callback=None, worker_id: int = 1) -> bool:
    """
    Paksa player memutar resolusi paling kecil (prioritas 144p).
    Urutan strategi:
    1. YouTube Player API setPlaybackQualityRange + setPlaybackQuality (instan & persisten).
    2. Verifikasi kualitas aktual via getPlaybackQuality / label / videoHeight.
    3. Fallback ke menu gear Player UI dengan memilih resolusi 'p' terkecil.
    Tidak pernah menyentuh player saat iklan tayang agar tidak freeze/pause.
    """
    if is_ad_active(page):
        return False

    state = _lowest_quality_state(page, apply=True)
    if state.get("status") == "already":
        return True

    verify = _wait_for_lowest_quality(page)
    if verify.get("status") == "already":
        label = verify.get("label") or (f"{verify.get('height')}p" if verify.get("height") else "resolusi terendah")
        emit_log(f"Resolusi terendah aktif ({label}) via Player API.", tag=tag, style="bold green", event_callback=event_callback, worker_id=worker_id)
        return True

    if _force_lowest_quality_ui(page):
        verify = _wait_for_lowest_quality(page)
        if verify.get("status") == "already":
            label = verify.get("label") or (f"{verify.get('height')}p" if verify.get("height") else "resolusi terendah")
            emit_log(f"Resolusi terendah aktif ({label}) via Player UI.", tag=tag, style="bold green", event_callback=event_callback, worker_id=worker_id)
            return True

    return False


def detect_video_duration(page: Page, initial_badge_duration: Optional[float] = None, tag: str = "[YT]", max_wait_seconds: int = 15) -> Optional[float]:
    """
    Mendeteksi durasi asli video YouTube secara akurat & tangguh:
    1. Membaca meta tag itemprop="duration" (PT14M54S)
    2. Membaca YouTube ytInitialPlayerResponse.videoDetails.lengthSeconds
    3. Menggunakan durasi badge dari thumbnail jika valid
    4. Membaca HTML5 video element (video.duration) HANYA jika iklan TIDAK sedang tayang!
    """
    # 1. Coba baca dari meta itemprop="duration"
    try:
        meta_dur = page.evaluate("() => { const el = document.querySelector('meta[itemprop=\"duration\"]'); return el ? el.getAttribute('content') : null; }")
        if meta_dur:
            sec = parse_iso_duration(meta_dur)
            if sec > 30:
                return sec
    except Exception:
        pass

    # 2. Coba baca dari window.ytInitialPlayerResponse
    try:
        yt_len = page.evaluate("() => { try { return window.ytInitialPlayerResponse.videoDetails.lengthSeconds; } catch(e) { return null; } }")
        if yt_len and int(yt_len) > 30:
            return float(yt_len)
    except Exception:
        pass

    # 3. Gunakan durasi badge dari thumbnail jika ada
    if initial_badge_duration and initial_badge_duration > 30:
        return initial_badge_duration

    # 4. Tunggu video element HANYA jika bukan iklan
    start = time.time()
    while time.time() - start < max_wait_seconds:
        if check_page_offline_or_error(page):
            return None

        # JANGAN membaca durasi saat iklan tayang
        if is_ad_active(page):
            time.sleep(1.0)
            continue

        try:
            res = page.evaluate("""() => {
                const v = document.querySelector('video');
                if (v && v.duration && !isNaN(v.duration) && v.duration > 30) {
                    return { type: 'video_el', val: v.duration };
                }
                const durEl = document.querySelector('.ytp-time-duration');
                if (durEl && durEl.innerText && durEl.innerText.trim()) {
                    return { type: 'dom_text', val: durEl.innerText.trim() };
                }
                const p = document.getElementById('movie_player');
                if (p && typeof p.getDuration === 'function') {
                    const d = p.getDuration();
                    if (d && !isNaN(d) && d > 30) return { type: 'player_api', val: d };
                }
                return null;
            }""")
            if res:
                if res["type"] in ("video_el", "player_api"):
                    return float(res["val"])
                elif res["type"] == "dom_text":
                    parsed = parse_time_str(res["val"])
                    if parsed and parsed > 30:
                        return parsed
        except Exception:
            pass

        time.sleep(1.0)

    return initial_badge_duration


class AdTracker:
    """Pelacak siklus hidup iklan YouTube (iklan_muncul, jeda skip, iklan_selesai)."""

    def __init__(self, skip_delay_range: Tuple[float, float] = (2.0, 4.5)):
        self.skip_delay_min, self.skip_delay_max = skip_delay_range
        self.ad_is_showing = False
        self.ad_start_time: Optional[float] = None
        self.skip_detected_time: Optional[float] = None
        self.skip_clicked = False
        self.target_skip_delay = 3.0
        self.total_ads_detected = 0
        self.total_ads_skipped = 0
        self.total_ads_finished = 0

    def check(self, page: Page, tag: str = "[YT]", event_callback=None, worker_id: int = 1) -> bool:
        """
        Memeriksa state iklan pada frame saat ini.
        Mengembalikan True jika sedang ada iklan tayang.
        """
        try:
            is_showing = page.evaluate("""
                () => {
                    const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                    if (player && (player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting'))) {
                        return true;
                    }
                    const adOverlay = document.querySelector('.ytp-ad-player-overlay, .ytp-ad-text, .ytp-ad-preview-text');
                    return !!adOverlay;
                }
            """)
        except Exception:
            is_showing = False

        now = time.time()

        # EVENT: IKLAN MUNCUL (TRANSISI FALSE -> TRUE)
        if is_showing and not self.ad_is_showing:
            self.ad_is_showing = True
            self.ad_start_time = now
            self.skip_detected_time = None
            self.skip_clicked = False
            self.total_ads_detected += 1
            emit_log("🟡 IKLAN MUNCUL! Memantau penayangan...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
            if event_callback:
                event_callback("ad_event", {
                    "worker_id": worker_id,
                    "event": "iklan_muncul",
                    "status": "🟡 Tayang Iklan",
                    "ad_count": self.total_ads_detected
                })

        # SEDANG TAYANG IKLAN: CEK TOMBOL SKIP
        if is_showing and self.ad_is_showing:
            elapsed_ad = int(now - (self.ad_start_time or now))
            if not self.skip_clicked:
                # Cek apakah ada tombol skip yang BENAR-BENAR terlihat (visible) di layar
                skip_info = page.evaluate("""() => {
                    const selectors = [
                        'button.ytp-ad-skip-button',
                        'button.ytp-ad-skip-button-modern',
                        'button.ytp-skip-ad-button',
                        '.ytp-ad-skip-button-container button',
                        'div.ytp-ad-text.ytp-ad-skip-button-text'
                    ];
                    for (const s of selectors) {
                        const el = document.querySelector(s);
                        if (el && el.offsetParent !== null) {
                            const style = window.getComputedStyle(el);
                            if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                                return { found: true, selector: s };
                            }
                        }
                    }
                    return { found: false };
                }""")

                if isinstance(skip_info, dict) and skip_info.get("found"):
                    if self.skip_detected_time is None:
                        self.skip_detected_time = now
                        self.target_skip_delay = random.uniform(self.skip_delay_min, self.skip_delay_max)
                        emit_log(f"Tombol Skip Ad muncul! Menunggu jeda reaksi ({self.target_skip_delay:.1f}s)...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)

                    if now - self.skip_detected_time >= self.target_skip_delay:
                        try:
                            clicked = page.evaluate("""(sel) => {
                                const btn = document.querySelector(sel);
                                if (btn) { btn.click(); return true; }
                                return false;
                            }""", skip_info.get("selector"))
                            if clicked:
                                self.skip_clicked = True
                                self.total_ads_skipped += 1
                                emit_log("⏩ IKLAN DI-SKIP dengan jeda manusiawi.", tag=tag, style="magenta", event_callback=event_callback, worker_id=worker_id)
                                if event_callback:
                                    event_callback("ad_event", {
                                        "worker_id": worker_id,
                                        "event": "iklan_di_skip",
                                        "status": "⏩ Iklan Di-skip",
                                        "ad_count": self.total_ads_detected
                                    })
                        except Exception:
                            pass

            if event_callback and not self.skip_clicked:
                event_callback("ad_event", {
                    "worker_id": worker_id,
                    "event": "iklan_berjalan",
                    "status": f"🟡 Iklan ({format_time(elapsed_ad)})",
                    "ad_count": self.total_ads_detected
                })

        # EVENT: IKLAN SELESAI (TRANSISI TRUE -> FALSE)
        if not is_showing and self.ad_is_showing:
            ad_dur = int(now - (self.ad_start_time or now))
            self.ad_is_showing = False
            self.total_ads_finished += 1
            emit_log(f"🟢 IKLAN SELESAI ({ad_dur}s). Melanjutkan video normal.", tag=tag, style="green", event_callback=event_callback, worker_id=worker_id)
            if event_callback:
                event_callback("ad_event", {
                    "worker_id": worker_id,
                    "event": "iklan_selesai",
                    "status": "🟢 Konten Normal",
                    "ad_duration": ad_dur,
                    "ad_count": self.total_ads_detected
                })

        return is_showing


def watch_video_dynamically(
    page: Page,
    config: Dict[str, Any],
    initial_duration: Optional[float] = None,
    tag: str = "[YT]",
    event_callback=None,
    worker_id: int = 1,
    stop_event: Optional[threading.Event] = None,
) -> bool:
    """
    Menonton video dengan durasi dinamis 30% - 60% dari total durasi asli,
    sambil terus memantau tayangan iklan dan interaksi mouse/scroll natural.
    """
    handle_consent_dialog(page, tag=tag)

    # 1. Pastikan video berputar (Play) jika tidak sedang ad
    try:
        page.evaluate("""() => {
            const v = document.querySelector('video');
            if (v && v.paused) v.play().catch(() => {});
        }""")
    except Exception:
        pass

    # Ambil judul video yang akurat dari document.title
    time.sleep(random.uniform(1.5, 2.5))
    try:
        clean_title = page.evaluate("() => document.title.replace(' - YouTube', '').trim()")
        if clean_title and clean_title != "YouTube":
            if event_callback:
                event_callback("video_picked", {
                    "worker_id": worker_id,
                    "title": clean_title,
                    "status": f"Video: {clean_title[:32]}..."
                })
    except Exception:
        pass

    # Cek apakah layar offline sebelum memulai interaksi video
    if check_page_offline_or_error(page):
        emit_log("⚠️ Layar offline terdeteksi ('Connectez-vous à Internet / Offline'). Mengakhiri sesi.", tag=tag, style="bold red", event_callback=event_callback, worker_id=worker_id)
        return False

    ad_tracker = AdTracker(
        skip_delay_range=(
            config.get("ad_skip_delay_seconds", {}).get("min", 2.0),
            config.get("ad_skip_delay_seconds", {}).get("max", 4.5),
        )
    )

    # 2. Atur resolusi 144p via Player UI jika bukan iklan
    quality_confirmed = False
    if not is_ad_active(page):
        quality_confirmed = set_playback_quality_144p(page, tag=tag, event_callback=event_callback, worker_id=worker_id)

    # 3. Deteksi Durasi Asli Video
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Mendeteksi Durasi Asli Video..."})

    detected_dur = detect_video_duration(page, initial_badge_duration=initial_duration, tag=tag, max_wait_seconds=10)

    # Cek jika layar offline terdeteksi saat menunggu video
    if check_page_offline_or_error(page):
        emit_log("⚠️ Layar offline terdeteksi. Proksi putus, mengakhiri sesi.", tag=tag, style="bold red", event_callback=event_callback, worker_id=worker_id)
        return False

    # Jika durasi sama sekali tidak terdeteksi DAN video tidak jalan, abort
    if not detected_dur or detected_dur <= 10:
        has_video = page.evaluate("() => { const v = document.querySelector('video'); return !!v; }")
        if not has_video or check_page_offline_or_error(page):
            emit_log("❌ Video player tidak memuat (proksi tidak stabil). Mengakhiri sesi.", tag=tag, style="bold red", event_callback=event_callback, worker_id=worker_id)
            return False

    # Perhitungan Durasi Tonton Dinamis (30% - 60% Sesuai Instruksi User)
    ratio_cfg = config.get("dynamic_watch_ratio", {})
    min_r = ratio_cfg.get("min_ratio", 0.30)
    max_r = ratio_cfg.get("max_ratio", 0.60)
    max_cap = config.get("max_watch_cap_seconds", 900)

    duration_finalized = False
    if detected_dur and detected_dur > 20:
        chosen_ratio = random.uniform(min_r, max_r)
        target_watch = int(detected_dur * chosen_ratio)
        target_watch = max(60, min(target_watch, max_cap))
        pct_label = f"{int(chosen_ratio * 100)}%"
        duration_finalized = True
        emit_log(f"🎬 Total Durasi Asli: {format_time(detected_dur)} ({int(detected_dur)}s) | Target Nonton ({pct_label}): {format_time(target_watch)} ({target_watch}s)", tag=tag, style="bold green", event_callback=event_callback, worker_id=worker_id)
    else:
        # Jika metadata player belum termuat (buffering lambat), pasang target sementara
        fb_cfg = config.get("fallback_watch_seconds", {})
        target_watch = random.randint(max(180, fb_cfg.get("min", 240)), max(360, fb_cfg.get("max", 420)))
        pct_label = "~45% (Buffering)"
        emit_log(f"Menunggu metadata durasi (Target sementara: {format_time(target_watch)})...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)

    if event_callback:
        event_callback("playback_target_set", {
            "worker_id": worker_id,
            "target_seconds": target_watch,
            "detected_duration": detected_dur or target_watch,
            "ratio_label": pct_label,
            "status": f"Menonton: {format_time(target_watch)} ({pct_label} 144p)"
        })

    # 4. Loop Pemutaran Video
    start_time = time.time()
    end_time = start_time + target_watch
    last_scroll = time.time()
    last_quality_check = 0.0

    while time.time() < end_time and not page.is_closed():
        if stop_event and stop_event.is_set():
            emit_log("Sinyal berhenti diterima.", tag=tag, style="red", event_callback=event_callback, worker_id=worker_id)
            return True

        now = time.time()
        elapsed_sec = int(now - start_time)

        # Cek jika koneksi offline atau proxy putus
        if check_page_offline_or_error(page):
            emit_log("Koneksi proksi terputus (Layar offline).", tag=tag, style="red", event_callback=event_callback, worker_id=worker_id)
            return False

        # Deteksi & penanganan iklan real-time
        is_ad = ad_tracker.check(page, tag=tag, event_callback=event_callback, worker_id=worker_id)

        # Jika durasi belum final dan BUKAN iklan, coba deteksi lagi pada detik-detik awal playback
        if not duration_finalized and not is_ad:
            live_dur = detect_video_duration(page, initial_badge_duration=initial_duration, tag=tag, max_wait_seconds=1)
            if live_dur and live_dur > 20:
                detected_dur = live_dur
                chosen_ratio = random.uniform(min_r, max_r)
                target_watch = int(detected_dur * chosen_ratio)
                target_watch = max(60, min(target_watch, max_cap))
                end_time = start_time + target_watch
                duration_finalized = True
                pct_label = f"{int(chosen_ratio * 100)}%"
                emit_log(f"🎬 Metadata termuat! Durasi: {format_time(detected_dur)} | Target Diperbarui ({pct_label}): {format_time(target_watch)}", tag=tag, style="bold green", event_callback=event_callback, worker_id=worker_id)
                if event_callback:
                    event_callback("playback_target_set", {
                        "worker_id": worker_id,
                        "target_seconds": target_watch,
                        "detected_duration": detected_dur,
                        "ratio_label": pct_label,
                        "status": f"Menonton: {format_time(target_watch)} ({pct_label} 144p)"
                    })

        # Jaga kualitas tetap di resolusi terendah. ABR YouTube bisa naik lagi setelah iklan selesai.
        if is_ad:
            quality_confirmed = False
        elif not quality_confirmed or now - last_quality_check >= 10.0:
            last_quality_check = now
            quality_confirmed = set_playback_quality_144p(page, tag=tag, event_callback=event_callback, worker_id=worker_id)

        # Cek apakah video sudah tamat (ended) di player
        try:
            is_ended = page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    const p = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                    if (v && v.ended) return true;
                    if (p && typeof p.getPlayerState === 'function') {
                        return p.getPlayerState() === 0;
                    }
                    return false;
                }
            """)
            if is_ended:
                emit_log("Video telah tamat diputar (ended).", tag=tag, style="green", event_callback=event_callback, worker_id=worker_id)
                break
        except Exception:
            pass

        elapsed_sec = int(now - start_time)
        pct = min(100.0, max(0.0, (elapsed_sec / target_watch) * 100)) if target_watch else 0.0

        if event_callback:
            event_callback("playback_progress", {
                "worker_id": worker_id,
                "current_seconds": elapsed_sec,
                "target_seconds": target_watch,
                "percent": pct,
                "formatted_current": format_time(elapsed_sec),
                "formatted_target": format_time(target_watch)
            })

        # Perilaku manusiawi: scroll santai membaca komentar / mouse drift
        if now - last_scroll > random.uniform(20.0, 35.0):
            try:
                scroll_delta = random.choice([250, 400, -200, 300])
                page.evaluate(f"window.scrollBy(0, {scroll_delta});")
            except Exception:
                pass
            last_scroll = now

        time.sleep(1.0)

    emit_log(f"Selesai menonton target {format_time(target_watch)}!", tag=tag, style="green", event_callback=event_callback, worker_id=worker_id)
    return True


def run_worker_session(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    event_callback=None,
    stop_event: Optional[threading.Event] = None,
) -> bool:
    """
    Eksekusi 1 Sesi Menonton YouTube:
    1. Acquire proxy eksklusif via ProxyManager
    2. Jalankan audit pre-flight via BrowserVerifier
    3. Eksekusi alur organik (Search 'horrornologi' -> 50% Direct vs 50% Channel Index 0)
    4. Nonton ~50% dinamis dengan deteksi iklan real-time
    5. Release proxy bersih kembali ke pool
    """
    tag = f"[W{worker_id}]"
    caller_id = f"worker_{worker_id}"

    # 1. Alokasi Proxy (dengan verifikasi jaringan live)
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Memvalidasi & Mengambil Proksi..."})

    proxy_data = proxy_manager.acquire_proxy(caller_id=caller_id, exclusive=True, verify_alive=True)
    if not proxy_data:
        emit_log("Tidak ada proksi tersedia dalam pool. Antre 5s...", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": "Antre Proksi Tersedia..."})
        time.sleep(5.0)
        return False

    proxy_id = proxy_data.get("id")
    ip = proxy_data.get("ip_detected") or proxy_data.get("host")
    country = proxy_data.get("country", "Unknown")
    badge = get_country_badge(country)

    emit_log(f"Proksi Diambil: {proxy_id} ({ip} | {badge})", tag=tag, style="cyan", event_callback=event_callback, worker_id=worker_id)
    if event_callback:
        event_callback("proxy_assigned", {
            "worker_id": worker_id,
            "proxy_id": proxy_id,
            "ip": ip,
            "country": badge,
            "status": f"Proksi: {ip} ({badge})"
        })

    session_success = False
    proxy_error_msg = None

    try:
        # 2. Luncurkan Camoufox
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": "Meluncurkan Camoufox..."})

        headless = config.get("headless", True)
        humanize = config.get("humanize", True)

        with create_camoufox_session(
            proxy_data=proxy_data,
            headless=headless,
            humanize=humanize,
            allow_ads=True,
        ) as browser:
            page = browser.new_page(viewport=get_random_viewport())

            # 3. Pre-Flight Browser Verifier (Audit Anti-Leak & Webdriver)
            if config.get("run_browser_verifier", True):
                if event_callback:
                    event_callback("status_update", {"worker_id": worker_id, "status": "Audit Pre-Flight Verifier..."})
                try:
                    page.goto("about:blank")
                    verifier = BrowserVerifier(strict_mode=False)
                    report = verifier.verify(page, expected_ip=proxy_data.get("ip_detected"), check_ads=True)

                    actual = report.actual_state
                    webdriver_val = actual.get("webdriver", False)
                    webrtc_leak_val = actual.get("webrtc_leak", False)
                    webgl_str = f"{actual.get('webgl_vendor', '')} {actual.get('webgl_renderer', '')}".strip() or "Native Hardware GPU"
                    ads_allowed_val = actual.get("ads_allowed", True)
                    canvas_audio_ok = actual.get("canvas_ok", True) and actual.get("audio_ok", True)

                    # Kirim laporan audit terperinci ke TUI Dashboard
                    if event_callback:
                        event_callback("verifier_report", {
                            "worker_id": worker_id,
                            "score": report.score,
                            "is_safe": report.is_safe,
                            "webdriver_hidden": (webdriver_val is False),
                            "webrtc_safe": (webrtc_leak_val is False),
                            "webgl": webgl_str[:28],
                            "canvas_audio_ok": canvas_audio_ok,
                            "ads_allowed": ads_allowed_val,
                            "os": actual.get("detected_os", "linux"),
                            "status": "PASS: Anti-Bot Hidden • 0 Leak • GPU Clean" if report.is_safe else "FAIL"
                        })

                    bot_text = "🟢 FALSE (Hidden)" if not webdriver_val else "🔴 Terdeteksi Bot!"
                    rtc_text = "🟢 AMAN (0 Leak)" if not webrtc_leak_val else "🔴 Bocor!"
                    ads_text = "🟢 Allowed (No AdBlock)" if ads_allowed_val else "🔴 AdBlock"
                    emit_log(
                        f"🛡️ AUDIT ({report.score}/100): Bot={bot_text} | WebRTC={rtc_text} | GPU={webgl_str[:20]} | Ads={ads_text}",
                        tag=tag,
                        style="bold green" if report.is_safe else "bold red",
                        event_callback=event_callback,
                        worker_id=worker_id,
                    )

                    if not report.is_safe:
                        emit_log(f"Audit Issues: {report.issues}", tag=tag, style="yellow", event_callback=event_callback, worker_id=worker_id)
                except Exception as ver_err:
                    emit_log(f"Pre-flight notice: {ver_err}", tag=tag, style="dim", event_callback=event_callback, worker_id=worker_id)

            # 4. Alur YouTube Organik
            keyword = config.get("search_keyword", "horrornologi")
            target_channel = config.get("target_channel", "horrornologi")

            nav_ok, flow_type, video_title, initial_dur = execute_search_flow(
                page=page,
                keyword=keyword,
                target_channel=target_channel,
                config=config,
                tag=tag,
                event_callback=event_callback,
                worker_id=worker_id,
            )

            if not nav_ok:
                emit_log("Gagal menemukan/memilih video target.", tag=tag, style="red", event_callback=event_callback, worker_id=worker_id)
                return False

            # 5. Tonton Video secara Dinamis (30% - 60%) + Deteksi Iklan
            session_success = watch_video_dynamically(
                page=page,
                config=config,
                initial_duration=initial_dur,
                tag=tag,
                event_callback=event_callback,
                worker_id=worker_id,
                stop_event=stop_event,
            )

            if session_success:
                if event_callback:
                    event_callback("session_completed", {
                        "worker_id": worker_id,
                        "title": video_title,
                        "flow_type": flow_type,
                        "status": "Sesi Berhasil Selesai!"
                    })
            else:
                proxy_error_msg = "Sesi menonton terputus / layar offline"

    except Exception as e:
        err_text = str(e)
        emit_log(f"Kesalahan dalam sesi: {err_text[:60]}", tag=tag, style="red", event_callback=event_callback, worker_id=worker_id)
        if any(k in err_text.lower() for k in ["proxy", "tunnel", "timeout", "connect", "refused", "reset"]):
            proxy_error_msg = err_text
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": f"Error: {err_text[:30]}"})
    finally:
        # 6. Lepas Proksi Bersih
        if proxy_id:
            if proxy_error_msg:
                proxy_manager.report_failure(proxy_id, error_message=proxy_error_msg, is_proxy_error=True)
            proxy_manager.release_proxy(proxy_id, caller_id=caller_id)
            emit_log(f"Proksi {proxy_id} berhasil dilepaskan.", tag=tag, style="dim", event_callback=event_callback, worker_id=worker_id)

    return session_success


def worker_thread_loop(
    worker_id: int,
    config: Dict[str, Any],
    proxy_manager: ProxyManager,
    event_callback=None,
    stop_event: Optional[threading.Event] = None,
):
    """Loop persisten worker untuk rotasi terus menerus."""
    tag = f"[W{worker_id}]"
    emit_log(f"Worker {worker_id} dimulai.", tag=tag, style="green", event_callback=event_callback, worker_id=worker_id)

    while not (stop_event and stop_event.is_set()):
        try:
            run_worker_session(
                worker_id=worker_id,
                config=config,
                proxy_manager=proxy_manager,
                event_callback=event_callback,
                stop_event=stop_event,
            )
        except Exception as e:
            emit_log(f"Worker error: {e}", tag=tag, style="red", event_callback=event_callback, worker_id=worker_id)

        if stop_event and stop_event.is_set():
            break

        cooldown_cfg = config.get("session_cooldown_seconds", {})
        cd = random.uniform(cooldown_cfg.get("min", 4.0), cooldown_cfg.get("max", 8.0))
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": f"Cooldown ({cd:.1f}s)..."})
        time.sleep(cd)

    emit_log(f"Worker {worker_id} dihentikan.", tag=tag, style="dim", event_callback=event_callback, worker_id=worker_id)
