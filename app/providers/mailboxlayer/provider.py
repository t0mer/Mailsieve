"""mailboxlayer provider — orchestrates secret → hash → request → map (§5.1).

This is the only component that talks to the outside world. Every fragile
coupling to mailboxlayer's current shape lives under this package so a change is
a one-file fix.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from app.providers.base import ProviderHealth
from app.providers.mailboxlayer.client import UpstreamClient
from app.providers.mailboxlayer.mapping import to_schema
from app.providers.mailboxlayer.politeness import Politeness
from app.providers.mailboxlayer.proxies import ProxyPool
from app.providers.mailboxlayer.secret import SecretProvider, SecretUnavailable
from app.providers.mailboxlayer.useragents import UserAgents

if TYPE_CHECKING:
    from app.config import Settings


def _syntax_ok(email: str) -> bool:
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain


def _looks_bad_secret(raw: dict[str, Any]) -> bool:
    """Defensively detect a bad/expired-secret response (shape is not contractual)."""
    if raw.get("success") is False:
        return True
    if "error" in raw:
        return True
    return "format_valid" not in raw


class MailboxlayerProvider:
    def __init__(self, settings: Settings) -> None:
        mb = settings.mailboxlayer
        self._cfg = mb
        self._api_url = mb.base_url.rstrip("/") + mb.api_path
        self._secret = SecretProvider(mb.secret_url, mb.secret_input_name, mb.secret.ttl_minutes)
        self._proxies = ProxyPool(
            mb.proxies.source_url,
            mb.proxies.protocol,
            mb.proxies.max,
            enabled=mb.proxies.enabled,
            refresh_minutes=mb.proxies.refresh_minutes,
        )
        self._agents = UserAgents(mb.user_agents_file)
        self._politeness = Politeness(
            mb.politeness.max_concurrent, mb.politeness.min_interval_seconds
        )
        self._client = UpstreamClient(
            self._proxies,
            self._agents,
            timeout_seconds=mb.request.timeout_seconds,
            max_retries=mb.request.max_retries,
            backoff_seconds=mb.request.backoff_seconds,
            politeness=self._politeness,
        )

    def _hash_key(self, email: str, secret: str) -> str:
        # md5 is mandated by the mailboxlayer request protocol, not a security choice.
        return hashlib.md5((email.strip() + secret).encode("utf-8")).hexdigest()  # noqa: S324

    async def _request(self, email: str, secret: str) -> dict[str, Any]:
        params = {
            "secret_key": self._hash_key(email, secret),
            "email_address": email,
            "smtp": self._cfg.smtp,
        }
        return await self._client.get_json(self._api_url, params)

    async def validate(self, email: str, email_raw: str) -> dict[str, Any]:
        # Cheap local gate so obvious garbage never spends an upstream request.
        if not _syntax_ok(email):
            return to_schema({"format_valid": False, "mx_found": False}, email, email_raw)

        # The proxy pool is refreshed lazily inside the client, only on failover,
        # so the direct-first hot path pays no proxy cost.
        secret = await self._secret.get()
        raw = await self._request(email, secret)

        if _looks_bad_secret(raw) and self._cfg.secret.refresh_on_reject:
            secret = await self._secret.force_refresh()
            raw = await self._request(email, secret)  # exactly one retry, no loop

        return to_schema(raw, email, email_raw)

    async def health(self) -> ProviderHealth:
        secret_ok = False
        detail = ""
        try:
            await self._secret.get()
            secret_ok = self._secret.ok
        except SecretUnavailable as exc:
            detail = str(exc)
        proxy_count = self._proxies.count()
        # Direct-first: reachability depends only on the secret; proxies are an
        # optional failover, so proxy_count is informational.
        reachable = secret_ok
        return ProviderHealth(
            reachable=reachable,
            secret_ok=secret_ok,
            proxy_count=proxy_count,
            detail=detail or (self._secret.last_error or ""),
        )
