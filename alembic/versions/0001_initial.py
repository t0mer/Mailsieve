"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_results_email", "validation_results", ["email"])
    op.create_index(
        "ix_validation_results_result_hash", "validation_results", ["result_hash"]
    )
    op.create_index(
        "ix_validation_results_created_at", "validation_results", ["created_at"]
    )
    op.create_index("ix_vr_email_created", "validation_results", ["email", "created_at"])

    op.create_table(
        "verification_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum("api", "ui", "refresh", name="event_source"),
            nullable=False,
        ),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["validation_results.id"]),
    )
    op.create_index("ix_verification_events_email", "verification_events", ["email"])
    op.create_index(
        "ix_verification_events_checked_at", "verification_events", ["checked_at"]
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_verification_events_checked_at", table_name="verification_events")
    op.drop_index("ix_verification_events_email", table_name="verification_events")
    op.drop_table("verification_events")
    op.drop_index("ix_vr_email_created", table_name="validation_results")
    op.drop_index("ix_validation_results_created_at", table_name="validation_results")
    op.drop_index("ix_validation_results_result_hash", table_name="validation_results")
    op.drop_index("ix_validation_results_email", table_name="validation_results")
    op.drop_table("validation_results")
    sa.Enum(name="event_source").drop(op.get_bind(), checkfirst=True)
