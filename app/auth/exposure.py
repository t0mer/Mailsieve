"""Guard against exposing destructive admin routes unauthenticated (§8).

Backup/restore/settings must not be reachable when both auth modes are off and
the service is bound to a non-loopback address — an open restore endpoint is a
remote database-replacement primitive.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

_LOOPBACK_NAMES = {"localhost"}


def is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def admin_exposure_ok(settings: Settings) -> bool:
    """True if admin routes may be served (auth enabled, or loopback-only bind)."""
    if settings.auth.api.enabled or settings.auth.ui.enabled:
        return True
    return is_loopback(settings.server.host)
