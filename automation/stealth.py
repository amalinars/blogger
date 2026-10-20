#!/usr/bin/env python3
"""
automation/stealth.py - Backward Compatibility Shim
Re-exports all symbols from automation.core.stealth to ensure existing code and tests continue working seamlessly.
"""

import sys
from pathlib import Path

# Add project root to sys.path if executed directly or standalone
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.core.stealth import (
    GEO_PROFILES,
    DEFAULT_GEO,
    get_geo_profile,
    get_fingerprint_profile,
    get_stealth_init_script,
    DESKTOP_VIEWPORTS,
    WINDOWS_USER_AGENTS,
    MAC_USER_AGENTS,
)

__all__ = [
    "GEO_PROFILES",
    "DEFAULT_GEO",
    "get_geo_profile",
    "get_fingerprint_profile",
    "get_stealth_init_script",
    "DESKTOP_VIEWPORTS",
    "WINDOWS_USER_AGENTS",
    "MAC_USER_AGENTS",
]
