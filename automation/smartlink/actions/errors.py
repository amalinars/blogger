#!/usr/bin/env python3
"""automation.smartlink.actions.errors — klasifikasi error sesi untuk ChainProxyProvider."""

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


def _looks_like_shutdown(error: BaseException) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in _SHUTDOWN_MARKERS)


def classify_session_error(error: BaseException, stopping: bool = False) -> str:
    """Klasifikasi error sesi untuk keputusan health/cooldown di ChainProxyProvider."""
    if stopping or _looks_like_shutdown(error):
        return "shutdown"
    text = str(error or "").lower()
    if any(marker in text for marker in _PROXY_ERROR_MARKERS):
        return "proxy"
    if "cloudflare" in text or "turnstile" in text or "just a moment" in text:
        return "cloudflare"
    return "other"
