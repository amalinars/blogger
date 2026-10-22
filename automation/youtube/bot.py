#!/usr/bin/env python3
"""
automation.youtube.bot - YouTube Organic Search & Channel Engagement Engine
Fitur Utama:
1. Anti-Fraud & Valid View: Masuk via Pencarian Organik YouTube (search "horrornologi") -> Masuk ke Channel -> Pilih Video Random.
2. Resolusi 144p: Otomatis diset ke kualitas terendah (144p) via Player API & Menu Pengaturan untuk hemat kuota proksi & ringan CPU/RAM.
3. 1 Video 1 Proxy: Setiap video ditonton menggunakan 1 proksi unik, lalu browser ditutup bersih.
4. Unlimited Rotation: Berjalan bergilir tanpa henti (rotasi terus-menerus) dari proxies.json.
5. Biometrik & Stealth: Menggunakan CDP stealth, argumen bebas deteksi otomasi, dan pergerakan mouse/scroll alami.
"""

import sys
import json
import time
import random
import argparse
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from playwright.sync_api import sync_playwright, Page, BrowserContext

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

try:
    from automation.core.browser import build_browser_args, format_proxy_dict, launch_browser, create_stealth_context
    from automation.core.proxy_manager import ProxyManager, load_proxies
    from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause
except ImportError:
    sys.path.insert(0, str(PROJECT_ROOT))
    from automation.core.browser import build_browser_args, format_proxy_dict, launch_browser, create_stealth_context
    from automation.core.proxy_manager import ProxyManager, load_proxies
    from automation.core.human import smooth_scroll, natural_mouse_move, physical_click, random_pause


def load_config() -> dict:
    cfg_file = BASE_DIR / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "search_keyword": "horrornologi",
        "target_channel": "horrornologi",
        "watch_duration": {"min_seconds": 60, "max_seconds": 180},
        "resolution": "144p",
        "proxy_source": "automation/proxies.json",
        "headless": False,
        "unlimited": True
    }


def handle_consent_dialog(page: Page, tag: str = "[YT]"):
    """
    Menangani popup 'Before you continue to YouTube' (GDPR Consent Bump v2) & backdrop:
    1. Klik tombol 'Reject all' atau 'Accept all' jika muncul
    2. Hapus elemen lightbox dan backdrop overlay dari DOM jika menghalangi pointer events
    """
    try:
        res = page.evaluate("""
            () => {
                let action = null;
                const lightbox = document.querySelector('ytd-consent-bump-v2-lightbox');
                if (lightbox) {
                    const btn = lightbox.querySelector("button[aria-label*='Reject all'], button[aria-label*='Accept all'], button[aria-label*='Tout refuser'], button[aria-label*='Tout accepter'], button[aria-label*='Alle ablehnen'], button[aria-label*='Tolak'], button[aria-label*='Setuju']")
                             || Array.from(lightbox.querySelectorAll('button')).find(b => /Reject all|Accept all|Tout refuser|Tout accepter|Alle ablehnen|I agree/i.test(b.innerText || ''));
                    if (btn) {
                        btn.click();
                        action = 'button-clicked';
                    } else {
                        lightbox.remove();
                        action = 'lightbox-removed';
                    }
                }
                const backdrops = document.querySelectorAll('tp-yt-iron-overlay-backdrop');
                if (backdrops.length > 0) {
                    backdrops.forEach(b => b.remove());
                    action = action || 'backdrop-removed';
                }
                return action;
            }
        """)
        if res:
            print(f"{tag} 🛡️ Berhasil mengatasi dialog consent YouTube ({res}).")
            time.sleep(1.0)
    except Exception:
        pass


def safe_click(page: Page, element, tag: str = "[YT]", timeout: int = 7000) -> bool:
    """
    Melakukan klik aman pada elemen:
    - Menghapus popup consent & backdrop jika menghalangi
    - Coba klik biasa, jika pointer events terhalang otomatis fallback ke force=True
    """
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
            element.click(force=True, timeout=4000)
            return True
        except Exception:
            return False


