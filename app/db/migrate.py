"""Run Alembic migrations programmatically at startup."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command

_ROOT = Path(__file__).resolve().parents[2]


def _config() -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    return cfg


def upgrade_to_head() -> None:
    """Apply all pending migrations. Blocking — call via a thread from async code."""
    command.upgrade(_config(), "head")
