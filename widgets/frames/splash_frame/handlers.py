"""Timer callbacks and lifecycle transitions for the splash frame."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from widgets.frames.splash_frame.protocol import LoadingFrameProto

    _Base = LoadingFrameProto
else:
    _Base = object


class LoadingFrameHandlersMixin(_Base):
    """Timer and completion handlers for :class:`LoadingFrame`."""

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
