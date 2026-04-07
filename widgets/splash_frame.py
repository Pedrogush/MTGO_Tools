from __future__ import annotations

import time
from collections.abc import Callable

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT


class LoadingFrame(wx.Frame):
    """Lightweight splash that shows a loading message while the main UI initializes."""

    def __init__(self, min_duration: float = 0.8, max_duration: float = 1.8) -> None:
        super().__init__(
            None,
            title="Loading MTGO Deck Builder",
            style=wx.BORDER_NONE | wx.STAY_ON_TOP,
            size=(420, 120),
        )
        self._start = time.monotonic()
        self._min_duration = min_duration
        self._max_duration = max_duration
        self._ready = False
        self._finished = False
        self._on_ready: Callable[[], None] | None = None

        self.SetBackgroundColour(DARK_BG)
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_PANEL)
        outer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(outer)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 12)
        self.SetSizer(frame_sizer)

        title = wx.StaticText(panel, label="Loading MTGOTools...")
        title.SetForegroundColour(LIGHT_TEXT)
        font = title.GetFont()
        font.SetPointSize(font.GetPointSize() + 4)
        font.MakeBold()
        title.SetFont(font)
        title.Wrap(320)
        outer.AddStretchSpacer(1)
        outer.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL)
        outer.AddStretchSpacer(1)

        panel.Layout()
        self.Layout()

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_tick, self._timer)
        self._timer.Start(40)

        self.Centre(wx.BOTH)

    def set_ready(self, on_ready: Callable[[], None] | None = None) -> None:
        self._ready = True
        self._on_ready = on_ready
        self._maybe_finish()

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


__all__ = ["LoadingFrame"]