def search_and_open_channel(page: Page, search_query: str, target_channel: str, tag: str = "[YT]") -> bool:
    """
    Melakukan pencarian organik di YouTube:
    1. Buka https://www.youtube.com
    2. Ketik 'search_query' secara alami (karakter demi karakter dengan jeda acak)
    3. Tekan Enter / klik search
    4. Cari kartu channel di hasil pencarian dan klik untuk masuk ke channel
    5. Klik tab 'Videos' di dalam channel
    """
    print(f"{tag} 🌐 Membuka beranda YouTube untuk pencarian organik...")
    try:
        page.goto("https://www.youtube.com", wait_until="commit", timeout=40000)
    except Exception as nav_e:
        if "ERR_ABORTED" not in str(nav_e):
            print(f"{tag} [-] Notice navigasi YouTube: {nav_e}")
    time.sleep(random.uniform(2.5, 4.0))
    handle_consent_dialog(page, tag=tag)

    # 1. Cari search input box
    search_input = None
    try:
        search_input = page.wait_for_selector(
            "input#search, input[name='search_query'], input.ytd-searchbox",
            timeout=10000
        )
    except Exception:
        search_input = page.query_selector("input#search, input[name='search_query'], input.ytd-searchbox")

    if not search_input:
        # Coba tombol search icon mobile jika tampilan kecil
        btn_icon = page.query_selector("button#search-button-narrow, button[aria-label='Search YouTube']")
        if btn_icon:
            btn_icon.click()
            time.sleep(1.0)
            search_input = page.query_selector("input#search, input[name='search_query']")

    if not search_input:
        print(f"{tag} [-] Input pencarian YouTube tidak ditemukan. Navigasi langsung ke search URL...")
        try:
            page.goto(f"https://www.youtube.com/results?search_query={search_query}", wait_until="commit", timeout=35000)
        except Exception:
            pass
    else:
        print(f"{tag} 🔍 Mengetik query pencarian: '{search_query}' secara alami...")
        safe_click(page, search_input, tag=tag)
        time.sleep(random.uniform(0.3, 0.7))

        # Ketik satu per satu karakter agar terdeteksi seperti ketikan manusia asli
        for char in search_query:
            search_input.type(char, delay=random.randint(60, 180))
            if random.random() < 0.15:
                time.sleep(random.uniform(0.1, 0.25))

        time.sleep(random.uniform(0.5, 1.2))
        page.keyboard.press("Enter")

    print(f"{tag} [*] Menunggu hasil pencarian termuat...")
    try:
        page.wait_for_selector("ytd-section-list-renderer, ytd-item-section-renderer, #contents", timeout=20000)
    except Exception:
        pass
    time.sleep(random.uniform(2.0, 3.5))

    # 2. Temukan channel 'target_channel' di hasil pencarian
    print(f"{tag} 🎯 Mencari channel '{target_channel}' di hasil pencarian...")
    channel_link = None

    # Coba cari elemen channel renderer resmi
    channel_selectors = [
        f"ytd-channel-renderer a[href*='{target_channel.lower()}']",
        f"a#main-link[href*='{target_channel.lower()}']",
        f"ytd-channel-renderer a#avatar-section",
        f"ytd-channel-name:has-text('{target_channel}') a",
        f"a[href*='/@{target_channel.lower()}']",
        f"a:has-text('{target_channel}')"
    ]

    for sel in channel_selectors:
        elem = page.query_selector(sel)
        if elem and elem.is_visible():
            channel_link = elem
            print(f"{tag} [✓] Menemukan channel card via selector: {sel}")
            break

    if channel_link:
        clicked = safe_click(page, channel_link, tag=tag, timeout=6000)
        if clicked:
            time.sleep(random.uniform(3.0, 5.0))
        else:
            print(f"{tag} [-] Klik channel gagal, navigasi langsung via URL...")
            page.goto(f"https://www.youtube.com/@{target_channel}/videos", wait_until="domcontentloaded", timeout=35000)
    else:
        print(f"{tag} [!] Kartu channel tidak ditemukan langsung di atas. Mengakses langsung ke channel /videos...")
        page.goto(f"https://www.youtube.com/@{target_channel}/videos", wait_until="domcontentloaded", timeout=35000)

    # 3. Pastikan berada di tab "Videos"
    try:
        if "/videos" not in page.url:
            print(f"{tag} [*] Beralih ke tab 'Videos' channel...")
            videos_tab = page.query_selector(
                "tp-yt-paper-tab:has-text('Videos'), "
                "tp-yt-paper-tab:has-text('Video'), "
                "a[href*='/videos']"
            )
            if videos_tab and videos_tab.is_visible():
                safe_click(page, videos_tab, tag=tag)
                time.sleep(random.uniform(2.0, 3.5))
            else:
                page.goto(f"https://www.youtube.com/@{target_channel}/videos", wait_until="domcontentloaded", timeout=35000)
    except Exception:
        pass

    return True


