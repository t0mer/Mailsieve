"""Data access for the append-only result store.

The central rule (§4): a re-check appends a new ``validation_results`` row only
when the *stable* portion of the result changes. ``result_hash`` excludes the
volatile fields (``checked_at``, ``cached``, ``source``) so an identical outcome
re-check produces no new row — getting this exclusion list wrong defeats the
whole design, so it is unit-tested.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventSource, ValidationResult, VerificationEvent

# Maximum rows a single history page may return, regardless of client request.
MAX_PAGE = 250

# Fields that vary between identical outcomes and must NOT affect the hash.
_VOLATILE_FIELDS = ("checked_at", "cached", "source")


def result_hash(payload: dict[str, Any]) -> str:
    """sha256 over the canonical result, excluding volatile fields."""
    stable = {k: v for k, v in payload.items() if k not in _VOLATILE_FIELDS}
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def clamp_limit(limit: int) -> int:
    """Clamp a requested page size into ``[1, MAX_PAGE]``."""
    return max(1, min(limit, MAX_PAGE))


async def latest(session: AsyncSession, email: str) -> ValidationResult | None:
    """Return the newest stored result for ``email``, or None."""
    stmt = (
        select(ValidationResult)
        .where(ValidationResult.email == email)
        .order_by(ValidationResult.created_at.desc(), ValidationResult.id.desc())
        .limit(1)
    )
    return cast("ValidationResult | None", await session.scalar(stmt))


async def insert_if_changed(
    session: AsyncSession, email: str, result: dict[str, Any], new_hash: str
) -> ValidationResult:
    """Insert a new row only when the latest hash differs; return the effective row."""
    current = await latest(session, email)
    if current is not None and current.result_hash == new_hash:
        return current
    row = ValidationResult(email=email, result=result, result_hash=new_hash)
    session.add(row)
    await session.flush()
    return row


async def record_event(
    session: AsyncSession,
    email: str,
    result_id: int,
    source: str,
    cache_hit: bool,
) -> None:
    """Record that ``email`` was checked, without touching the results table."""
    session.add(
        VerificationEvent(
            email=email,
            result_id=result_id,
            source=EventSource(source),
            cache_hit=cache_hit,
        )
    )
    await session.flush()


async def get_by_id(session: AsyncSession, result_id: int) -> ValidationResult | None:
    """Fetch a single stored result by primary key."""
    return await session.get(ValidationResult, result_id)


async def counts_by_email(
    session: AsyncSession, emails: list[str]
) -> dict[str, int]:
    """Number of stored revisions for each of ``emails`` (missing = absent key)."""
    if not emails:
        return {}
    stmt = (
        select(ValidationResult.email, func.count())
        .where(ValidationResult.email.in_(emails))
        .group_by(ValidationResult.email)
    )
    rows = await session.execute(stmt)
    return dict(rows.tuples().all())


async def revisions(session: AsyncSession, email: str) -> list[ValidationResult]:
    """All stored revisions for ``email``, newest first."""
    stmt = (
        select(ValidationResult)
        .where(ValidationResult.email == email)
        .order_by(ValidationResult.created_at.desc(), ValidationResult.id.desc())
    )
    return list((await session.scalars(stmt)).all())


def _sort_column(sort: str) -> Any:
    if sort == "email":
        return ValidationResult.email
    if sort in ("verdict", "reason", "provider"):
        return ValidationResult.result[sort].as_string()
    if sort == "score":
        return ValidationResult.result["score"].as_float()
    # default and "created_at"/"checked_at" alias
    return ValidationResult.created_at


async def paginate(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    sort: str,
    order: str,
    search: str | None,
) -> tuple[list[ValidationResult], int]:
    """Server-side paginated listing. ``limit`` is clamped to ``MAX_PAGE``."""
    limit = clamp_limit(limit)
    offset = max(0, offset)

    filters = []
    if search:
        filters.append(ValidationResult.email.ilike(f"%{search}%"))

    col = _sort_column(sort)
    col = col.asc() if order.lower() == "asc" else col.desc()

    rows_stmt = (
        select(ValidationResult)
        .where(*filters)
        .order_by(col, ValidationResult.id.asc())
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count()).select_from(ValidationResult).where(*filters)

    rows = list((await session.scalars(rows_stmt)).all())
    total = int(await session.scalar(count_stmt) or 0)
    return rows, total
