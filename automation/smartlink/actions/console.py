#!/usr/bin/env python3
"""automation.smartlink.actions.console — warna ANSI + log terminal berwarna."""

# ── Warna terminal (ANSI) ──
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"

_STYLES = {
    "white": "",
    "dim": DIM,
    "cyan": CYAN,
    "green": GREEN,
    "yellow": YELLOW,
    "magenta": MAGENTA,
    "red": RED,
    "bold green": BOLD + GREEN,
    "bold yellow": BOLD + YELLOW,
    "bold red": BOLD + RED,
}


def log(worker_id: int, msg: str, style: str = "white") -> None:
    color = _STYLES.get(style, "")
    print(f"{color}[W{worker_id}] {msg}{RESET}", flush=True)
