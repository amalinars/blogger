#!/usr/bin/env python3
"""
automation/traffic_bot.py - Backward Compatibility Shim
Forwards execution to automation.blog.bot while preserving CLI arguments and symbol exports.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.blog.bot import (
    main,
    run_session,
    run_single_session_safe,
    get_organic_referer,
    DEFAULT_REFERERS,
    load_config,
    load_proxies,
    resolve_proxy_path,
    ProxyManager,
    ProxyUnavailableError,
)

__all__ = [
    "main",
    "run_session",
    "run_single_session_safe",
    "get_organic_referer",
    "DEFAULT_REFERERS",
    "load_config",
    "load_proxies",
    "resolve_proxy_path",
    "ProxyManager",
    "ProxyUnavailableError",
]

if __name__ == "__main__":
    main()
