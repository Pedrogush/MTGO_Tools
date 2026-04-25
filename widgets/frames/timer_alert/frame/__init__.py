"""Timer alert frame UI construction package.

The :class:`TimerAlertFrame` itself owns the window state and orchestrates the
top-to-bottom layout, while each section builder mixin (:mod:`sections`)
constructs a specific section. Re-exports :class:`ThresholdPanel` so existing
``from widgets.frames.timer_alert.frame import ThresholdPanel`` import sites
continue to work.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx
from loguru import logger

from utils.constants import (
    DARK_BG,
    PADDING_SM,
    TIMER_ALERT_FRAME_SIZE,
    TIMER_ALERT_POLL_INTERVAL_MS,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS,
    TIMER_ALERT_WATCH_INTERVAL_MS,
)
from utils.i18n import translate
from utils.mtgo_bridge_client import BridgeWatcher
from widgets.frames.timer_alert.frame.sections import SectionsBuilderMixin
from widgets.frames.timer_alert.frame.styling import StylingMixin
from widgets.frames.timer_alert.frame.threshold_panel import SOUND_OPTIONS, ThresholdPanel
from widgets.frames.timer_alert.handlers import TimerAlertHandlersMixin
from widgets.frames.timer_alert.properties import TimerAlertPropertiesMixin


class TimerAlertFrame(
    TimerAlertHandlersMixin,
    TimerAlertPropertiesMixin,
    StylingMixin,
    SectionsBuilderMixin,
    wx.Frame,
):
    """Polls MTGO challenge timers via the bridge and plays audible alerts."""

    WATCH_INTERVAL_MS = TIMER_ALERT_WATCH_INTERVAL_MS
    WATCH_RETRY_DELAY_MS = 5000
    POLL_INTERVAL_MS = TIMER_ALERT_POLL_INTERVAL_MS

    def __init__(self, parent: wx.Window | None = None, locale: str | None = None) -> None:
        style = wx.CAPTION | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.STAY_ON_TOP | wx.RESIZE_BORDER
        super().__init__(
            parent,
            title=translate(locale, "window.title.timer_alert"),
            size=TIMER_ALERT_FRAME_SIZE,
            style=style,
        )
        self._locale = locale

        self._watcher: BridgeWatcher | None = None
        self._watch_start_pending = False
        self._closed = False
        self._watch_timer = wx.Timer(self)
        self._monitor_timer = wx.Timer(self)
        self._repeat_timer = wx.Timer(self)

        self._last_snapshot: dict[str, Any] | None = None
        self.challenge_text: wx.StaticText | None = None
        self.threshold_panels: list[ThresholdPanel] = []

        self.monitor_job_active = False
        self.triggered_thresholds: set[int] = set()
        self.start_alert_sent = False
        self._current_thresholds: list[int] = []
        self._monitor_interval_ms = TIMER_ALERT_POLL_INTERVAL_MS
        self._repeat_interval_ms = TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS

        self._build_ui()

        self.Bind(wx.EVT_TIMER, self._on_watch_timer, self._watch_timer)
        self.Bind(wx.EVT_TIMER, self._on_monitor_timer, self._monitor_timer)
        self.Bind(wx.EVT_TIMER, self._on_repeat_timer, self._repeat_timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        wx.CallAfter(self._start_watch_loop)

    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        self._build_thresholds_section(panel, sizer)
        self._build_options_section(panel, sizer)
        self._build_status_section(panel, sizer)

        self._set_status("timer.configure")
        self.Bind(wx.EVT_SIZE, self._on_resize)

    def _add_threshold_panel(self) -> None:
        panel = ThresholdPanel(self.threshold_container, on_remove=self._remove_threshold_panel)
        self.threshold_panels.append(panel)
        self.threshold_container_sizer.Add(panel, 0, wx.EXPAND | wx.BOTTOM, PADDING_SM)
        self.threshold_container.Layout()
        self.threshold_container.FitInside()

    def _remove_threshold_panel(self, panel: ThresholdPanel) -> None:
        if len(self.threshold_panels) <= 1:
            self._set_status("timer.status.one_threshold_required")
            return
        self.threshold_panels.remove(panel)
        self.threshold_container_sizer.Detach(panel)
        panel.Destroy()
        self.threshold_container.Layout()
        self.threshold_container.FitInside()


def main() -> None:
    """Launch the timer alert widget as a standalone application."""
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = TimerAlertFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()


__all__ = ["SOUND_OPTIONS", "ThresholdPanel", "TimerAlertFrame", "main"]
