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

# Free proxies are dead or slow; bound each proxy attempt hard so a bad proxy is
# abandoned in a few seconds and the direct fallback takes over. Direct attempts
# keep the full configured timeout.
_PROXY_ATTEMPT_TIMEOUT = 6.0


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

    def _attempt_timeout(self, proxy: str | None) -> float:
        """Direct attempts get the full timeout; proxy attempts fail fast."""
        if proxy is None:
            return self._timeout
        return min(self._timeout, _PROXY_ATTEMPT_TIMEOUT)

    def _default_factory(self, proxy: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(proxy=proxy, timeout=self._attempt_timeout(proxy))

    async def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch and parse JSON, using proxies best-effort with a direct fallback.

        Proxies are unreliable (free pool), so a proxy is tried first; the moment
        one fails — or the pool is empty — the client falls back to a direct
        request when ``fallback_direct`` is set, rather than cycling through dead
        proxies until the retry budget is exhausted.
        """
        last_exc: Exception | None = None
        go_direct = False
        for attempt in range(self._max_retries):
            if go_direct:
                proxy = None
            else:
                proxy = self._proxies.pick()
                if proxy is None:
                    if self._fallback_direct:
                        go_direct = True  # empty pool -> direct from here on
                    else:
                        await self._proxies.refresh()
                        proxy = self._proxies.pick()
                        if proxy is None:
                            last_exc = UpstreamError("no live proxy available")
                            break
            ua = self._agents.pick()
            try:
                async with self._politeness, self._client_factory(proxy) as client:
                    # Hard-bound the attempt: httpx's timeout is per-phase, so a
                    # proxy that connects then stalls could otherwise exceed it.
                    resp = await asyncio.wait_for(
                        client.get(url, params=params, headers={"User-Agent": ua}),
                        timeout=self._attempt_timeout(proxy),
                    )
                    resp.raise_for_status()
                    data: Any = resp.json()  # raises on non-JSON body
                if not isinstance(data, dict):
                    raise UpstreamError("upstream returned a non-object JSON body")
                return data
            except (httpx.HTTPError, ValueError, UpstreamError, TimeoutError) as exc:
                last_exc = exc
                if proxy is not None:
                    self._proxies.mark_bad(proxy)
                    # A proxy just failed; fall back to direct for the next attempt
                    # instead of burning the retry budget on more dead proxies.
                    if self._fallback_direct:
                        go_direct = True
                if attempt < self._max_retries - 1:
                    await self._sleep(self._backoff * (2**attempt))
        raise UpstreamError(
            f"upstream request failed after {self._max_retries} attempts"
        ) from last_exc
