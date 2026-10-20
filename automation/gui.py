#!/usr/bin/env python3
"""
automation/gui.py - Backward Compatibility Shim
Launches automation.blog.gui while allowing existing shortcuts and ./run_gui.sh to work directly.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.blog.gui import main, TrafficBotGUI, BotProcessWorker

if __name__ == "__main__":
    main()
