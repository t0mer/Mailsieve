"""Service-wide politeness: caps concurrency and paces upstream requests.

Mandatory and global (§5.6, §1.1). A single instance is shared by every caller
so the total in-flight upstream requests and their spacing are bounded no matter
how many API/UI clients arrive at once. Not disabled by config.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from types import TracebackType


class Politeness:
    def __init__(
        self,
        max_concurrent: int,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval_seconds
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._pace_lock = asyncio.Lock()
        self._last: float | None = None

    async def __aenter__(self) -> Politeness:
        await self._sem.acquire()
        try:
            async with self._pace_lock:
                now = self._clock()
                if self._last is not None:
                    wait = self._min_interval - (now - self._last)
                    if wait > 0:
                        await self._sleep(wait)
                        now = self._clock()
                self._last = now
        except BaseException:
            self._sem.release()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self._sem.release()
        return False
