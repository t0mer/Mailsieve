"""Request/response models for the validation API (see §7)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["deliverable", "undeliverable", "risky", "unknown"]


class ValidateRequest(BaseModel):
    email: str = Field(..., description="Email address to validate.")


class ValidationResponse(BaseModel):
    """Mapped mailboxlayer result plus Mailsieve-derived fields.

    ``null`` vs ``false`` is preserved exactly as mailboxlayer sends it —
    ``catch_all: null`` means undetermined, not negative.
    """

    email: str
    email_raw: str
    user: str | None = None
    domain: str | None = None
    format_valid: bool | None = None
    mx_found: bool | None = None
    smtp_check: bool | None = None
    catch_all: bool | None = None
    role: bool | None = None
    disposable: bool | None = None
    free: bool | None = None
    did_you_mean: str | None = None
    score: float | None = None
    verdict: Verdict
    reason: str | None = None
    provider: str = "mailboxlayer"
    checked_at: str
    cached: bool = False
    source: str
