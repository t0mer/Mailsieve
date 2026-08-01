"""Provider protocol. mailboxlayer is the only implementation in this build."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ProviderHealth:
    """Upstream reachability snapshot surfaced by ``/api/v1/health``."""

    reachable: bool
    secret_ok: bool
    proxy_count: int
    detail: str = ""


@runtime_checkable
class Provider(Protocol):
    async def validate(self, email: str, email_raw: str) -> dict[str, Any]:
        """Validate ``email`` upstream and return the mapped result payload."""
        ...

    async def health(self) -> ProviderHealth:
        """Report upstream reachability without raising."""
        ...
