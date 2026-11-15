#!/usr/bin/env python3
"""
automation.smartlink.actions.engage
Fase klik kartu artikel: sorot kartu, klik gesture asli (memicu direct link),
kumpulkan tab baru. Site pure direct link — klik kartu HANYA buka direct link
di tab baru, halaman asli tetap di list. Per tab: scroll penuh + dwell 5-10s +
klik-klik bebas, tutup tab. Safety: bila halaman asli pernah masuk detail
(?article=), scroll penuh lalu balik home.
"""

import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from automation.monetag.humanizer import human_click
from automation.smartlink.actions.console import log as _log
from automation.smartlink.actions.scroll import ensure_visible
from automation.smartlink.actions.tabs import (
    is_detail_url,
    page_host,
    wait_and_handle_new_pages,
)


def engage_articles(
    context: Any,
    page: Any,
    worker_id: int,
    config: Dict[str, Any],
    target_url: str,
) -> None:
    """Jalankan beberapa percobaan klik kartu + tangani tab yang terbuka."""
    attempts = max(1, int(config.get("click_attempts", 3)))
    dwell_cfg = config.get("dwell_seconds", {}) or {"min": 5.0, "max": 10.0}
    home_host = page_host(target_url)
    card_order: Optional[List[int]] = None

    for attempt in range(1, attempts + 1):
        # Pastikan halaman asli di home (bukan detail, bukan kena redirect popunder)
        if page_host(page.url) != home_host or is_detail_url(page.url):
            try:
                _log(worker_id, f"↩️ Tab utama tidak di home ({page.url[:100]}), kembali ke home...", "yellow")
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(random.uniform(1.0, 1.8))
            except Exception as exc:
                _log(worker_id, f"⚠️ Gagal kembali home: {exc}", "red")
                break
        try:
            page.bring_to_front()
        except Exception:
            pass

        cards = page.locator("article")
        try:
            n_cards = cards.count()
        except Exception:
            n_cards = 0
        if n_cards == 0:
            _log(worker_id, "⚠️ Kartu artikel tidak ditemukan, hentikan fase klik.", "yellow")
            break

        # Pilih kartu unik per sesi (tanpa pengulangan); daftar dibekukan di awal
        if card_order is None:
            card_order = random.sample(range(n_cards), k=min(attempts, n_cards))
        card_order = [i for i in card_order if i < n_cards]
        if not card_order:
            _log(worker_id, "✅ Semua kartu artikel sudah dikunjungi sesi ini.", "cyan")
            break
        idx = card_order.pop(0)
        card = cards.nth(idx)
        title = card.locator("h3").first
        link_loc = card.locator("h3 a").first
        try:
            if not link_loc.count():
                link_loc = card.locator("a[href]").first
        except Exception:
            pass
        href: Optional[str] = None
        try:
            if link_loc.count():
                raw_href = link_loc.get_attribute("href")
                if raw_href and not raw_href.startswith(("javascript:", "#")):
                    href = urljoin(target_url, raw_href)
        except Exception:
            href = None

        _log(
            worker_id,
            f"🖱️ Percobaan {attempt}/{attempts}: sorot kartu artikel #{idx + 1}...",
            "cyan",
        )
        try:
            target_loc = link_loc if link_loc.count() else (title if title.count() else card)
        except Exception:
            target_loc = title if title.count() else card
        pages_before = len(context.pages)
        clicked = None
        # Klik native Playwright: auto-scroll + gesture trusted, jauh lebih cepat
        fast_click = getattr(target_loc, "click", None)
        if callable(fast_click):
            try:
                fast_click(timeout=3000)
                clicked = (0.0, 0.0)
            except Exception as exc:
                _log(worker_id, f"⚠️ Klik cepat gagal ({exc}), pakai gesture manual...", "yellow")

        if clicked is None:
            visible = True
            scroll_js = getattr(target_loc, "evaluate", None)
            if callable(scroll_js):
                try:
                    scroll_js("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
                except Exception:
                    visible = ensure_visible(page, target_loc)
            else:
                visible = ensure_visible(page, target_loc)
            if not visible:
                try:
                    box = target_loc.bounding_box()
                except Exception:
                    box = None
                _log(worker_id, f"⚠️ Kartu tidak terjangkau viewport (url={page.url[:80]}, box={box}), lewati.", "yellow")
                continue
            try:
                clicked = human_click(page, target_loc)
                if clicked is None:
                    box = card.bounding_box()
                    if box:
                        clicked = human_click(page, (box["x"] + box["width"] * 0.5,
                                                     box["y"] + min(box["height"] * 0.2, 220)))
            except Exception as exc:
                _log(worker_id, f"⚠️ Klik gagal: {exc}", "yellow")
        if clicked is None:
            _log(worker_id, "⚠️ Klik tidak terkirim, ulang percobaan berikutnya.", "yellow")
            continue
        _log(worker_id, "👆 Klik gesture asli terkirim ke kartu.", "bold yellow")
        time.sleep(0.3)

        # Site pure direct link: klik kartu HANYA buka direct link di tab baru,
        # halaman asli tetap di list. Tab baru (termasuk yang telat >10 detik,
        # ad-chain uplcm -> redirect) dipolling lalu dilayani scroll + dwell.
        handled = wait_and_handle_new_pages(
            context, page, pages_before, worker_id, dwell_cfg,
            wait_seconds=float(config.get("tab_wait_seconds", 2.5)),
            fallback_url=href,
            sibling_grace_seconds=float(config.get("sibling_grace_seconds", 1.5)),
        )
        if handled == 0:
            _log(worker_id, "ℹ️ Tidak ada tab baru terbuka (direct link belum trigger).", "yellow")
        else:
            _log(worker_id, f"🔎 Klik kartu -> {handled} tab direct link dilayani.", "bold yellow")

        # Halaman asli: pulihkan jika ditimpa iklan (host berubah) atau masuk detail (?article=)
        try:
            page.bring_to_front()
        except Exception:
            pass
        cur_url = getattr(page, "url", "") or ""
        if page_host(cur_url) != home_host:
            _log(worker_id, f"↩️ Tab utama ditimpa iklan ({cur_url[:80]}), kembali ke home...", "yellow")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(random.uniform(0.4, 0.8))
            except Exception as exc:
                _log(worker_id, f"⚠️ Gagal kembali home: {exc}", "red")
                break
        elif is_detail_url(cur_url):
            _log(worker_id, "📖 Halaman asli di detail artikel, kembali ke home...", "cyan")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(random.uniform(0.4, 0.8))
            except Exception as exc:
                _log(worker_id, f"⚠️ Gagal kembali home: {exc}", "red")
                break

        if attempt < attempts:
            time.sleep(random.uniform(0.3, 0.8))
