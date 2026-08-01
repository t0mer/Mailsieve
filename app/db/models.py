"""Append-only ORM models. Rows are never mutated; history is the product.

``validation_results`` grows only when a re-check produces a different
``result_hash``. ``verification_events`` records every check (for "last verified"
answers) without touching the results table. ``app_settings`` holds the bcrypt
hash of the API token, never plaintext.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Longest practical email length; also used for the indexed search column.
_EMAIL_LEN = 320


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class EventSource(enum.StrEnum):
    api = "api"
    ui = "ui"
    refresh = "refresh"


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(_EMAIL_LEN), index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=_utcnow
    )

    # Every read is "latest for this address": (email, created_at DESC).
    __table_args__ = (Index("ix_vr_email_created", "email", text("created_at DESC")),)


class VerificationEvent(Base):
    __tablename__ = "verification_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(_EMAIL_LEN), index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("validation_results.id"))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=_utcnow
    )
    source: Mapped[EventSource] = mapped_column(SAEnum(EventSource, name="event_source"))
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