def pick_and_play_random_video(page: Page, tag: str = "[YT]", event_callback=None, worker_id: int = 1) -> bool:
    """Memilih salah satu video di channel secara acak dan memutarnya."""
    print(f"{tag} 🎲 Memindai daftar video di channel...")
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Memindai Daftar Video..."})
    time.sleep(random.uniform(2.0, 3.5))

    # Sedikit scroll agar video ter-render lengkap
    smooth_scroll(page, distance=random.randint(250, 450), steps=8)
    time.sleep(random.uniform(1.0, 2.0))

    # Ambil elemen video
    video_elements = page.query_selector_all(
        "ytd-rich-item-renderer a#video-title-link, "
        "ytd-grid-video-renderer a#video-title, "
        "a#video-title-link, "
        "a#video-title"
    )

    valid_videos = []
    for v in video_elements:
        href = v.get_attribute("href") or ""
        title = v.get_attribute("title") or v.inner_text().strip()
        if "/watch?v=" in href and title:
            valid_videos.append((v, title, href))

    if not valid_videos:
        try:
            if page.evaluate("() => /Connect to the internet|You're offline/i.test(document.body ? document.body.innerText : '')"):
                print(f"{tag} ⚠️ Terdeteksi layar 'You're offline' (Kuota proksi terputus saat memindai video).")
                return False
        except Exception:
            pass
        print(f"{tag} [-] Tidak ditemukan video di tab Videos. Mencoba fallback pencarian link video watch...")
        any_watch = page.query_selector("a[href*='/watch?v=']")
        if any_watch:
            safe_click(page, any_watch, tag=tag)
            time.sleep(random.uniform(3.0, 5.0))
            return True
        return False

    # Pilih 1 video secara acak dari 15 video teratas
    pool = valid_videos[:15]
    chosen_elem, chosen_title, chosen_href = random.choice(pool)
    print(f"{tag} 🎬 [VIDEO TERPILIH] '{chosen_title}' ({chosen_href})")

    if event_callback:
        full_url = f"https://www.youtube.com{chosen_href}" if chosen_href.startswith("/") else chosen_href
        event_callback("video_picked", {
            "worker_id": worker_id,
            "title": chosen_title,
            "url": full_url,
            "status": "Video Dipilih: " + chosen_title[:35] + "..."
        })

    clicked = safe_click(page, chosen_elem, tag=tag, timeout=6000)
    if not clicked:
        clean_url = f"https://www.youtube.com{chosen_href}" if chosen_href.startswith("/") else chosen_href
        page.goto(clean_url, wait_until="domcontentloaded", timeout=35000)

    time.sleep(random.uniform(3.0, 5.0))
    return True



def set_playback_quality_144p(page: Page, tag: str = "[YT]"):
    """
    Mengatur resolusi video ke 144p:
    1. Menggunakan YouTube HTML5 Player JS API ('tiny' = 144p)
    2. Fallback via UI Gear Settings -> Quality -> 144p
    """
    print(f"{tag} ⚙️ Mengatur resolusi pemutaran video ke 144p...")

    # Cara 1: Injeksi langsung ke JavaScript YouTube Player API
    try:
        api_success = page.evaluate("""
            () => {
                const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                if (player) {
                    if (typeof player.setPlaybackQualityRange === 'function') {
                        player.setPlaybackQualityRange('tiny', 'tiny');
                    }
                    if (typeof player.setPlaybackQuality === 'function') {
                        player.setPlaybackQuality('tiny');
                    }
                    return true;
                }
                return false;
            }
        """)
        if api_success:
            print(f"{tag} [✓] Player API: Berhasil meminta resolusi 'tiny' (144p).")
    except Exception as e:
        print(f"{tag} [-] Player API notice: {e}")

    # Cara 2: Menu Gear YouTube Player (UI fallback)
    try:
        settings_btn = page.query_selector("button.ytp-settings-button")
        if settings_btn and settings_btn.is_visible():
            settings_btn.click()
            time.sleep(random.uniform(0.6, 1.0))

            # Cari menu Kualitas / Quality
            quality_item = page.query_selector(
                ".ytp-menuitem:has-text('Quality'), "
                ".ytp-menuitem:has-text('Kualitas')"
            )
            if quality_item:
                quality_item.click()
                time.sleep(random.uniform(0.5, 0.9))

                # Klik opsi 144p
                p144 = page.query_selector(".ytp-menuitem:has-text('144p')")
                if p144:
                    p144.click()
                    print(f"{tag} [✓] UI Settings: Resolusi 144p berhasil dipilih secara fisik.")
                else:
                    # Tutup menu gear jika opsi 144p tidak ditemukan
                    settings_btn.click()
            else:
                settings_btn.click()
    except Exception:
        pass


