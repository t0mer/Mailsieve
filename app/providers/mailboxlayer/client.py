"""Upstream HTTP: direct-first with proxy failover (§5.5).

The direct request to mailboxlayer is fast and reliable, so it is the primary
path. Only if the direct attempt fails (e.g. the IP is blocked) does the client
rotate through the proxy pool — which is fetched lazily at that point, never on
the hot path. Each attempt runs inside the shared politeness gate.

httpx URL-encodes query params, so plus-addressing (``user+tag@example.com``)
reaches the endpoint intact — such addresses are NOT filtered out (§1.2).
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
        client_factory: ClientFactory | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._proxies = proxies
        self._agents = agents
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)
        self._backoff = backoff_seconds
        self._politeness = politeness
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
        """Fetch and parse JSON, direct-first with proxy as a last-resort failover.

        Direct is the fast, reliable path, so every attempt is direct except the
        final one — a transient upstream hiccup (e.g. a non-JSON body) is retried
        directly rather than jumping to the slow proxy pool. Only the last attempt
        fails over to a proxy (e.g. if the IP is blocked), refreshing the pool
        lazily at that point. If proxies are disabled/empty, the last attempt is
        direct too.
        """
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            final_failover = attempt == self._max_retries - 1 and attempt > 0
            if final_failover:
                await self._proxies.ensure_fresh()  # lazy: only now that it's needed
                proxy = self._proxies.pick()  # None if proxies disabled/empty -> direct
            else:
                proxy = None  # direct: primary path + fast retries for transient errors
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
                if attempt < self._max_retries - 1:
                    await self._sleep(self._backoff * (2**attempt))
        raise UpstreamError(
            f"upstream request failed after {self._max_retries} attempts"
        ) from last_exc
