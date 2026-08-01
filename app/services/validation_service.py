"""Validation orchestration: cache → DB → provider (§6).

Expiry evicts the cache entry only; database rows are permanent. A re-validation
appends a new row only when the result changed (``insert_if_changed``). The
upstream provider is reached only on a genuine miss, keeping the politeness
budget low.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import repository as repo
from app.db.models import ValidationResult
from app.db.session import session_scope
from app.schemas.validation import ValidationResponse

if TYPE_CHECKING:
    from app.cache.redis_cache import Cache
    from app.providers.base import Provider


def normalise(email: str) -> str:
    """Trim and lowercase the domain; the local part is left as-is."""
    email = email.strip()
    local, sep, domain = email.partition("@")
    if not sep:
        return email.lower()
    return f"{local}@{domain.lower()}"


class ValidationService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cache: Cache,
        provider: Provider,
        ttl_days: int,
    ) -> None:
        self._sm = sessionmaker
        self._cache = cache
        self._provider = provider
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400

    @property
    def ttl_days(self) -> int:
        return self._ttl_days

    def set_ttl_days(self, days: int) -> None:
        """Update the cache/freshness TTL at runtime (from a settings change)."""
        self._ttl_days = days
        self._ttl_seconds = days * 86400

    def _is_fresh(self, row: ValidationResult) -> bool:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return datetime.now(UTC) - created < timedelta(days=self._ttl_days)

    def _response(
        self, payload: dict[str, Any], email_raw: str, *, cached: bool, source: str
    ) -> ValidationResponse:
        merged = {**payload, "email_raw": email_raw, "cached": cached, "source": source}
        return ValidationResponse.model_validate(merged)

    async def validate(
        self, email_input: str, *, source: str, force: bool = False
    ) -> ValidationResponse:
        email = normalise(email_input)

        if not force:
            cached = await self._cache.get(email)
            if cached is not None:
                return self._response(cached, email_input, cached=True, source="cache")

        async with session_scope(self._sm) as session:
            if not force:
                latest_row = await repo.latest(session, email)
                if latest_row is not None and self._is_fresh(latest_row):
                    await repo.record_event(
                        session, email, latest_row.id, source, cache_hit=False
                    )
                    await self._cache.set(email, latest_row.result, self._ttl_seconds)
                    return self._response(
                        latest_row.result, email_input, cached=False, source="db"
                    )

            raw = await self._provider.validate(email, email_input)
            new_hash = repo.result_hash(raw)
            row = await repo.insert_if_changed(session, email, raw, new_hash)
            await repo.record_event(session, email, row.id, source, cache_hit=False)

        await self._cache.set(email, raw, self._ttl_seconds)
        return self._response(raw, email_input, cached=False, source="provider")
