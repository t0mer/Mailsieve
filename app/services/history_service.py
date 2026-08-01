"""History listing and revision diffing.

The results table is append-only, so history is a record of what changed and
when. Listing is server-side paginated (limit clamped to 250 in the repository);
the diff compares any two revisions of one address.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.db import repository as repo
from app.db.session import session_scope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.db.models import ValidationResult

# Volatile fields are ignored when diffing, matching the change-detection hash.
_VOLATILE = ("checked_at", "cached", "source")


def _iso(dt: Any) -> str:
    return dt.isoformat() if dt is not None else ""


def _row_dict(row: ValidationResult) -> dict[str, Any]:
    result = row.result
    return {
        "id": row.id,
        "email": row.email,
        "verdict": result.get("verdict"),
        "score": result.get("score"),
        "created_at": _iso(row.created_at),
        "result": result,
    }


class HistoryService:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def list_history(
        self,
        *,
        limit: int,
        offset: int,
        sort: str,
        order: str,
        search: str | None,
    ) -> dict[str, Any]:
        async with session_scope(self._sm) as s:
            rows, total = await repo.paginate(
                s, limit=limit, offset=offset, sort=sort, order=order, search=search
            )
            counts = await repo.counts_by_email(s, [r.email for r in rows])
            items = []
            for r in rows:
                d = _row_dict(r)
                d["revision_count"] = counts.get(r.email, 1)
                items.append(d)
        return {
            "items": items,
            "total": total,
            "limit": repo.clamp_limit(limit),
            "offset": max(0, offset),
        }

    async def history_for(self, email: str) -> list[dict[str, Any]]:
        async with session_scope(self._sm) as s:
            rows = await repo.revisions(s, email)
        return [_row_dict(r) for r in rows]

    async def diff(self, email: str, rev_a: int, rev_b: int) -> dict[str, Any]:
        async with session_scope(self._sm) as s:
            a = await repo.get_by_id(s, rev_a)
            b = await repo.get_by_id(s, rev_b)
            timeline = [
                {"id": r.id, "created_at": _iso(r.created_at), "verdict": r.result.get("verdict")}
                for r in await repo.revisions(s, email)
            ]
        if a is None or b is None or a.email != email or b.email != email:
            raise ValueError("revision not found for this address")

        changed: dict[str, dict[str, Any]] = {}
        keys = (set(a.result) | set(b.result)) - set(_VOLATILE)
        for key in sorted(keys):
            av = a.result.get(key)
            bv = b.result.get(key)
            if av != bv:
                changed[key] = {"from": av, "to": bv}

        return {
            "email": email,
            "a": _row_dict(a),
            "b": _row_dict(b),
            "changed": changed,
            "timeline": timeline,
        }
