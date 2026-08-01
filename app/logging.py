"""Loguru-based logging setup with optional JSON output and request-id binding."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TextIO

from loguru import logger

if TYPE_CHECKING:
    from app.config import LoggingCfg

_TEXT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[request_id]}</cyan> | "
    "<level>{message}</level>"
)


def setup_logging(cfg: LoggingCfg, sink: Callable[[str], Any] | TextIO | None = None) -> None:
    """Configure the global loguru logger.

    ``sink`` defaults to stderr; tests pass a callable to capture output. When
    ``cfg.json_logs`` is set, records are serialized as JSON lines.
    """
    logger.remove()
    logger.configure(extra={"request_id": "-"})
    logger.add(
        sink if sink is not None else sys.stderr,
        level=cfg.level,
        serialize=cfg.json_logs,
        format=_TEXT_FORMAT,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )


@contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    """Bind ``request_id`` to every log record emitted within the context."""
    with logger.contextualize(request_id=request_id):
        yield
