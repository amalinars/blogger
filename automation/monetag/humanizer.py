#!/usr/bin/env python3
"""
automation.monetag.humanizer
Gerakan mouse Bézier, klik fisik, dan scroll ringan untuk Camoufox (C++ humanize=True).
Dioptimalkan agar hemat CPU IPC saat menjalankan banyak worker sekaligus.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Optional, Tuple, Union


def _cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    u = 1.0 - t
    tt = t * t
    uu = u * u
    x = (uu * u) * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + (tt * t) * p3[0]
    y = (uu * u) * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + (tt * t) * p3[1]
    return x, y


def human_move(
    page: Any,
    target_x: float,
    target_y: float,
    current_x: Optional[float] = None,
    current_y: Optional[float] = None,
    steps: Optional[int] = None,
) -> Tuple[float, float]:
    """Gerakkan kursor mengikuti 3-6 waypoint kurva Bézier (C++ Camoufox menghaluskan sub-step)."""
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
    except Exception:
        vp = {"width": 1280, "height": 800}

    start_x = current_x if current_x is not None else random.uniform(100, vp["width"] - 100)
    start_y = current_y if current_y is not None else random.uniform(100, vp["height"] - 100)

    dx = target_x - start_x
    dy = target_y - start_y
    distance = math.hypot(dx, dy)

    if steps is None:
        steps = max(3, min(6, int(distance / 140) + 2))

    deviation = min(distance * 0.30, 140.0)
    p0 = (start_x, start_y)
    p1 = (
        start_x + dx * random.uniform(0.18, 0.38) + random.uniform(-deviation, deviation),
        start_y + dy * random.uniform(0.18, 0.38) + random.uniform(-deviation, deviation),
    )
    p2 = (
        start_x + dx * random.uniform(0.62, 0.85) + random.uniform(-deviation, deviation),
        start_y + dy * random.uniform(0.62, 0.85) + random.uniform(-deviation, deviation),
    )
    p3 = (target_x, target_y)

    for i in range(1, steps + 1):
        t = i / steps
        ease_t = 3 * (t ** 2) - 2 * (t ** 3)
        bx, by = _cubic_bezier(p0, p1, p2, p3, ease_t)
        jx = random.uniform(-0.8, 0.8) if i < steps else 0.0
        jy = random.uniform(-0.8, 0.8) if i < steps else 0.0
        fx = max(1.0, min(float(vp["width"] - 1), bx + jx))
        fy = max(1.0, min(float(vp["height"] - 1), by + jy))
        try:
            page.mouse.move(fx, fy)
        except Exception:
            break
        time.sleep(random.uniform(0.005, 0.015))

    return target_x, target_y


def human_click(
    page: Any,
    target: Union[str, Any, Tuple[float, float]],
    current_pos: Optional[Tuple[float, float]] = None,
) -> Optional[Tuple[float, float]]:
    """Klik fisik (move -> hesitation -> mouse.down -> hold -> mouse.up) pada koordinat atau elemen."""
    cur_x = current_pos[0] if current_pos else None
    cur_y = current_pos[1] if current_pos else None

    if isinstance(target, tuple):
        click_x, click_y = float(target[0]), float(target[1])
    elif isinstance(target, str):
        loc = page.locator(target).first
        try:
            loc.wait_for(state="visible", timeout=5000)
            box = loc.bounding_box()
            if not box:
                return None
            click_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
            click_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
        except Exception:
            return None
    else:
        try:
            box = target.bounding_box()
            if not box:
                return None
            click_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
            click_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
        except Exception:
            return None

    end_x, end_y = human_move(page, click_x, click_y, current_x=cur_x, current_y=cur_y)
    time.sleep(random.uniform(0.08, 0.20))

    try:
        page.mouse.down()
        time.sleep(random.uniform(0.055, 0.130))
        page.mouse.up()
    except Exception:
        pass

    time.sleep(random.uniform(0.20, 0.45))
    return end_x, end_y


def human_scroll(
    page: Any,
    scroll_amount: int,
    pause_range: Tuple[float, float] = (0.15, 0.35),
) -> None:
    """Simulasi scroll roda mouse natural dalam beberapa chunk kecil."""
    direction = 1 if scroll_amount > 0 else -1
    remaining = abs(scroll_amount)

    while remaining > 0:
        chunk = min(remaining, random.randint(90, 240))
        delta_y = chunk * direction

        if random.random() < 0.12 and remaining > 180:
            try:
                page.mouse.wheel(0, -int(chunk * 0.4) * direction)
            except Exception:
                pass
            time.sleep(random.uniform(0.12, 0.25))

        try:
            page.mouse.wheel(0, delta_y)
        except Exception:
            break

        remaining -= chunk
        time.sleep(random.uniform(*pause_range))


def human_wander(page: Any, duration_seconds: float) -> None:
    """Gerakkan kursor santai dan sesekali scroll kecil selama masa dwell."""
    started = time.time()
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
    except Exception:
        vp = {"width": 1280, "height": 800}

    cur_x = random.uniform(180, max(220, vp["width"] - 180))
    cur_y = random.uniform(180, max(220, vp["height"] - 180))

    while time.time() - started < duration_seconds:
        next_x = max(80.0, min(float(vp["width"] - 80), cur_x + random.uniform(-220, 220)))
        next_y = max(80.0, min(float(vp["height"] - 80), cur_y + random.uniform(-180, 180)))
        cur_x, cur_y = human_move(page, next_x, next_y, current_x=cur_x, current_y=cur_y, steps=random.randint(3, 5))

        rem = duration_seconds - (time.time() - started)
        if rem <= 0:
            break
        time.sleep(min(rem, random.uniform(0.6, 1.4)))

        if random.random() < 0.35 and (time.time() - started) < duration_seconds:
            human_scroll(page, random.choice([90, 150, -70]), pause_range=(0.1, 0.25))
