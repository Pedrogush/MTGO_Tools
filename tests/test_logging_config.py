"""Tests for logging level configuration (non-wx)."""

from __future__ import annotations

from loguru import logger

from utils.logging_config import _warmup_filter, configure_logging


class _Level:
    def __init__(self, no: int) -> None:
        self.no = no


def _record(*, warmup: bool, level_name: str) -> dict:
    return {
        "extra": {"warmup": True} if warmup else {},
        "level": _Level(logger.level(level_name).no),
    }


def test_warmup_filter_drops_info_from_warmup_context():
    assert _warmup_filter(_record(warmup=True, level_name="INFO")) is False
    assert _warmup_filter(_record(warmup=True, level_name="DEBUG")) is False


def test_warmup_filter_keeps_warnings_from_warmup_context():
    assert _warmup_filter(_record(warmup=True, level_name="WARNING")) is True
    assert _warmup_filter(_record(warmup=True, level_name="ERROR")) is True


def test_warmup_filter_passes_non_warmup_records():
    assert _warmup_filter(_record(warmup=False, level_name="INFO")) is True
    assert _warmup_filter(_record(warmup=False, level_name="DEBUG")) is True


def _captured_levels(logs_dir, monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("MTGO_LOG_LEVEL", env_value)

    configure_logging(logs_dir)
    try:
        # loguru exposes the configured sinks via the private handler registry;
        # their `levelno` reflects the threshold each sink will emit at.
        return sorted(h.levelno for h in logger._core.handlers.values())
    finally:
        logger.remove()


def test_default_level_is_info(tmp_path, monkeypatch):
    info_no = logger.level("INFO").no
    assert all(no == info_no for no in _captured_levels(tmp_path, monkeypatch, None))


def test_debug_level_via_env(tmp_path, monkeypatch):
    debug_no = logger.level("DEBUG").no
    assert all(no == debug_no for no in _captured_levels(tmp_path, monkeypatch, "DEBUG"))


def test_env_level_is_case_insensitive(tmp_path, monkeypatch):
    debug_no = logger.level("DEBUG").no
    assert all(no == debug_no for no in _captured_levels(tmp_path, monkeypatch, "debug"))
