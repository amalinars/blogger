#!/usr/bin/env python3
"""Session budgeting and execution control utilities for bot automation."""

import threading
from typing import Any, Dict, Optional


def country_label(country: Optional[str]) -> str:
    return (country or "Unknown").strip() or "Unknown"


def is_proxy_pool_exhausted(stats: Dict[str, Any]) -> bool:
    """True when no proxy is usable and no worker is still holding one."""
    if not stats:
        return False
    if stats.get("in_use", 0) > 0:
        return False
    usable = (
        stats.get("alive", 0)
        + stats.get("unknown", 0)
        + stats.get("cooldown", 0)
    )
    return usable == 0


class SessionBudget:
    """Thread-safe cap that prevents unbounded bot session visits.

    max_sessions=0 means unlimited — the budget never exhausts on its own.
    """

    def __init__(self, max_sessions: int, max_sessions_per_proxy: int = 1):
        self.max_sessions = int(max_sessions)
        self.unlimited = self.max_sessions == 0
        self.max_sessions_per_proxy = max(1, int(max_sessions_per_proxy))
        self._lock = threading.RLock()
        self.reserved = 0
        self.completed = 0
        self.passed = 0
        self.warned = 0
        self.failed = 0
        self.stopped = False
        self.proxy_counts: Dict[str, int] = {}

    def has_capacity(self) -> bool:
        with self._lock:
            if self.stopped:
                return False
            if self.unlimited:
                return True
            return self.reserved < self.max_sessions

    def is_exhausted(self) -> bool:
        with self._lock:
            if self.unlimited:
                return self.stopped
            return self.stopped or self.completed >= self.max_sessions

    def set_max_sessions(self, new_max: int) -> None:
        """Dynamically expand max_sessions when new proxies are added to pool."""
        with self._lock:
            if not self.unlimited and new_max > self.max_sessions:
                self.max_sessions = new_max

    def stop(self) -> None:
        with self._lock:
            self.stopped = True

    def reserve(self) -> bool:
        with self._lock:
            if self.stopped:
                return False
            if self.unlimited:
                self.reserved += 1
                return True
            if self.reserved >= self.max_sessions:
                return False
            self.reserved += 1
            return True

    def can_use_proxy(self, proxy_id: str) -> bool:
        with self._lock:
            if self.unlimited:
                return True
            return self.proxy_counts.get(proxy_id, 0) < self.max_sessions_per_proxy

    def mark_proxy(self, proxy_id: str) -> None:
        with self._lock:
            self.proxy_counts[proxy_id] = self.proxy_counts.get(proxy_id, 0) + 1

    def reset_proxy_counts(self) -> None:
        """Clear per-proxy usage counters (called when proxy pool loops)."""
        with self._lock:
            self.proxy_counts.clear()

    def record(self, status: str) -> None:
        with self._lock:
            self.completed += 1
            if status == "PASS":
                self.passed += 1
            elif status == "WARN":
                self.warned += 1
            else:
                self.failed += 1

    def record_session(self, proxy_id: Optional[str], status: str) -> None:
        """Helper to record session status and increment proxy count."""
        with self._lock:
            self.record(status)
            if proxy_id:
                self.proxy_counts[proxy_id] = self.proxy_counts.get(proxy_id, 0) + 1

    def covered_all(self, total_proxies: int) -> bool:
        with self._lock:
            if total_proxies <= 0:
                return False
            covered = sum(
                1
                for count in self.proxy_counts.values()
                if count >= self.max_sessions_per_proxy
            )
            return covered >= total_proxies

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "max_sessions": self.max_sessions,
                "unlimited": self.unlimited,
                "max_sessions_per_proxy": self.max_sessions_per_proxy,
                "reserved": self.reserved,
                "completed": self.completed,
                "passed": self.passed,
                "warned": self.warned,
                "failed": self.failed,
                "remaining": (0 if self.unlimited else max(0, self.max_sessions - self.completed)),
                "proxy_counts": dict(self.proxy_counts),
                "stopped": self.stopped,
            }
