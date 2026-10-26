#!/usr/bin/env python3
"""
automation.adsterra.gui
Wrapper untuk backward-compatibility.
GUI utama sekarang berada di automation/gui.py dan mendukung Adsterra & Monetag.
"""

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.gui import launch_gui, Dashboard, RunController, EventBridge

def launch_adsterra_gui() -> int:
    return launch_gui()

if __name__ == "__main__":
    raise SystemExit(launch_gui())
