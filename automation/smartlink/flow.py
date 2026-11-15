#!/usr/bin/env python3
"""
automation.smartlink.flow
Orkestrator sesi Smartlink: buka https://ghasima.ai.studio/ lewat Camoufox + proxy,
lalu fase klik kartu artikel (lihat actions/engage.py).

Struktur:
- actions/console.py  : warna ANSI + log terminal
- actions/errors.py   : klasifikasi error sesi (chain health)
- actions/scroll.py   : scroll penuh manusiawi + bikin elemen kelihatan
- actions/tabs.py     : deteksi/klasifikasi tab baru + dwell
- actions/engage.py   : fase klik kartu + tangani tab popunder/smartlink
"""

import random
import time
from typing import Any, Dict, Optional

from camoufox.sync_api import Camoufox

from automation.engine import WORKER_STARTUP_LOCK, build_camoufox_kwargs, build_camoufox_context_options
# Re-export (dipakai runner.py): warna + klasifikasi error
from automation.smartlink.actions.console import (  # noqa: F401
    BOLD,
    CYAN,
    GREEN,
    MAGENTA,
    RED,
    RESET,
    YELLOW,
    log as _log,
)
from automation.smartlink.actions.errors import classify_session_error  # noqa: F401
from automation.smartlink.actions.engage import engage_articles
from automation.smartlink.actions.tabs import page_host

DEFAULT_TARGET_URL = "https://ghasima.ai.studio/"


def guard_main_navigation(page: Any, target_url: str, worker_id: int) -> None:
    """
    Blokir tab-under: navigasi main frame ke host luar (iklan) digagalkan.
    Iklan tetap boleh buka tab baru; yang dicegah hanya halaman utama ditimpa.
    """
    home_host = page_host(target_url)
    blocked_hosts: set = set()

    def _handler(route: Any) -> None:
        try:
            req = route.request
            if req.is_navigation_request() and req.frame == page.main_frame:
                host = page_host(req.url)
                if host and host != home_host:
                    if host not in blocked_hosts:
                        blocked_hosts.add(host)
                        _log(worker_id, f"🚫 Navigasi tab utama ke iklan diblokir: {req.url[:80]}", "yellow")
                    route.abort()
                    return
        except Exception:
            pass
        try:
            route.continue_()
        except Exception:
            pass

    page.route("**/*", _handler)


def run_smartlink_session(
    worker_id: int,
    proxy_data: Optional[Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Jalankan 1 sesi kunjungan Smartlink."""
    target_url = config.get("target_url") or DEFAULT_TARGET_URL
    headless = bool(config.get("headless", True))
    humanize_enabled = bool(config.get("humanize", True))
    proxy_info = proxy_data or {}

    if not proxy_info.get("host") or not proxy_info.get("port"):
        raise ValueError("Proxy residensial wajib aktif! Koneksi langsung (Direct IP VPS) diblokir.")
    proxy_label = f"{proxy_info.get('host')}:{proxy_info.get('port')}"

    session_start = time.time()
    _log(worker_id, f"Memulai sesi Smartlink dengan proxy: {proxy_label}", "cyan")

    camoufox_kwargs = build_camoufox_kwargs(
        proxy_data=proxy_data,
        headless=headless,
        humanize=humanize_enabled,
    )
    context_opts = build_camoufox_context_options(proxy_data)

    with Camoufox(**camoufox_kwargs) as browser:
        context = browser.new_context(**context_opts)
        page = context.new_page()
        guard_main_navigation(page, target_url, worker_id)

        with WORKER_STARTUP_LOCK:
            _log(worker_id, f"Membuka halaman Smartlink: {target_url}", "bold yellow")
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(random.uniform(0.2, 0.4))
            _log(worker_id, "🟢 Halaman Smartlink termuat.", "bold green")

        # Pemicu lazy-load instan (tanpa scroll manusiawi): ke bawah lalu balik atas
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

        # Fase klik kartu: memicu popunder onclick / smartlink, tangani tab baru
        engage_articles(context, page, worker_id, config, target_url)

        duration = round(time.time() - session_start, 1)
        _log(worker_id, f"🎉 Sesi Smartlink selesai dalam {duration}s!", "bold green")

        return {
            "worker_id": worker_id,
            "success": True,
            "duration_seconds": duration,
            "target_url": target_url,
            "proxy": proxy_label,
        }
