#!/usr/bin/env python3
"""automation.smartlink.actions.scroll — fallback scroll untuk elemen di luar viewport."""

import random
import time
from typing import Any

from automation.monetag.humanizer import human_scroll


def ensure_visible(page: Any, locator: Any) -> bool:
    """Fallback: scroll viewport bertahap sampai locator terlihat."""
    vp = page.viewport_size or {"width": 1280, "height": 800}
    for _ in range(70):
        try:
            box = locator.bounding_box()
        except Exception:
            return False
        if box:
            if box["y"] >= 40 and box["y"] + box["height"] <= vp["height"] - 60:
                return True
            delta = -random.randint(350, 700) if box["y"] < 40 else random.randint(350, 700)
        else:
            return False
        human_scroll(page, delta, pause_range=(0.25, 0.6))
        time.sleep(random.uniform(0.2, 0.5))
    return False
