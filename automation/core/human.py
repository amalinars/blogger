#!/usr/bin/env python3
"""
automation.core.human - Organic Human Interaction Simulation
Simulates human-like mouse curves, micro-step scrolling, and physical click mechanics
to ensure generated events have `isTrusted=True` and pass behavioral biometrics.
"""

import time
import random
from typing import Optional


def random_pause(min_seconds: float = 1.0, max_seconds: float = 3.0):
    """Jeda acak untuk mensimulasikan waktu reaksi manusia."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def smooth_scroll(page, distance: int, steps: int = 12):
    """
    Melakukan scrolling halus (smooth scroll) tanpa patah-patah
    dengan interpolasi micro-steps via roda mouse fisik.
    """
    try:
        if page.is_closed():
            return
        micro_dist = distance / steps
        for _ in range(steps):
            if page.is_closed():
                break
            page.mouse.wheel(0, micro_dist)
            time.sleep(random.uniform(0.012, 0.035))
    except Exception:
        pass


def natural_mouse_move(page, target_x: int, target_y: int, steps: int = 15):
    """
    Menggerakkan kursor mouse ke koordinat target secara bertahap / bertingkat
    untuk meniru lintasan pergerakan tangan manusia.
    """
    try:
        if page.is_closed():
            return
        page.mouse.move(target_x, target_y, steps=steps)
    except Exception:
        pass


def physical_click(page, x: Optional[int] = None, y: Optional[int] = None, steps: int = 14):
    """
    Melakukan klik mouse fisik alami (mouse.move -> mouse.down -> mouse.up).
    Menghasilkan browser event dengan isTrusted=True yang sah.
    """
    try:
        if page.is_closed():
            return

        if x is not None and y is not None:
            natural_mouse_move(page, x, y, steps=steps)
            time.sleep(random.uniform(0.12, 0.28))

        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.18))
        page.mouse.up()
    except Exception:
        pass
