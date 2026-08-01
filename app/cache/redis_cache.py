"""Redis result cache with graceful degradation (§6).

Redis is a cache, not a dependency: any Redis error is logged (throttled) and
treated as a miss/no-op. The service NEVER 500s because Redis is down.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

import redis.asyncio as aioredis
from loguru import logger
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from app.config import RedisCfg

_WARN_INTERVAL_SECONDS = 60.0


class Cache:
    def __init__(self, cfg: RedisCfg, *, client: Any = None) -> None:
        self._enabled = cfg.enabled
        self._prefix = cfg.key_prefix
        self._client = client
        if self._enabled and self._client is None:
            self._client = aioredis.from_url(
                cfg.url,
                password=cfg.password or None,
                decode_responses=True,
            )
        self._last_warn = 0.0

    def key_for(self, email: str) -> str:
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
        return f"{self._prefix}:result:{digest}"

    def _warn(self, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._last_warn >= _WARN_INTERVAL_SECONDS:
            logger.warning("redis unavailable, serving without cache: {}", exc)
            self._last_warn = now

    async def get(self, email: str) -> dict[str, Any] | None:
        if not self._enabled or self._client is None:
            return None
        try:
            raw = await self._client.get(self.key_for(email))
        except RedisError as exc:
            self._warn(exc)
            return None
        if raw is None:
            return None
        try:
            data: Any = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    async def set(self, email: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            await self._client.set(self.key_for(email), json.dumps(payload), ex=ttl_seconds)
        except RedisError as exc:
            self._warn(exc)

    async def delete(self, email: str) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            await self._client.delete(self.key_for(email))
        except RedisError as exc:
            self._warn(exc)

    async def close(self) -> None:
        if self._client is not None:
            with contextlib.suppress(RedisError):
                await self._client.aclose()
