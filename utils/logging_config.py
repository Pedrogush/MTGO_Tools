"""Logging helpers to mirror console output into a persistent log file."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger


def _warmup_filter(record) -> bool:
    """Drop records emitted by the background cache warm-up.

    The warm-up drives a high volume of per-archetype scrapes and per-deck
    downloads, each of which logs from ``deck_operations`` and the scrapers
    (including expected per-deck parse failures for decks MTGGoldfish can't
    render). Those calls run inside ``logger.contextualize(warmup=True)``, so we
    drop the resulting records from every sink — including their errors, which
    are best-effort and already summarised by the warmer's own failed count —
    and let the warmer emit its own concise, clearly-labelled progress lines.
    """
    return not record["extra"].get("warmup")


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
            logger.add(
                stream,
                level=level,
                backtrace=True,
                diagnose=True,
                enqueue=True,
                filter=_warmup_filter,
            )
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
            filter=_warmup_filter,
        )
    except Exception as exc:
        logger.warning(f"File logging disabled; unable to write to {logs_dir}: {exc}")

    return log_file
