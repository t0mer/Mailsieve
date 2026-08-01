"""Admin/ops endpoints: health, metrics, backup, restore."""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_backup_service, get_session, get_settings_dep, require_admin
from app.db.models import ValidationResult, VerificationEvent
from app.services.backup_service import BackupError

if TYPE_CHECKING:
    from app.config import Settings
    from app.providers.base import Provider
    from app.services.backup_service import BackupService

router = APIRouter(prefix="/api/v1", tags=["admin"])

_CHUNK = 1 << 20


def _version() -> str:
    from app.main import __version__

    return __version__


@router.get("/health", summary="Liveness + upstream reachability (always open)")
async def health(request: Request) -> dict[str, Any]:
    provider: Provider = request.app.state.provider
    session_maker = request.app.state.sessionmaker

    db_ok = True
    try:
        async with session_maker() as s:
            await s.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - health must never raise
        db_ok = False

    ph = await provider.health()
    settings: Settings = request.app.state.settings
    overall = "ok" if db_ok and ph.reachable else "degraded"
    return {
        "status": overall,
        "version": _version(),
        "database": {"ok": db_ok, "type": settings.database.type},
        "redis": {"enabled": settings.redis.enabled},
        "provider": {
            "name": "mailboxlayer",
            "reachable": ph.reachable,
            "secret_ok": ph.secret_ok,
            "proxy_count": ph.proxy_count,
            "detail": ph.detail,
        },
    }


@router.get("/metrics", summary="Basic row counts", dependencies=[Depends(require_admin)])
async def metrics(session: AsyncSession = Depends(get_session)) -> dict[str, int]:
    results = await session.scalar(select(func.count()).select_from(ValidationResult)) or 0
    events = await session.scalar(select(func.count()).select_from(VerificationEvent)) or 0
    return {"validation_results": int(results), "verification_events": int(events)}


@router.post("/backup", summary="Download a portable backup archive")
async def backup(
    svc: BackupService = Depends(get_backup_service),
    _: str = Depends(require_admin),
) -> Response:
    data = await svc.make_backup()
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="mailsieve.mailsieve-backup.gz"'},
    )


@router.post("/restore", summary="Restore from a backup archive (destructive)")
async def restore(
    request: Request,
    file: UploadFile,
    confirm_token: str = Form(...),
    svc: BackupService = Depends(get_backup_service),
    settings: Settings = Depends(get_settings_dep),
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    max_bytes = settings.backup.max_upload_mb * 1024 * 1024
    fd, path = tempfile.mkstemp(suffix=".mailsieve-backup.gz")
    written = 0
    try:
        with os.fdopen(fd, "wb") as tmp:
            while chunk := await file.read(_CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="archive exceeds the maximum upload size",
                    )
                tmp.write(chunk)
        try:
            counts = await svc.restore(path, confirm_token)
        except BackupError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        request.app.state.api_token_hash = await _reload_token_hash(request)
        return {"status": "restored", "row_counts": counts}
    finally:
        await asyncio.to_thread(_safe_unlink, path)


def _safe_unlink(path: str) -> None:
    if os.path.exists(path):
        os.unlink(path)


async def _reload_token_hash(request: Request) -> str | None:
    from app.api.routes_settings import TOKEN_KEY
    from app.db import repository as repo

    async with request.app.state.sessionmaker() as s:
        return await repo.get_setting(s, TOKEN_KEY)
