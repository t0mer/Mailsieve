"""API-token hashing and header extraction.

The token is stored bcrypt-hashed in ``app_settings`` (never plaintext) and shown
once on generation. Verification is constant-time via bcrypt.
"""

from __future__ import annotations

from collections.abc import Mapping

import bcrypt


def hash_secret(secret: str) -> str:
    """bcrypt-hash a token or password for storage."""
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_secret(presented: str, stored_hash: str) -> bool:
    """Constant-time verify a presented secret against a stored bcrypt hash."""
    if not presented or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(presented.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False


def extract_api_token(headers: Mapping[str, str]) -> str | None:
    """Read a token from ``Authorization: Bearer`` or ``X-API-Key``."""
    auth = headers.get("Authorization") or headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    xkey = headers.get("X-API-Key") or headers.get("x-api-key")
    if xkey:
        return xkey.strip() or None
    return None
