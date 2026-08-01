"""Rotating free-proxy pool (§5.3).

Best-effort by nature — free proxies are slow and short-lived. The pool refreshes
on an interval and on demand, hands out random live proxies, and drops proxies
the caller reports as bad until the next refresh.
"""

from __future__ import annotations

import contextlib
import secrets
import time
from collections.abc import Callable
from typing import Any

import httpx

HttpFactory = Callable[[], httpx.AsyncClient]


def _default_http_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15)


def _parse_proxies(data: Any, protocol: str) -> list[str]:
    if isinstance(data, dict):
        entries = data.get("proxies", [])
    elif isinstance(data, list):
        entries = data
    else:
        entries = []
    out: list[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if str(e.get("protocol", "")).lower() != protocol.lower():
            continue
        ip = e.get("ip")
        port = e.get("port")
        if ip and port:
            out.append(f"{protocol}://{ip}:{port}")
    return out


class ProxyPool:
    def __init__(
        self,
        source_url: str,
        protocol: str,
        max_proxies: int,
        *,
        enabled: bool = True,
        refresh_minutes: float = 10.0,
        http_factory: HttpFactory | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._url = source_url
        self._protocol = protocol
        self._max = max_proxies
        self._enabled = enabled
        self._refresh_interval = refresh_minutes * 60.0
        self._http_factory = http_factory or _default_http_factory
        self._clock = clock or time.monotonic
        self._live: list[str] = []
        self._bad: set[str] = set()
        self._refreshed_at: float | None = None

    async def refresh(self) -> None:
        if not self._enabled:
            return
        async with self._http_factory() as client:
            resp = await client.get(self._url)
            resp.raise_for_status()
            data = resp.json()
        self._live = _parse_proxies(data, self._protocol)[: self._max]
        self._bad.clear()
        self._refreshed_at = self._clock()

    async def ensure_fresh(self) -> None:
        if not self._enabled:
            return
        stale = (
            self._refreshed_at is None
            or (self._clock() - self._refreshed_at) >= self._refresh_interval
        )
        if stale:
            # Best-effort: keep whatever we have; caller handles emptiness.
            with contextlib.suppress(httpx.HTTPError):
                await self.refresh()

    def _available(self) -> list[str]:
        return [p for p in self._live if p not in self._bad]

    def pick(self) -> str | None:
        avail = self._available()
        if not avail:
            return None
        return secrets.choice(avail)

    def mark_bad(self, proxy: str) -> None:
        self._bad.add(proxy)

    def count(self) -> int:
        return len(self._available())
