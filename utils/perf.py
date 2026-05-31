from __future__ import annotations

import functools
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

from loguru import logger

P = ParamSpec("P")
R = TypeVar("R")


def timed(func: Callable[P, R]) -> Callable[P, R]:
    """Log execution time of *func* at DEBUG level.

    Overhead per call: two ``time.perf_counter()`` syscalls plus one
    ``logger.debug`` guard check (~80–150 ns total). Suitable for methods
    that are called at most a few times per user action; do NOT apply to
    sub-millisecond callbacks firing at 60 FPS.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        t0 = time.perf_counter()
        result = func(*args, **kwargs)
        logger.debug("{} took {:.4f}s", func.__qualname__, time.perf_counter() - t0)
        return result

    return wrapper


@contextmanager
def perf_phase(name: str, *, level: str = "INFO") -> Iterator[None]:
    """Time a code segment and emit a single ``PERF | <ms> | <name>`` log line.

    Unlike :func:`timed` (DEBUG, whole-function), this is meant for ad-hoc
    profiling of a *named segment* inside a hot user-action path — e.g. each
    stage of the click-to-rendered-deck flow — at INFO so the breakdown is
    visible without enabling DEBUG. The fixed ``PERF |`` prefix and right-
    aligned millisecond column make the lines greppable and easy to eyeball::

        PERF |    12.3 ms | analyze_deck
        PERF |   418.7 ms | main_table.set_cards

    Overhead is two ``perf_counter`` reads plus one log call per phase, so use
    it for segments measured in milliseconds, not 60 FPS callbacks.
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.log(level, "PERF | {:>7.1f} ms | {}", (time.perf_counter() - t0) * 1000.0, name)
