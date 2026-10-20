"""
automation.core - Reusable Playwright, Stealth, Proxy, and Human Interaction Engine
Shared across all automation targets (Blog, YouTube, Scrapers).
"""

from .stealth import (
    GEO_PROFILES,
    DEFAULT_GEO,
    get_geo_profile,
    get_fingerprint_profile,
    get_stealth_init_script,
)
from .browser import (
    build_browser_args,
    launch_browser,
    create_stealth_context,
)
from .proxy_manager import (
    ProxyManager,
    ProxyUnavailableError,
)
from .human import (
    smooth_scroll,
    natural_mouse_move,
    physical_click,
    random_pause,
)

__all__ = [
    "GEO_PROFILES",
    "DEFAULT_GEO",
    "get_geo_profile",
    "get_fingerprint_profile",
    "get_stealth_init_script",
    "build_browser_args",
    "launch_browser",
    "create_stealth_context",
    "ProxyManager",
    "ProxyUnavailableError",
    "smooth_scroll",
    "natural_mouse_move",
    "physical_click",
    "random_pause",
]
