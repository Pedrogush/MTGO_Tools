"""Timer callbacks and lifecycle transitions for the splash frame."""

from __future__ import annotations

import time
from collections.abc import Callable

import wx


class LoadingFrameHandlersMixin:
    """Timer and completion handlers for :class:`LoadingFrame`."""

    _start: float
    _min_duration: float
    _max_duration: float
    _ready: bool
    _finished: bool
    _on_ready: Callable[[], None] | None
    _timer: wx.Timer

    def _on_tick(self, _event: wx.TimerEvent) -> None:
        self._maybe_finish()

    def _maybe_finish(self) -> None:
        if self._finished:
            return
        elapsed = time.monotonic() - self._start
        if (self._ready and elapsed >= self._min_duration) or elapsed >= self._max_duration:
            self._finished = True
            self._timer.Stop()
            callback = self._on_ready
            self.Hide()
            self.Destroy()
            if callback:
                wx.CallAfter(callback)
