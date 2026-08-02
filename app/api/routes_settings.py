"""Settings + API-token management. Guarded by require_admin (§8).

The token is shown once on generation and stored bcrypt-hashed; it is never
returned again. TTL changes take effect immediately and persist across restarts.
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_settings_dep, require_admin
from app.auth.api_key import hash_secret
from app.config import Settings
from app.db import repository as repo

router = APIRouter(prefix="/api/v1", tags=["settings"])

TOKEN_KEY = "api_token_hash"  # noqa: S105 - a settings key name, not a secret
TTL_KEY = "ttl_days"


class SettingsUpdate(BaseModel):
    ttl_days: int | None = Field(default=None, ge=1)


class TokenResponse(BaseModel):
    token: str
    warning: str = "Store this now — it will not be shown again."


def _masked_view(request: Request, settings: Settings) -> dict[str, Any]:
    token_set = bool(getattr(request.app.state, "api_token_hash", None))
    return {
        "server": {"host": settings.server.host, "port": settings.server.port},
        "database": {"type": settings.database.type},
        "redis": {"enabled": settings.redis.enabled},
        "validation": {"ttl_days": request.app.state.validation.ttl_days},
        "auth": {
            "api": {"enabled": settings.auth.api.enabled, "token_set": token_set},
            "ui": {"enabled": settings.auth.ui.enabled, "username": settings.auth.ui.username},
        },
        "mailboxlayer": {
            "proxies_enabled": settings.mailboxlayer.proxies.enabled,
        },
        "backup": {"max_upload_mb": settings.backup.max_upload_mb},
    }


@router.get("/settings", summary="Current settings (secrets masked)")
async def get_settings_view(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    return _masked_view(request, settings)


@router.put("/settings", summary="Update mutable settings (TTL)")
async def update_settings(
    body: SettingsUpdate,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    if body.ttl_days is not None:
        request.app.state.validation.set_ttl_days(body.ttl_days)
        await repo.set_setting(session, TTL_KEY, str(body.ttl_days))
        await session.commit()
    return _masked_view(request, settings)


@router.post(
    "/settings/token",
    response_model=TokenResponse,
    summary="Generate or rotate the API token (shown once)",
)
async def rotate_token(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_admin),
) -> TokenResponse:
    token = secrets.token_urlsafe(32)
    token_hash = hash_secret(token)
    await repo.set_setting(session, TOKEN_KEY, token_hash)
    await session.commit()
    request.app.state.api_token_hash = token_hash
    return TokenResponse(token=token)


@router.delete("/settings/token", summary="Remove the API token")
async def delete_token(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_admin),
) -> dict[str, str]:
    await repo.delete_setting(session, TOKEN_KEY)
    await session.commit()
    request.app.state.api_token_hash = None
    return {"status": "removed"}
