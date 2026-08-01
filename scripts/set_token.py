#!/usr/bin/env python
"""Headless API-token generator (§3.14).

Generates a token, stores its bcrypt hash in ``app_settings``, and prints the
plaintext once to stdout. The plaintext is never logged or persisted.

Usage:
    python scripts/set_token.py
"""

from __future__ import annotations

import asyncio
import secrets

from app.auth.api_key import hash_secret
from app.config import load_settings
from app.db import repository as repo
from app.db.migrate import upgrade_to_head
from app.db.session import make_engine, make_sessionmaker, session_scope

TOKEN_KEY = "api_token_hash"  # noqa: S105 - a settings key name, not a secret


async def _write_token() -> str:
    settings = load_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    token = secrets.token_urlsafe(32)
    try:
        async with session_scope(sessionmaker) as session:
            await repo.set_setting(session, TOKEN_KEY, hash_secret(token))
    finally:
        await engine.dispose()
    return token


def main() -> None:
    # Run migrations first, at top level: Alembic drives its own event loop, so
    # it must not be invoked from inside asyncio.run() below.
    upgrade_to_head()
    token = asyncio.run(_write_token())
    # Plaintext to stdout ONLY, shown once. Never logged.
    print(token)  # noqa: T201


if __name__ == "__main__":
    main()
