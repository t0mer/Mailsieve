"""Upstream HTTP with proxy/UA rotation and retry (§5.5).

httpx URL-encodes query params, so plus-addressing (``user+tag@example.com``)
reaches the endpoint intact — such addresses are NOT filtered out (§1.2). Each
attempt runs inside the shared politeness gate; on failure the proxy is marked
bad and both proxy and user-agent rotate for the next attempt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.providers.mailboxlayer.politeness import Politeness
from app.providers.mailboxlayer.proxies import ProxyPool
from app.providers.mailboxlayer.useragents import UserAgents

ClientFactory = Callable[[str | None], httpx.AsyncClient]


class UpstreamError(Exception):
    """Raised when every attempt to reach the upstream endpoint fails."""


class UpstreamClient:
    def __init__(
        self,
        proxies: ProxyPool,
        agents: UserAgents,
        *,
        timeout_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        politeness: Politeness,
        fallback_direct: bool,
        client_factory: ClientFactory | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._proxies = proxies
        self._agents = agents
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)
        self._backoff = backoff_seconds
        self._politeness = politeness
        self._fallback_direct = fallback_direct
        self._client_factory = client_factory or self._default_factory
        self._sleep = sleep or asyncio.sleep

    def _default_factory(self, proxy: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(proxy=proxy, timeout=self._timeout)

    def _next_proxy(self) -> tuple[str | None, bool]:
        """Return (proxy, ok). ok is False when no request can be made."""
        proxy = self._proxies.pick()
        if proxy is not None:
            return proxy, True
        if self._fallback_direct:
            return None, True
        return None, False

    async def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            proxy, ok = self._next_proxy()
            if not ok:
                # Pool empty and no direct fallback: try one refresh, then give up.
                await self._proxies.refresh()
                proxy, ok = self._next_proxy()
                if not ok:
                    last_exc = UpstreamError("no proxy available")
                    break
            ua = self._agents.pick()
            try:
                async with self._politeness, self._client_factory(proxy) as client:
                    resp = await client.get(url, params=params, headers={"User-Agent": ua})
                    resp.raise_for_status()
                    data: Any = resp.json()  # raises on non-JSON body
                if not isinstance(data, dict):
                    raise UpstreamError("upstream returned a non-object JSON body")
                return data
            except (httpx.HTTPError, ValueError, UpstreamError) as exc:
                last_exc = exc
                if proxy is not None:
                    self._proxies.mark_bad(proxy)
                if attempt < self._max_retries - 1:
                    await self._sleep(self._backoff * (2**attempt))
        raise UpstreamError(
            f"upstream request failed after {self._max_retries} attempts"
        ) from last_exc
