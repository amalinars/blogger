#!/usr/bin/env python3
"""
automation.monetag.humanizer
Perilaku mouse dan interaksi ultra-natural untuk menghindari bot-detection Monetag.
Menggunakan kurva Bézier, micro-tremor, variasi kecepatan, dan click offset acak.
"""

import math
import random
import time
from typing import Any, Dict, Optional, Tuple, Union


def _cubic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    """Menghitung titik pada kurva Bézier kubik pada parameter t [0, 1]."""
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return x, y


def human_move(
    page: Any,
    target_x: float,
    target_y: float,
    current_x: Optional[float] = None,
    current_y: Optional[float] = None,
    steps: Optional[int] = None,
) -> Tuple[float, float]:
    """
    Menggerakkan kursor mouse ke (target_x, target_y) mengikuti kurva Bézier manusiawi,
    lengkap dengan deviasi acak dan micro-jitter di sepanjang jalur.
    """
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
    except Exception:
        vp = {"width": 1280, "height": 800}

    # Titik awal
    start_x = current_x if current_x is not None else random.uniform(100, vp["width"] - 100)
    start_y = current_y if current_y is not None else random.uniform(100, vp["height"] - 100)

    # Jarak
    dx = target_x - start_x
    dy = target_y - start_y
    distance = math.hypot(dx, dy)

    if steps is None:
        steps = max(12, int(distance / 25) + random.randint(5, 12))

    # Titik kontrol kurva dengan lengkungan alami
    deviation = min(distance * 0.35, 180.0)
    ctrl1_x = start_x + dx * random.uniform(0.15, 0.4) + random.uniform(-deviation, deviation)
    ctrl1_y = start_y + dy * random.uniform(0.15, 0.4) + random.uniform(-deviation, deviation)
    ctrl2_x = start_x + dx * random.uniform(0.6, 0.85) + random.uniform(-deviation, deviation)
    ctrl2_y = start_y + dy * random.uniform(0.6, 0.85) + random.uniform(-deviation, deviation)

    p0 = (start_x, start_y)
    p1 = (ctrl1_x, ctrl1_y)
    p2 = (ctrl2_x, ctrl2_y)
    p3 = (target_x, target_y)

    for i in range(1, steps + 1):
        t = i / steps
        # Easing in-out (lambat di awal, cepat di tengah, melambat saat mendekati target)
        ease_t = 3 * (t ** 2) - 2 * (t ** 3)
        bx, by = _cubic_bezier(p0, p1, p2, p3, ease_t)

        # Micro-tremor (getaran tangan manusia)
        jitter_x = random.uniform(-0.8, 0.8) if i < steps else 0
        jitter_y = random.uniform(-0.8, 0.8) if i < steps else 0

        final_x = max(0, min(vp["width"], bx + jitter_x))
        final_y = max(0, min(vp["height"], by + jitter_y))

        try:
            page.mouse.move(final_x, final_y)
        except Exception:
            break

        # Variasi jeda antar-langkah (1-4ms)
        time.sleep(random.uniform(0.002, 0.007))

    return target_x, target_y


def human_click(
    page: Any,
    target: Union[str, Any, Tuple[float, float]],
    current_pos: Optional[Tuple[float, float]] = None,
) -> Optional[Tuple[float, float]]:
    """
    Melakukan klik ultra-humanize pada elemen atau koordinat:
    1. Mencari koordinat acak di dalam area elemen (bukan dead-center eksak).
    2. Menggerakkan mouse dengan kurva Bézier alami.
    3. Memberi jeda berpikir sebelum mouse down.
    4. Mouse down -> Hold delay fisik (60-150ms) -> Mouse up.
    5. Jeda penyelesaian setelah klik.
    """
    click_x: float = 0.0
    click_y: float = 0.0

    cur_x = current_pos[0] if current_pos else None
    cur_y = current_pos[1] if current_pos else None

    # Tentukan koordinat target
    if isinstance(target, tuple):
        click_x, click_y = target
    elif isinstance(target, str):
        # Target adalah selector string
        loc = page.locator(target).first
        try:
            loc.wait_for(state="visible", timeout=6000)
            box = loc.bounding_box()
            if not box:
                return None
            # Acak di area 25% - 75% elemen (hindari border)
            click_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
            click_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
        except Exception:
            return None
    else:
        # Target adalah Locator Playwright
        try:
            box = target.bounding_box()
            if not box:
                return None
            click_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
            click_y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
        except Exception:
            return None

    # Gerakkan mouse ke posisi target
    end_x, end_y = human_move(page, click_x, click_y, current_x=cur_x, current_y=cur_y)

    # Jeda natural sebelum jari menekan (hesitation delay)
    time.sleep(random.uniform(0.12, 0.28))

    # Eksekusi klik fisik (Mouse Down -> Hold -> Mouse Up)
    try:
        page.mouse.down()
        time.sleep(random.uniform(0.065, 0.145))
        page.mouse.up()
    except Exception:
        pass

    # Jeda pasca-klik
    time.sleep(random.uniform(0.25, 0.55))
    return end_x, end_y


def human_scroll(
    page: Any,
    scroll_amount: int,
    pause_range: Tuple[float, float] = (0.2, 0.5),
) -> None:
    """
    Simulasi scroll mouse-wheel natural:
    - Dipecah menjadi beberapa chunk scroll kecil (70 - 200px).
    - Ada peluang 15% scroll mundur sedikit seolah user membaca ulang konten.
    """
    direction = 1 if scroll_amount > 0 else -1
    remaining = abs(scroll_amount)

    while remaining > 0:
        chunk = min(remaining, random.randint(70, 210))
        delta_y = chunk * direction

        # 15% kemungkinan re-scroll mundur sedikit
        if random.random() < 0.15 and remaining > 150:
            back_delta = -int(chunk * random.uniform(0.3, 0.6)) * direction
            try:
                page.mouse.wheel(0, back_delta)
            except Exception:
                pass
            time.sleep(random.uniform(0.15, 0.35))

        try:
            page.mouse.wheel(0, delta_y)
        except Exception:
            break

        remaining -= chunk
        time.sleep(random.uniform(*pause_range))


def human_wander(page: Any, duration_seconds: float) -> None:
    """
    Simulasi pengunjung sedang memperhatikan / membaca halaman:
    Menggerakkan mouse santai, berhenti sesaat, dan sesekali scrolling kecil.
    """
    started = time.time()
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
    except Exception:
        vp = {"width": 1280, "height": 800}

    cur_x = random.uniform(200, vp["width"] - 200)
    cur_y = random.uniform(200, vp["height"] - 200)

    while time.time() - started < duration_seconds:
        # Pindah kursor santai
        next_x = max(100, min(vp["width"] - 100, cur_x + random.uniform(-250, 250)))
        next_y = max(100, min(vp["height"] - 100, cur_y + random.uniform(-200, 200)))
        cur_x, cur_y = human_move(page, next_x, next_y, current_x=cur_x, current_y=cur_y, steps=random.randint(15, 30))

        # Jeda membaca
        time.sleep(random.uniform(0.8, 2.2))

        # Sesekali scroll halus
        if random.random() < 0.4:
            human_scroll(page, random.choice([80, 140, -60]), pause_range=(0.1, 0.3))

        time.sleep(random.uniform(0.5, 1.2))
