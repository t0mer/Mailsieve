"""Application factory, lifespan singletons, and SPA fallback."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import routes_admin, routes_history, routes_settings, routes_validate
from app.api.deps import require_admin  # noqa: F401 - re-exported for tests/overrides
from app.api.ratelimit import RateLimiter
from app.auth.exposure import admin_exposure_ok
from app.cache.redis_cache import Cache
from app.config import Settings, load_settings
from app.db import repository as repo
from app.db.migrate import upgrade_to_head
from app.db.session import make_engine, make_sessionmaker
from app.logging import setup_logging
from app.providers.mailboxlayer.provider import MailboxlayerProvider
from app.services.backup_service import BackupService
from app.services.history_service import HistoryService
from app.services.validation_service import ValidationService


def _resolve_version() -> str:
    # The Docker workflow injects the released image version (YYYY.M.PATCH) via
    # MAILSIEVE_VERSION; fall back to the installed package metadata otherwise.
    env_version = os.environ.get("MAILSIEVE_VERSION")
    if env_version and env_version != "dev":
        return env_version
    try:
        return version("mailsieve")
    except PackageNotFoundError:  # pragma: no cover - source checkout without install
        return "2026.8.0"


__version__ = _resolve_version()

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_RATE_LIMIT_PER_MIN = 60


async def _load_persisted(app: FastAPI) -> None:
    async with app.state.sessionmaker() as s:
        token_hash = await repo.get_setting(s, routes_settings.TOKEN_KEY)
        ttl = await repo.get_setting(s, routes_settings.TTL_KEY)
    app.state.api_token_hash = token_hash
    if ttl is not None:
        app.state.validation.set_ttl_days(int(ttl))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    setup_logging(settings.logging)

    if not admin_exposure_ok(settings):
        logger.warning(
            "backup/restore/settings are reachable unauthenticated on a non-loopback "
            "bind ({}); enable auth or bind to loopback",
            settings.server.host,
        )

    await asyncio.to_thread(upgrade_to_head)

    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    cache = Cache(settings.redis)
    provider = MailboxlayerProvider(settings)

    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.cache = cache
    app.state.provider = provider
    app.state.validation = ValidationService(
        sessionmaker, cache, provider, settings.validation.ttl_days
    )
    app.state.history = HistoryService(sessionmaker)
    app.state.backup = BackupService(
        sessionmaker,
        directory=settings.backup.directory,
        max_upload_mb=settings.backup.max_upload_mb,
        backend=settings.database.type,
    )
    app.state.rate_limiter = RateLimiter(_RATE_LIMIT_PER_MIN)
    await _load_persisted(app)

    logger.info("Mailsieve {} started", __version__)
    try:
        yield
    finally:
        await cache.close()
        await engine.dispose()


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    index = static_dir / "index.html"

    # Sync route: FastAPI runs it in a threadpool, so the blocking filesystem
    # checks below don't stall the event loop.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> Any:
        # Never let the SPA fallback shadow the API or docs: an unmatched /api/*
        # path must be a JSON 404, not index.html.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (static_dir / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(static_dir.resolve())
        ):
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"detail": "UI not built"}, status_code=404)


def create_app(settings: Settings | None = None, *, static_dir: Path | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(
        title="Mailsieve",
        version=__version__,
        description="Self-hosted email validation over the mailboxlayer endpoint.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.include_router(routes_validate.router)
    app.include_router(routes_history.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_admin.router)

    _mount_spa(app, static_dir or _STATIC_DIR)
    return app


app = create_app()
