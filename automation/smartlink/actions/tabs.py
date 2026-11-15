#!/usr/bin/env python3
"""
automation.smartlink.actions.tabs
Tab baru dari direct link: deteksi, layani (dwell singkat), tutup.
Tab yang tetap kosong (about:blank) dianggap gagal agar caller membuka fallback.
"""

import random
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from automation.smartlink.actions.console import log as _log


def page_host(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower()
    except Exception:
        return ""


def is_detail_url(url: str) -> bool:
    """Detail artikel di site ini pakai query ?article=<slug> (history.replaceState)."""
    return "article=" in (url or "")


def dwell_human(page: Any, worker_id: int, dwell_cfg: Dict[str, Any], free_clicks: bool = False) -> None:
    """Dwell singkat dengan batas waktu ketat (tanpa wander/klik yang bisa overshoot)."""
    dur = random.uniform(float(dwell_cfg.get("min", 1.5)), float(dwell_cfg.get("max", 3.0)))
    _log(worker_id, f"⏳ Dwell {dur:.1f}s...", "cyan")
    end = time.time() + dur
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
    except Exception:
        vp = {"width": 1280, "height": 800}
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        try:
            page.mouse.move(
                random.uniform(100, vp["width"] - 100),
                random.uniform(100, vp["height"] - 100),
            )
            if random.random() < 0.35:
                page.mouse.wheel(0, random.choice([80, 140, -60]))
        except Exception:
            pass
        time.sleep(min(random.uniform(0.3, 0.6), remaining))


def _handle_one_tab(np: Any, worker_id: int, dwell_cfg: Dict[str, Any]) -> bool:
    """Layani 1 tab baru: tunggu navigasi -> dwell -> tutup. False bila tetap kosong."""
    try:
        np.bring_to_front()
    except Exception as exc:
        _log(worker_id, f"⚠️ Tab baru tidak bisa difokuskan: {exc}", "yellow")

    navigated = False
    for _ in range(5):
        if getattr(np, "is_closed", lambda: False)():
            return False
        cur = getattr(np, "url", "") or ""
        if cur and cur != "about:blank":
            navigated = True
            break
        time.sleep(0.4)
    if not navigated:
        _log(worker_id, "⚠️ Tab baru masih kosong, tutup & pakai fallback.", "yellow")
        try:
            np.close()
        except Exception:
            pass
        return False

    try:
        np.wait_for_load_state("domcontentloaded", timeout=2000)
    except Exception:
        pass
    time.sleep(random.uniform(0.1, 0.3))
    _log(worker_id, f"🆕 Tab baru terbuka [DIRECT LINK]: {(getattr(np, 'url', '') or '')[:100]}", "bold yellow")

    dwell_human(np, worker_id, dwell_cfg)

    try:
        np.close()
        _log(worker_id, "🧹 Tab baru ditutup.", "cyan")
    except Exception:
        pass
    return True


def wait_and_handle_new_pages(
    context: Any,
    main_page: Any,
    baseline: int,
    worker_id: int,
    dwell_cfg: Dict[str, Any],
    wait_seconds: float = 2.5,
    max_tabs: int = 4,
    fallback_url: Optional[str] = None,
    sibling_grace_seconds: float = 1.5,
) -> int:
    """
    Tunggu tab baru setelah klik sampai `wait_seconds`, lalu layani
    (dwell + tutup) sampai `max_tabs`.

    Memakai `context.wait_for_event("page")` agar popup dari iframe iklan maupun
    tab yang telat ikut tertangkap (sekaligus memompa event Playwright agar
    `context.pages` ter-update). Jika tetap 0 tab baru dan `fallback_url`
    tersedia, buka manual di tab baru agar direct link tetap terlayani.
    """
    known = set(list(context.pages)[:baseline])
    handled = 0
    first_deadline = time.time() + max(1.0, wait_seconds)
    deadline = first_deadline

    def _fresh():
        return [
            p for p in context.pages
            if p not in known and p is not main_page and not getattr(p, "is_closed", lambda: False)()
        ]

    while handled < max_tabs:
        now = time.time()
        if now >= deadline:
            break
        fresh = _fresh()
        if not fresh:
            try:
                new_p = context.wait_for_event("page", timeout=min(1000.0, (deadline - now) * 1000.0))
                if (
                    new_p is not None
                    and new_p not in known
                    and new_p is not main_page
                    and not getattr(new_p, "is_closed", lambda: False)()
                ):
                    fresh = [new_p]
            except Exception:
                pass
            for p in _fresh():
                if p not in fresh:
                    fresh.append(p)
        for np in fresh:
            if np in known:
                continue
            known.add(np)
            if _handle_one_tab(np, worker_id, dwell_cfg):
                handled += 1
            deadline = time.time() + max(0.0, sibling_grace_seconds)

    # Sisa melebihi max_tabs atau telat setelah grace: tutup saja biar tidak numpuk
    for np in _fresh():
        try:
            _log(worker_id, f"🧹 Tab kelebihan ditutup: {np.url[:80]}", "cyan")
            np.close()
        except Exception:
            pass

    if handled == 0 and fallback_url:
        _log(worker_id, f"🔗 Popup direct link tidak muncul, buka manual di tab baru: {fallback_url[:100]}", "bold yellow")
        np = None
        try:
            np = context.new_page()
            np.goto(fallback_url, wait_until="domcontentloaded", timeout=45000)
            if _handle_one_tab(np, worker_id, dwell_cfg):
                handled += 1
        except Exception as exc:
            _log(worker_id, f"⚠️ Gagal buka fallback direct link: {exc}", "yellow")
            if np is not None:
                try:
                    np.close()
                except Exception:
                    pass

    return handled
