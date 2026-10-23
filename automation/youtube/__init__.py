"""
automation.youtube
YouTube Organic Retention & Ad Detection Suite with Camoufox Anti-Detect Browser.
"""

from .bot import (
    load_config,
    execute_search_flow,
    watch_video_dynamically,
    run_worker_session,
    worker_thread_loop,
    AdTracker,
)
from .camoufox_engine import (
    create_camoufox_session,
    build_camoufox_kwargs,
    get_proxy_credentials,
)
from .tui import TUIManager, launch_youtube_tui

__all__ = [
    "load_config",
    "execute_search_flow",
    "watch_video_dynamically",
    "run_worker_session",
    "worker_thread_loop",
    "AdTracker",
    "create_camoufox_session",
    "build_camoufox_kwargs",
    "get_proxy_credentials",
    "TUIManager",
    "launch_youtube_tui",
]
