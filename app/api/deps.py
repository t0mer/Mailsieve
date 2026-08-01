"""Dependency injection: app.state singletons + auth/rate-limit gates."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, cast

from fastapi import Depends, HTTPException, Request, status

from app.auth.api_key import extract_api_token, verify_secret
from app.auth.basic import verify_basic
from app.auth.exposure import admin_exposure_ok

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.cache.redis_cache import Cache
    from app.config import Settings
    from app.providers.base import Provider
    from app.services.backup_service import BackupService
    from app.services.history_service import HistoryService
    from app.services.validation_service import ValidationService


def get_settings_dep(request: Request) -> Settings:
    return cast("Settings", request.app.state.settings)


def get_cache(request: Request) -> Cache:
    return cast("Cache", request.app.state.cache)


def get_provider(request: Request) -> Provider:
    return cast("Provider", request.app.state.provider)


def get_validation_service(request: Request) -> ValidationService:
    return cast("ValidationService", request.app.state.validation)


def get_history_service(request: Request) -> HistoryService:
    return cast("HistoryService", request.app.state.history)


def get_backup_service(request: Request) -> BackupService:
    return cast("BackupService", request.app.state.backup)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    maker = request.app.state.sessionmaker
    async with maker() as session:
        yield session


# --- auth gates -------------------------------------------------------------- #
def _valid_api_token(request: Request) -> bool:
    token = extract_api_token(request.headers)
    stored = getattr(request.app.state, "api_token_hash", None)
    return bool(token and stored and verify_secret(token, stored))


def _valid_ui_basic(request: Request, settings: Settings) -> bool:
    return verify_basic(
        request.headers.get("Authorization"),
        settings.auth.ui.username,
        settings.auth.ui.password,
    )


def require_api(request: Request, settings: Settings = Depends(get_settings_dep)) -> str:
    """Gate for API routes. Open when api auth is disabled."""
    if not settings.auth.api.enabled:
        return "open"
    if _valid_api_token(request):
        return "api"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing API token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(request: Request, settings: Settings = Depends(get_settings_dep)) -> str:
    """Gate for backup/restore/settings. Refuses when unsafely exposed (§8)."""
    if not admin_exposure_ok(settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin routes are disabled: enable auth or bind to loopback",
        )
    if settings.auth.api.enabled or settings.auth.ui.enabled:
        if settings.auth.api.enabled and _valid_api_token(request):
            return "api"
        if settings.auth.ui.enabled and _valid_ui_basic(request, settings):
            return "ui"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "open"


def rate_limit_validate(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> None:
    limiter = request.app.state.rate_limiter
    key = extract_api_token(request.headers) or (
        request.client.host if request.client else "anon"
    )
    if not limiter.check(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )
