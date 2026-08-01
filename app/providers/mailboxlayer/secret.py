"""Homepage request-secret lifecycle (§5.2).

The secret is a hidden input on mailboxlayer's homepage. It is cached in memory
with a TTL and refreshed lazily; concurrent refreshes are collapsed into one via
an async lock (single-flight). Failure to fetch surfaces as a provider-unavailable
condition rather than crashing the app.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import httpx
from bs4 import BeautifulSoup


class SecretUnavailable(Exception):  # noqa: N818 - descriptive name kept intentionally
    """Raised when the homepage secret cannot be fetched or parsed."""


HttpFactory = Callable[[], httpx.AsyncClient]


def _default_http_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15, follow_redirects=True)


class SecretProvider:
    def __init__(
        self,
        secret_url: str,
        input_name: str,
        ttl_minutes: float,
        *,
        http_factory: HttpFactory | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._url = secret_url
        self._input = input_name
        self._ttl = ttl_minutes * 60.0
        self._http_factory = http_factory or _default_http_factory
        self._clock = clock or time.monotonic
        self._value: str | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()
        self.ok = False
        self.last_error: str | None = None

    def parse_secret(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("input", attrs={"name": self._input})
        if tag is None:
            return None
        value = tag.get("value")  # type: ignore[union-attr]
        if isinstance(value, list):
            value = value[0] if value else None
        return value or None

    def _fresh(self) -> bool:
        return self._value is not None and (self._clock() - self._fetched_at) < self._ttl

    async def get(self) -> str:
        if self._fresh():
            assert self._value is not None
            return self._value
        return await self._refresh(force=False)

    async def force_refresh(self) -> str:
        return await self._refresh(force=True)

    async def _refresh(self, *, force: bool) -> str:
        async with self._lock:
            # Another waiter may have refreshed while we queued on the lock.
            if not force and self._fresh():
                assert self._value is not None
                return self._value
            try:
                async with self._http_factory() as client:
                    resp = await client.get(self._url)
                    resp.raise_for_status()
                    html = resp.text
            except httpx.HTTPError as exc:
                self.ok = False
                self.last_error = str(exc)
                raise SecretUnavailable(str(exc)) from exc
            secret = self.parse_secret(html)
            if not secret:
                self.ok = False
                self.last_error = f"input[name={self._input}] not found on homepage"
                raise SecretUnavailable(self.last_error)
            self._value = secret
            self._fetched_at = self._clock()
            self.ok = True
            self.last_error = None
            return secret
