"""Logging helpers to mirror console output into a persistent log file."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger


def configure_logging(logs_dir: Path) -> Path | None:
    """
    Configure loguru to emit to stderr and a rolling file in the given logs directory.

    The log level defaults to ``INFO`` but can be lowered via the
    ``MTGO_LOG_LEVEL`` environment variable (e.g. ``DEBUG``) to surface the
    ``utils.perf.timed`` per-step timings used for cold-start profiling.

    Returns the file path in use when file logging is available, otherwise None.
    """
    level = os.environ.get("MTGO_LOG_LEVEL", "INFO").upper()
    logger.remove()
    for stream_name in ("stderr", "stdout"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            logger.add(stream, level=level, backtrace=True, diagnose=True, enqueue=True)
            break
        except TypeError:
            continue

    log_file: Path | None = None
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"mtgo_tools_{datetime.now():%Y%m%d_%H%M%S}.log"
        logger.add(
            log_file,
            level=level,
            rotation="5 MB",
            retention=5,
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )
    except Exception as exc:
        logger.warning(f"File logging disabled; unable to write to {logs_dir}: {exc}")

    return log_file
