"""Simple in-memory fixed-window rate limiter for the client-facing API.

This is the client limit (default 60/min). It is separate from and independent
of the upstream politeness budget (§5.6), which always applies.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock or time.monotonic
        self._buckets: dict[str, tuple[float, int]] = {}

    def check(self, key: str) -> bool:
        """Record a hit for ``key``; return False when over the limit."""
        now = self._clock()
        start, count = self._buckets.get(key, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        count += 1
        self._buckets[key] = (start, count)
        return count <= self._limit
