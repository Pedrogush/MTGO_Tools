"""Tests for logging level configuration (non-wx)."""

from __future__ import annotations

import re
from pathlib import Path

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


def test_warmup_filter_drops_all_warmup_records():
    # Every level from the warm-up context is dropped, including errors —
    # the warmer summarises failures itself.
    for level_name in ("DEBUG", "INFO", "WARNING", "ERROR"):
        assert _warmup_filter(_record(warmup=True, level_name=level_name)) is False


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


def test_returns_log_file_path_under_logs_dir(tmp_path, monkeypatch):
    # A writable logs_dir yields a timestamped Path under that dir, and the
    # directory is created so the file sink can be written to.
    monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)
    try:
        log_file = configure_logging(tmp_path)
    finally:
        logger.remove()

    assert isinstance(log_file, Path)
    assert log_file.parent == tmp_path
    assert re.fullmatch(r"mtgo_tools_\d{8}_\d{6}\.log", log_file.name)
    assert tmp_path.is_dir()


def test_file_logging_failure_returns_none_but_keeps_stream_sink(tmp_path, monkeypatch):
    # When the logs_dir cannot be created/written, file logging is disabled:
    # configure_logging returns None but the stderr/stdout sink(s) survive so
    # console logging still works.
    monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)

    def _boom(*_args, **_kwargs):
        raise OSError("logs dir is not writable")

    monkeypatch.setattr(Path, "mkdir", _boom)
    try:
        log_file = configure_logging(tmp_path)
        assert log_file is None
        # The stream sink was registered before the file sink failed.
        assert len(logger._core.handlers) >= 1
    finally:
        logger.remove()