def format_time(seconds: float) -> str:
    """Mengubah detik ke format MM:SS atau HH:MM:SS."""
    s = max(0, int(seconds))
    m = s // 60
    sec = s % 60
    h = m // 60
    if h > 0:
        return f"{h:02d}:{m % 60:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def check_and_skip_ad(page: Page, tag: str = "[YT]", event_callback=None, worker_id: int = 1):
    """Mendeteksi dan otomatis menekan tombol Skip Ad jika iklan YouTube muncul."""
    try:
        is_ad = page.evaluate("""
            () => {
                const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                if (player && (player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting'))) {
                    return true;
                }
                const adOverlay = document.querySelector('.ytp-ad-player-overlay, .ytp-ad-text, .ytp-ad-preview-text');
                return !!adOverlay;
            }
        """)

        if is_ad:
            skip_selectors = [
                "button.ytp-ad-skip-button",
                "button.ytp-ad-skip-button-modern",
                "button.ytp-skip-ad-button",
                ".ytp-ad-skip-button-container button",
                "div.ytp-ad-text.ytp-ad-skip-button-text"
            ]
            for sel in skip_selectors:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    print(f"{tag} ⏩ Terdeteksi iklan YouTube. Menekan tombol Skip Ad...")
                    btn.click()
                    if event_callback:
                        event_callback("ad_event", {"worker_id": worker_id, "status": "⏩ Iklan Di-skip", "action": "skipped"})
                    time.sleep(1.0)
                    return True
            if event_callback:
                event_callback("ad_event", {"worker_id": worker_id, "status": "🟡 Sedang Tayang Iklan", "action": "playing"})
            return True
        else:
            if event_callback:
                event_callback("ad_event", {"worker_id": worker_id, "status": "🟢 Konten Normal (Tanpa Iklan)", "action": "clean"})
            return False
    except Exception:
        return False


def get_video_duration(page: Page, tag: str = "[YT]") -> Optional[float]:
    """
    Mendeteksi durasi asli video YouTube (dalam detik)
    menggunakan YouTube Player API (movie_player.getDuration()) dan HTML5 video element.
    """
    for _ in range(8):
        check_and_skip_ad(page, tag=tag)
        try:
            dur = page.evaluate("""
                () => {
                    const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                    if (player && typeof player.getDuration === 'function') {
                        const d = player.getDuration();
                        if (d && !isNaN(d) && d > 0) return d;
                    }
                    const v = document.querySelector('video');
                    if (v && v.duration && !isNaN(v.duration) && v.duration > 0) {
                        return v.duration;
                    }
                    return null;
                }
            """)
            if dur and float(dur) > 0:
                return float(dur)
        except Exception:
            pass
        time.sleep(1.2)
    return None


