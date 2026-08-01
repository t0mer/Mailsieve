import json

from loguru import logger

from app.config import LoggingCfg
from app.logging import bind_request_id, setup_logging


def test_json_logging_emits_parseable_json():
    lines: list[str] = []
    setup_logging(LoggingCfg(json=True, level="INFO"), sink=lines.append)
    logger.info("hello")
    rec = json.loads(lines[-1])
    assert rec["record"]["message"] == "hello"


def test_level_filtering_drops_below_threshold():
    lines: list[str] = []
    setup_logging(LoggingCfg(level="WARNING", json=False), sink=lines.append)
    logger.info("shh")
    logger.warning("boom")
    text = "".join(lines)
    assert "boom" in text
    assert "shh" not in text


def test_bind_request_id_attaches_to_record():
    lines: list[str] = []
    setup_logging(LoggingCfg(json=True, level="INFO"), sink=lines.append)
    with bind_request_id("req-123"):
        logger.info("x")
    rec = json.loads(lines[-1])
    assert rec["record"]["extra"]["request_id"] == "req-123"
