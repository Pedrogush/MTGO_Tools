"""Perf instrumentation for the card-view mouse-wheel scroll path.

A mouse-wheel notch travels ``_on_wheel`` → :func:`scroll_by_wheel` →
``window.Scroll`` (which invalidates) → ``_on_paint``. To tell whether the
*rendered* view keeps up with the *input*, we need timestamps from both ends of
that path: when each notch moved the scroll origin, and when each paint actually
put pixels on screen at a given origin.

This module records exactly that into a small per-window ring buffer. It is
**off by default** — the record hooks are no-ops unless a recorder has been
attached to the window via :func:`enable`, so the production hot path pays only
a single ``getattr`` returning ``None``. The automation harness flips it on for
a measured burst, reads the events back, and computes input→frame latency from
the two event streams (see ``automation/server/scroll_perf.py`` and
``tests/test_card_view_wheel_scroll_latency.py``).
"""

from __future__ import annotations

import time

from loguru import logger

# Stashed on the wx.ScrolledWindow instance. Absent == instrumentation disabled.
_ATTR = "_scroll_perf"

# Cap the buffer so a forgotten-enabled recorder can't grow without bound.
_MAX_EVENTS = 4096


class _Recorder:
    """Per-window ring buffer of ``(kind, t_ms, x, y, dur_ms)`` scroll events."""

    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events: list[tuple[str, float, int, int, float]] = []

    def add(self, kind: str, x: int, y: int, dur_ms: float = 0.0) -> None:
        if len(self.events) >= _MAX_EVENTS:
            # Drop the oldest half in one slice rather than popping per-append.
            del self.events[: _MAX_EVENTS // 2]
        self.events.append((kind, time.perf_counter() * 1000.0, x, y, dur_ms))


def enable(window: object) -> None:
    """Attach a fresh recorder to ``window`` (idempotent reset)."""
    setattr(window, _ATTR, _Recorder())


def disable(window: object) -> None:
    """Detach the recorder so the hooks go back to zero-overhead no-ops."""
    if hasattr(window, _ATTR):
        delattr(window, _ATTR)


def reset(window: object) -> None:
    """Clear recorded events but keep recording enabled."""
    recorder = getattr(window, _ATTR, None)
    if recorder is not None:
        recorder.events.clear()


def record_input(window: object, x: int, y: int) -> None:
    """Note that a wheel notch moved the scroll origin to ``(x, y)``."""
    recorder = getattr(window, _ATTR, None)
    if recorder is not None:
        recorder.add("input", x, y)
        logger.debug("PERF | scroll input -> ({}, {})", x, y)


def record_paint(window: object, x: int, y: int, dur_ms: float = 0.0) -> None:
    """Note that a paint rendered the view at ``(x, y)`` taking ``dur_ms``."""
    recorder = getattr(window, _ATTR, None)
    if recorder is not None:
        recorder.add("paint", x, y, dur_ms)
        logger.debug("PERF | scroll paint  @ ({}, {}) in {:.1f}ms", x, y, dur_ms)


def snapshot(window: object) -> list[dict[str, float]]:
    """Return the recorded events as JSON-friendly dicts (empty if disabled)."""
    recorder = getattr(window, _ATTR, None)
    if recorder is None:
        return []
    return [
        {"kind": kind, "t_ms": t_ms, "x": x, "y": y, "dur_ms": dur_ms}
        for (kind, t_ms, x, y, dur_ms) in recorder.events
    ]