def watch_video_organically(page: Page, config: dict, tag: str = "[YT]", event_callback=None, worker_id: int = 1):
    """
    Simulasi menonton video yang sah & anti-fraud:
    - Durasi tonton menyesuaikan durasi asli video secara dinamis (85% s/d 98% atau full jika video pendek).
    - Memastikan video aktif berputar (unpause jika terjeda).
    - Otomatis skip iklan (pre-roll / mid-roll) jika muncul tombol skip.
    - Scroll santai ke komentar / deskripsi dan gerakan mouse alami.
    - Berhenti otomatis saat video selesai diputar (ended).
    """
    handle_consent_dialog(page, tag=tag)

    # 1. Pastikan video sedang play
    try:
        play_btn = page.query_selector("button.ytp-play-button")
        if play_btn:
            aria = play_btn.get_attribute("aria-label") or ""
            if "Play" in aria or "Putar" in aria:
                print(f"{tag} [*] Video belum jalan, mengklik tombol play...")
                play_btn.click()
    except Exception:
        pass

    # 2. Atur kualitas 144p
    set_playback_quality_144p(page, tag=tag)

    # 3. Deteksi durasi asli video
    print(f"{tag} ⏳ Mendeteksi durasi asli video dari YouTube player...")
    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Mendeteksi Durasi Video..."})
    detected_dur = get_video_duration(page, tag=tag)

    if detected_dur and detected_dur > 10:
        # Menyesuaikan dengan durasi video: tonton 85% - 98% durasi (atau full jika durasi < 120s)
        if detected_dur < 120:
            target_watch = int(detected_dur)
            ratio_label = "100% (Full)"
        else:
            ratio = random.uniform(0.85, 0.98)
            target_watch = int(detected_dur * ratio)
            ratio_label = f"{int(ratio * 100)}% (Near-Full Retention)"

        print(f"{tag} 🎯 [DURASI ASLI] Total Panjang Video : {format_time(detected_dur)} ({int(detected_dur)}s)")
        print(f"{tag} 🎬 [TARGET NONTON] Disesuaikan ke : {format_time(target_watch)} ({target_watch}s | {ratio_label})")
    else:
        # Fallback jika durasi player tidak terbaca
        w_min = config.get("watch_duration", {}).get("min_seconds", 90)
        w_max = config.get("watch_duration", {}).get("max_seconds", 240)
        target_watch = random.randint(w_min, w_max)
        detected_dur = target_watch
        print(f"{tag} [!] Durasi video tidak terbaca, menggunakan durasi fallback: {format_time(target_watch)} ({target_watch}s)")

    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": f"Menonton: {format_time(target_watch)} (144p)"})

    # 4. Loop penayangan video
    start_time = time.time()
    end_time = start_time + target_watch
    last_scroll = time.time()
    last_log = time.time()

    while time.time() < end_time and not page.is_closed():
        now = time.time()

        # Otomatis lewati iklan jika tombol skip muncul saat menonton
        check_and_skip_ad(page, tag=tag, event_callback=event_callback, worker_id=worker_id)

        # Cek apakah koneksi proksi terputus / kuota habis (muncul layar 'Connect to the internet')
        try:
            is_offline = page.evaluate("""
                () => {
                    const txt = document.body ? document.body.innerText : '';
                    if (/Connect to the internet|You're offline|No internet/i.test(txt)) return true;
                    const v = document.querySelector('video');
                    if (v && v.error) return true;
                    return false;
                }
            """)
            if is_offline:
                print(f"{tag} ⚠️ Terdeteksi layar 'You're offline' (Kuota proksi habis / koneksi terputus). Mengakhiri sesi ini...")
                return False
        except Exception:
            pass

        # Cek apakah video sudah tamat / ended secara wajar di player
        try:
            is_ended = page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    const p = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                    if (v && v.ended) {
                        if (v.duration && v.currentTime && v.currentTime >= v.duration - 12) return true;
                        if (v.currentTime && v.currentTime > 30) return true;
                    }
                    if (p && typeof p.getPlayerState === 'function') {
                        return p.getPlayerState() === 0; // 0 = YT.PlayerState.ENDED
                    }
                    return false;
                }
            """)
            if is_ended:
                print(f"{tag} 🏁 Video telah selesai diputar sampai akhir (ended). Mengakhiri sesi menonton.")
                break
        except Exception:
            pass

        # Ambil posisi playback terkini
        cur_pos = None
        try:
            cur_pos = page.evaluate("""
                () => {
                    const p = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
                    if (p && typeof p.getCurrentTime === 'function') return p.getCurrentTime();
                    const v = document.querySelector('video');
                    return v ? v.currentTime : null;
                }
            """)
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

        # Log countdown setiap 15 detik
        if now - last_log >= 15.0:
            remaining = max(0, int(end_time - now))

            pos_str = f"Posisi: {format_time(cur_pos)} / " if cur_pos else ""
            tot_str = format_time(detected_dur) if detected_dur else format_time(target_watch)
            print(f"{tag} ⏱️ Sedang menonton... {pos_str}{tot_str} (Sisa tonton: {format_time(remaining)}) [144p]")
            last_log = now

        # Scroll acak setiap 18-32 detik (mensimulasikan membaca komentar/rekomendasi)
        if now - last_scroll > random.uniform(18.0, 32.0):
            direction = random.choice([1, 1, -1])  # Lebih sering ke bawah
            scroll_amt = random.randint(180, 380) * direction
            smooth_scroll(page, scroll_amt, steps=random.randint(6, 12))
            last_scroll = now

            # Gerakkan mouse santai
            rx = random.randint(250, 850)
            ry = random.randint(250, 650)
            natural_mouse_move(page, rx, ry, steps=random.randint(8, 14))

        time.sleep(1.0)

    total_watched = int(time.time() - start_time)
    print(f"{tag} [✓] Selesai menonton video ({format_time(total_watched)}). View tercatat dengan retensi tinggi secara organik.")


def test_proxy_youtube(proxy_info: Optional[Dict[str, Any]], timeout: float = 6.0) -> Tuple[bool, str, int]:
    """
    Menguji koneksi proksi langsung ke YouTube sebelum browser dibuka.
    Hanya proksi yang benar-benar responsif (HTTP 200/204) yang dinyatakan 'mantap'.
    """
    if not proxy_info:
        return True, "Direct Connection (Tanpa Proksi)", 0

    host = proxy_info.get("host")
    port = proxy_info.get("port")
    if not host or not port:
        return False, "Host/Port proksi tidak valid", 0

    user = proxy_info.get("username", "")
    pwd = proxy_info.get("password", "")
    if user and pwd:
        px_url = f"http://{user}:{pwd}@{host}:{port}"
    else:
        px_url = f"http://{host}:{port}"

    proxies_dict = {"http": px_url, "https": px_url}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }

    start_t = time.time()
    try:
        # Menguji koneksi riil ke halaman YouTube
        resp = requests.get(
            "https://www.youtube.com",
            proxies=proxies_dict,
            timeout=timeout,
            headers=headers,
            allow_redirects=True,
        )
        latency_ms = int((time.time() - start_t) * 1000)
        if resp.status_code in [200, 204, 301, 302]:
            return True, f"HTTP {resp.status_code} ({latency_ms}ms) Mantap! 🔥", latency_ms
        return False, f"Status HTTP {resp.status_code} ({latency_ms}ms)", latency_ms
    except requests.exceptions.ProxyError as pe:
        pe_str = str(pe)
        if "402" in pe_str:
            return False, "402 Payment Required (Akun/kuota proksi habis)", 0
        if "407" in pe_str:
            return False, "407 Proxy Unauthorized (Password proksi salah)", 0
        return False, f"Tunneling Proksi Gagal: {pe_str[:40]}", 0
    except requests.exceptions.ConnectTimeout:
        return False, f"Koneksi Timeout (> {timeout}s)", 0
    except requests.exceptions.ReadTimeout:
        return False, f"Respon Timeout (> {timeout}s)", 0
    except Exception as e:
        err_msg = str(e).splitlines()[0] if str(e) else "Error koneksi"
        return False, f"Koneksi Gagal: {err_msg[:45]}", 0


class UniqueProxyPool:
    """
    Pool proksi thread-safe dengan aturan ketat:
    - 5 worker berjalan paralel secara bersamaan.
    - Setiap worker dijamin memakai proksi yang berbeda (distinct proxy).
    - Proksi yang sudah dipakai TIDAK AKAN PERNAH dipakai lagi (Single-Use / No Reuse).
    - Proksi yang mati/lelet (gagal uji HTTP 200) otomatis dibuang dari pool.
    """
    def __init__(self, proxies: List[Dict[str, Any]]):
        self._lock = threading.Lock()
        self._pool = list(proxies)
        self._total_initial = len(proxies)
        self._used_count = 0
        self._failed_count = 0

    def get_tested_working_proxy(self, worker_id: int, event_callback=None) -> Optional[Dict[str, Any]]:
        tag = f"[W{worker_id}]"
        while True:
            candidate = None
            with self._lock:
                if not self._pool:
                    return None
                candidate = self._pool.pop(0)

            host = candidate.get("host")
            port = candidate.get("port")
            geo = candidate.get("country", "Global")
            print(f"{tag} 🔎 Menguji proksi {host}:{port} ({geo}) ke YouTube...")
            if event_callback:
                event_callback("proxy_testing", {
                    "worker_id": worker_id,
                    "host": host,
                    "port": port,
                    "country": geo
                })

            is_ok, msg, lat = test_proxy_youtube(candidate, timeout=6.0)

            with self._lock:
                remaining = len(self._pool)
                if is_ok:
                    self._used_count += 1
                    used_num = self._used_count
                    print(f"{tag} [✓] 🎉 Proksi Lolos Uji ({msg})! Dipakai untuk sesi ini (Sisa belum dipakai: {remaining})\n")
                    if event_callback:
                        event_callback("proxy_assigned", {
                            "worker_id": worker_id,
                            "host": host,
                            "port": port,
                            "country": geo,
                            "latency": lat,
                            "status": "Lolos Uji"
                        })
                    return candidate
                else:
                    self._failed_count += 1
                    print(f"{tag} [-] ❌ Proksi Gagal ({msg}). Dibuang permanen (Sisa antrean: {remaining})\n")
                    if event_callback:
                        event_callback("proxy_failed", {
                            "worker_id": worker_id,
                            "host": host,
                            "port": port,
                            "country": geo,
                            "latency": lat,
                            "status": "Gagal"
                        })

    def get_stats(self) -> Tuple[int, int, int]:
        with self._lock:
            return self._used_count, self._failed_count, len(self._pool)


def run_single_youtube_session(
    proxy: Optional[Dict[str, Any]],
    config: dict,
    worker_id: int = 1,
    session_num: int = 1,
    total_concurrency: int = 1,
    event_callback=None
) -> bool:
    """Menjalankan 1 sesi tontonan video YouTube dengan 1 proksi unik."""
    tag = f"[W{worker_id}-Sesi#{session_num}]"
    search_query = config.get("search_keyword", "horrornologi")
    target_channel = config.get("target_channel", "horrornologi")
    headless = config.get("headless", False)

    print("=" * 65)
    print(f"{tag} 🚀 Memulai Sesi YouTube Baru")
    print(f"{tag} 🎯 Target: Search '{search_query}' -> Channel '{target_channel}' -> Video Random")
    if proxy:
        print(f"{tag} 🛡️ Proksi Unik: {proxy.get('host')}:{proxy.get('port')} (Negara: {proxy.get('country', 'Global')})")
    else:
        print(f"{tag} 🛡️ Proksi: Direct Connection (Tanpa Proksi)")
    print(f"{tag} ⏱️ Durasi Nonton: Otomatis Menyesuaikan Durasi Asli Video | Resolusi: 144p")
    print("=" * 65)

    if event_callback:
        event_callback("status_update", {"worker_id": worker_id, "status": "Membuka Browser YouTube..."})

    with sync_playwright() as p:
        # Atur tata letak jendela (tiling) agar 5 batch terlihat rapi di layar
        if total_concurrency > 1 and not headless:
            grid_positions = [
                (0, 0),       # W1 (kiri atas)
                (640, 0),     # W2 (tengah atas)
                (1280, 0),    # W3 (kanan atas)
                (0, 520),     # W4 (kiri bawah)
                (640, 520),   # W5 (tengah bawah)
            ]
            pos = grid_positions[(worker_id - 1) % len(grid_positions)]
            win_size = (640, 500)
        else:
            pos = None
            win_size = (1280, 820)

        browser_args = build_browser_args(
            window_position=pos,
            window_size=win_size,
            extra_args=[
                "--disable-quic",
                "--disable-http2",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies"
            ]
        )
        proxy_dict = format_proxy_dict(proxy)

        browser = launch_browser(
            p,
            proxy_dict=proxy_dict,
            headless=headless,
            browser_args=browser_args,
            tag=tag,
        )

        proxy_country = proxy.get("country", "") if proxy else ""
        context, meta = create_stealth_context(
            browser,
            proxy_country=proxy_country,
            tag=tag,
        )

        # Pre-inject cookies persetujuan YouTube/Google agar popup 'Before you continue' tidak pernah muncul
        try:
            context.add_cookies([
                {"name": "SOCS", "value": "CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMwODI5LjA3X3AwGgJlbhACGgYIgP-8mgY", "domain": ".youtube.com", "path": "/"},
                {"name": "CONSENT", "value": "PENDING+999", "domain": ".youtube.com", "path": "/"}
            ])
        except Exception:
            pass

        page = context.new_page()

        try:
            # 1. Buka YouTube dan cari channel
            if event_callback:
                event_callback("status_update", {"worker_id": worker_id, "status": f"Mencari @{target_channel}..."})
            search_and_open_channel(page, search_query=search_query, target_channel=target_channel, tag=tag)

            # 2. Pilih video acak
            found_video = pick_and_play_random_video(page, tag=tag, event_callback=event_callback, worker_id=worker_id)
            if not found_video:
                print(f"{tag} [-] Gagal menemukan video untuk diputar. Mengakhiri sesi.")
                if event_callback:
                    event_callback("status_update", {"worker_id": worker_id, "status": "Video Tidak Ditemukan"})
                return False

            # 3. Tonton video secara organik dengan durasi menyesuaikan panjang video (144p)
            success = watch_video_organically(page, config=config, tag=tag, event_callback=event_callback, worker_id=worker_id)
            if event_callback:
                event_callback("session_finished", {"worker_id": worker_id, "success": bool(success)})
            return bool(success)

        except Exception as e:
            print(f"{tag} [-] Kendala selama sesi YouTube: {e}")
            if event_callback:
                event_callback("status_update", {"worker_id": worker_id, "status": f"Error: {str(e)[:30]}"})
            return False
        finally:
            print(f"{tag} 🧹 Menutup browser & membersihkan sesi...")
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass


def worker_loop(
    worker_id: int,
    proxy_pool: UniqueProxyPool,
    config: dict,
    stop_event: threading.Event,
    total_concurrency: int = 5,
    event_callback=None
):
    """Loop pekerjaan per worker batch: ambil 1 proksi unik -> tonton video -> ulangi."""
    tag = f"[W{worker_id}]"
    session_count = 0

    while not stop_event.is_set():
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": "Menyiapkan Proksi..."})
        # Dapatkan proksi baru yang lolos uji (proksi yang sudah dipakai tidak akan keluar lagi)
        proxy = proxy_pool.get_tested_working_proxy(worker_id=worker_id, event_callback=event_callback)
        if not proxy:
            print(f"{tag} [!] Semua proksi unik di proxies.json telah habis terpakai. Worker selesai.")
            if event_callback:
                event_callback("status_update", {"worker_id": worker_id, "status": "Proksi Habis / Selesai"})
            break

        session_count += 1
        try:
            run_single_youtube_session(
                proxy=proxy,
                config=config,
                worker_id=worker_id,
                session_num=session_count,
                total_concurrency=total_concurrency,
                event_callback=event_callback
            )
        except Exception as e:
            print(f"{tag} [-] Kendala sesi worker: {e}")

        if stop_event.is_set():
            break

        cooldown = random.uniform(3.5, 7.0)
        print(f"{tag} 💤 Pendinginan {cooldown:.1f}s sebelum mengambil video & proksi berikutnya...")
        if event_callback:
            event_callback("status_update", {"worker_id": worker_id, "status": f"Cooldown {cooldown:.0f}s..."})
        time.sleep(cooldown)


def main():
    parser = argparse.ArgumentParser(description="YouTube Organic Search & View Automation (Multi-Batch Concurrent)")
    parser.add_argument("--search", type=str, default="", help="Kata kunci pencarian YouTube (default: horrornologi)")
    parser.add_argument("--channel", type=str, default="", help="Nama channel target (default: horrornologi)")
    parser.add_argument("--watch-min", type=int, default=0, help="Durasi minimal tonton (detik)")
    parser.add_argument("--watch-max", type=int, default=0, help="Durasi maksimal tonton (detik)")
    parser.add_argument("--concurrency", "-c", type=int, default=0, help="Jumlah batch / jendela berjalan bersamaan (default: 5)")
    parser.add_argument("--headless", action="store_true", help="Jalankan di balik layar tanpa jendela")
    parser.add_argument("--no-proxy", action="store_true", help="Gunakan koneksi internet langsung tanpa proksi")
    args = parser.parse_args()

    cfg = load_config()
    if args.search:
        cfg["search_keyword"] = args.search
    if args.channel:
        cfg["target_channel"] = args.channel
    if args.watch_min > 0:
        cfg["watch_duration"]["min_seconds"] = args.watch_min
    if args.watch_max > 0:
        cfg["watch_duration"]["max_seconds"] = args.watch_max
    if args.headless:
        cfg["headless"] = True

    concurrency = args.concurrency or cfg.get("concurrency", 5)

    proxy_source = cfg.get("proxy_source", "automation/proxies.json")
    raw_proxies = []
    if not args.no_proxy:
        raw_proxies = load_proxies(proxy_source)
        if not raw_proxies:
            print("[!] Peringatan: Tidak ada proksi di proxies.json.")
    else:
        print("[*] Mode --no-proxy aktif: Menggunakan koneksi langsung.")

    proxy_pool = UniqueProxyPool(raw_proxies)

    print("\n" + "🔥" * 33)
    print("🎬 YOUTUBE ORGANIC VIEW ENGINE (5-BATCH CONCURRENT)")
    print(f"📌 Search Query     : {cfg['search_keyword']}")
    print(f"📌 Target Channel   : {cfg['target_channel']}")
    print(f"📌 Batch Concurrency: {concurrency} Jendela / Worker Berjalan Bersamaan")
    print(f"📌 Aturan Proksi    : 1 Video = 1 Proksi Berbeda (Yang Sudah Dipakai DIBUANG / Tidak Dipakai Lagi)")
    print(f"📌 Durasi Nonton    : Otomatis Menyesuaikan Durasi Asli Video (High Retention)")
    print(f"📌 Resolusi Video   : 144p (Hemat kuota & performa ringan)")
    print(f"📌 Total Proksi Awal: {len(raw_proxies)} proksi dimuat")
    print("🔥" * 33 + "\n")

    stop_event = threading.Event()

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(worker_loop, w_id, proxy_pool, cfg, stop_event, concurrency)
                for w_id in range(1, concurrency + 1)
            ]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    print(f"[-] Worker pool notice: {e}")

    except KeyboardInterrupt:
        print("\n\n[!] Sinyal Ctrl+C diterima. Menghentikan seluruh 5 worker secara tertib...")
        stop_event.set()
    finally:
        used, failed, remaining = proxy_pool.get_stats()
        print("\n" + "=" * 55)
        print("📊 REKAP PENGGUNAAN PROKSI:")
        print(f"  - Total Berhasil Dipakai : {used} proksi (video selesai ditonton)")
        print(f"  - Total Gagal / Dibuang  : {failed} proksi (mati / timeout / 402)")
        print(f"  - Sisa Belum Digunakan   : {remaining} proksi")
        print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
