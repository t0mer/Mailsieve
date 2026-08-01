"""Map raw mailboxlayer JSON to the Mailsieve response payload (§7).

The verdict rule lives here, in one place. ``null`` vs ``false`` is preserved
exactly; an empty-string ``did_you_mean`` becomes JSON ``null``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schemas.validation import Verdict


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_verdict(raw: dict[str, Any]) -> tuple[Verdict, str | None]:
    if raw.get("format_valid") is False:
        return "undeliverable", "invalid address format"
    if raw.get("mx_found") is False:
        return "undeliverable", "no MX record for domain"
    if raw.get("catch_all") is True or raw.get("disposable") is True:
        return "risky", "catch-all or disposable domain"
    if raw.get("smtp_check") is True:
        return "deliverable", None
    return "unknown", "insufficient signals from upstream"


def to_schema(raw: dict[str, Any], email: str, email_raw: str) -> dict[str, Any]:
    did_you_mean = raw.get("did_you_mean")
    if did_you_mean == "":
        did_you_mean = None

    verdict, reason = _derive_verdict(raw)

    return {
        "email": email,
        "email_raw": email_raw,
        "user": raw.get("user"),
        "domain": raw.get("domain"),
        "format_valid": raw.get("format_valid"),
        "mx_found": raw.get("mx_found"),
        "smtp_check": raw.get("smtp_check"),
        "catch_all": raw.get("catch_all"),
        "role": raw.get("role"),
        "disposable": raw.get("disposable"),
        "free": raw.get("free"),
        "did_you_mean": did_you_mean,
        "score": raw.get("score"),
        "verdict": verdict,
        "reason": reason,
        "provider": "mailboxlayer",
        "checked_at": _now_iso(),
        "cached": False,
        "source": "provider",
    }
