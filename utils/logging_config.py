"""Logging helpers to mirror console output into a persistent log file."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from utils.console import force_utf8_console


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


# The persistent file always captures at the lowest level so an installed
# build keeps a full history of events — invaluable for diagnosing user-only
# issues (e.g. the cold-start image 429 storm) after the fact, since the
# windowed build has no console to watch. The console sink stays at the
# ``MTGO_LOG_LEVEL`` (default INFO) so dev runs aren't drowned in TRACE noise.
FILE_LOG_LEVEL = "TRACE"


def configure_logging(logs_dir: Path) -> Path | None:
    """
    Configure loguru to emit to stderr and a rolling file in the given logs directory.

    The **console** sink level defaults to ``INFO`` and can be changed via the
    ``MTGO_LOG_LEVEL`` environment variable. The **file** sink always records at
    ``TRACE`` (:data:`FILE_LOG_LEVEL`) — including the background warm-up traffic
    that is filtered off the console — so the installed build retains a complete
    event history for support and post-mortem debugging.

    Returns the file path in use when file logging is available, otherwise None.
    """
    # Before any sink is attached: the console sink below is a *stream* sink, so
    # a redirected stdout/stderr carries the locale encoding (cp1252 on this
    # machine) and any log line holding a character outside it raises inside the
    # sink. Card names alone are enough -- see utils/console.py.
    force_utf8_console()
    console_level = os.environ.get("MTGO_LOG_LEVEL", "INFO").upper()
    logger.remove()
    for stream_name in ("stderr", "stdout"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            logger.add(
                stream,
                level=console_level,
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
            level=FILE_LOG_LEVEL,
            rotation="10 MB",
            retention=10,
            backtrace=True,
            diagnose=True,
            enqueue=True,
            # No _warmup_filter here: the file keeps the full history, warm-up
            # included, which is exactly the traffic needed to debug the image
            # prefetch/warm pipeline in an installed build.
        )
    except Exception as exc:
        logger.warning(f"File logging disabled; unable to write to {logs_dir}: {exc}")

    return log_file
