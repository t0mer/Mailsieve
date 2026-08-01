"""HTTP Basic auth helpers for UI routes."""

from __future__ import annotations

import base64
import binascii
import secrets

from app.auth.api_key import verify_secret


def parse_basic(header: str | None) -> tuple[str, str] | None:
    """Decode a ``Basic`` Authorization header into (username, password)."""
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header[6:]).decode("utf-8")
    except (binascii.Error, ValueError):
        return None
    user, sep, password = raw.partition(":")
    if not sep:
        return None
    return user, password


def verify_basic(header: str | None, username: str, password_hash: str) -> bool:
    """Verify a Basic header against the configured username + bcrypt password hash."""
    creds = parse_basic(header)
    if creds is None:
        return False
    user, password = creds
    if not secrets.compare_digest(user, username):
        return False
    return verify_secret(password, password_hash)
