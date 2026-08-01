"""History and diff endpoints. Server-side paginated; limit clamped to 250."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_history_service, require_api

if TYPE_CHECKING:
    from app.services.history_service import HistoryService

router = APIRouter(prefix="/api/v1", tags=["history"])


@router.get("/history", summary="List validation history (paginated)")
async def list_history(
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    sort: str = "created_at",
    order: str = "desc",
    search: str | None = None,
    svc: HistoryService = Depends(get_history_service),
    _: str = Depends(require_api),
) -> dict[str, Any]:
    return await svc.list_history(
        limit=limit, offset=offset, sort=sort, order=order, search=search
    )


@router.get("/history/{email}", summary="All stored revisions for an address")
async def history_for(
    email: str,
    svc: HistoryService = Depends(get_history_service),
    _: str = Depends(require_api),
) -> list[dict[str, Any]]:
    return await svc.history_for(email)


@router.get("/history/{email}/diff", summary="Diff two revisions of an address")
async def history_diff(
    email: str,
    a: int,
    b: int,
    svc: HistoryService = Depends(get_history_service),
    _: str = Depends(require_api),
) -> dict[str, Any]:
    try:
        return await svc.diff(email, a, b)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
