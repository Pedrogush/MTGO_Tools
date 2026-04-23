"""UI construction for the loading splash frame."""

from __future__ import annotations

import time
from collections.abc import Callable

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT
from widgets.frames.splash_frame.handlers import LoadingFrameHandlersMixin
from widgets.frames.splash_frame.properties import LoadingFramePropertiesMixin


class LoadingFrame(LoadingFrameHandlersMixin, LoadingFramePropertiesMixin, wx.Frame):
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

        self._build_ui()

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_tick, self._timer)
        self._timer.Start(40)

        self.Centre(wx.BOTH)

    def _build_ui(self) -> None:
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
