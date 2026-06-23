"""Tests for logging level configuration (non-wx)."""

from __future__ import annotations

import re
import sys
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


def _is_stream_sink(handler) -> bool:
    # loguru names stream sinks after the stream repr (e.g. ``<stderr>``);
    # file sinks are named after their quoted path.
    return handler._name.startswith("<")


def test_file_logging_failure_returns_none_but_keeps_stream_sink(tmp_path, monkeypatch):
    # When the logs_dir cannot be created/written, file logging is disabled:
    # configure_logging returns None but the stream sink survives so console
    # logging still works, and a warning explaining the failure is emitted.
    monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)
    info_no = logger.level("INFO").no

    def _boom(*_args, **_kwargs):
        raise OSError("logs dir is not writable")

    monkeypatch.setattr(Path, "mkdir", _boom)

    # Capture the warning emitted on file-logging failure. configure_logging
    # calls logger.remove() up front, so a sink added beforehand would be torn
    # down; recording logger.warning directly survives that reset.
    warnings: list[str] = []
    real_warning = logger.warning
    monkeypatch.setattr(logger, "warning", lambda msg, *a, **k: warnings.append(msg))

    try:
        log_file = configure_logging(tmp_path)
        assert log_file is None

        handlers = list(logger._core.handlers.values())
        # Exactly one stream sink survives and no file sink was registered.
        assert all(_is_stream_sink(h) for h in handlers)
        assert len(handlers) == 1
        # The surviving sink emits at the configured (default INFO) level.
        assert handlers[0].levelno == info_no
    finally:
        monkeypatch.setattr(logger, "warning", real_warning)
        logger.remove()

    # The failure is surfaced as a warning naming the directory and the error.
    assert len(warnings) == 1
    assert str(tmp_path) in warnings[0]
    assert "logs dir is not writable" in warnings[0]


def test_uses_stdout_when_stderr_unavailable(tmp_path, monkeypatch):
    # Frozen/windowed builds can have ``sys.stderr is None``; the stream-
    # selection loop must fall through to stdout rather than ending up with no
    # console sink at all.
    monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)
    monkeypatch.setattr(sys, "stderr", None)
    try:
        configure_logging(tmp_path)
        stream_sinks = [h for h in logger._core.handlers.values() if _is_stream_sink(h)]
        assert len(stream_sinks) == 1
        # The surviving console sink writes to stdout, the fallback stream.
        # (Asserting the stream identity rather than the sink name keeps this
        # robust under pytest's stdout capturing, which renames the stream.)
        assert stream_sinks[0]._sink._stream is sys.stdout
    finally:
        logger.remove()


def test_falls_back_to_stdout_when_stderr_sink_raises_typeerror(tmp_path, monkeypatch):
    # ``sys.stderr`` can be present but unusable as a loguru sink (e.g. a
    # frozen/windowed build whose stderr lacks a real ``write``), in which case
    # ``logger.add`` raises TypeError. The stream-selection loop must catch that
    # and fall through to stdout rather than leaving no console sink.
    monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)

    real_add = logger.add

    def _add(sink, *args, **kwargs):
        if sink is sys.stderr:
            raise TypeError("cannot use stderr as a sink")
        return real_add(sink, *args, **kwargs)

    monkeypatch.setattr(logger, "add", _add)
    try:
        configure_logging(tmp_path)
        stream_sinks = [h for h in logger._core.handlers.values() if _is_stream_sink(h)]
        assert len(stream_sinks) == 1
        assert stream_sinks[0]._sink._stream is sys.stdout
    finally:
        logger.remove()


def test_file_sink_writes_non_warmup_records_but_drops_warmup(tmp_path, monkeypatch):
    # The happy-path file sink must actually persist ordinary records while the
    # warm-up filter keeps the high-volume warm-up records out of the file.
    monkeypatch.delenv("MTGO_LOG_LEVEL", raising=False)
    try:
        log_file = configure_logging(tmp_path)
        assert log_file is not None

        logger.info("ordinary-record-marker")
        with logger.contextualize(warmup=True):
            logger.info("warmup-record-marker")
    finally:
        # Removing the sinks flushes and closes the enqueued file handler.
        logger.remove()

    contents = log_file.read_text(encoding="utf-8")
    assert "ordinary-record-marker" in contents
    assert "warmup-record-marker" not in contents
