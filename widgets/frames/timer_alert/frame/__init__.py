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
from typing import TYPE_CHECKING, Any

_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx
from loguru import logger

from utils.constants import (
    DARK_BG,
    SPACE_XS,
    TIMER_ALERT_FRAME_SIZE,
    TIMER_ALERT_POLL_INTERVAL_MS,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS,
    TIMER_ALERT_WATCH_INTERVAL_MS,
)
from utils.i18n import translate
from widgets.frames.timer_alert.frame.sections import SectionsBuilderMixin
from widgets.frames.timer_alert.frame.styling import StylingMixin
from widgets.frames.timer_alert.frame.threshold_panel import SOUND_OPTIONS, ThresholdPanel
from widgets.frames.timer_alert.handlers import TimerAlertHandlersMixin
from widgets.frames.timer_alert.properties import TimerAlertPropertiesMixin
from widgets.stylize import clamp_to_display, init_top_level_window

if TYPE_CHECKING:
    from services.mtgo_bridge_service.client import BridgeWatcher


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

    def __init__(
        self,
        parent: wx.Window | None = None,
        controller=None,
        locale: str | None = None,
    ) -> None:
        style = wx.CAPTION | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.STAY_ON_TOP | wx.RESIZE_BORDER
        super().__init__(
            parent,
            title=translate(locale, "window.title.timer_alert"),
            size=TIMER_ALERT_FRAME_SIZE,
            style=style,
        )
        init_top_level_window(self)
        self._locale = locale
        self.controller = controller

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

        # Phase 6 logged this window as wanting 438px inside a 404px client and
        # phase 8 confirmed it: the three action buttons are a wx.GridSizer of
        # equal columns (phase 4's A2), the widest of them needs 130px, and
        # 3 x 130 + gaps + margins is 438. A wx.BoxSizer row absorbs a deficit
        # silently in its last item; a GridSizer spreads it across every column,
        # so all three buttons were narrower than their labels at once and none
        # of them looked obviously wrong.
        #
        # Fixed by measurement rather than by a wider literal, because the
        # binding term is a translated string: "Start Monitoring" is
        # "Iniciar Monitoramento" in pt-BR and the checkbox above it is half
        # again as long, so any width picked from the English build is wrong in
        # the other locale by construction. TIMER_ALERT_FRAME_SIZE stays the
        # floor; the content raises it when it needs to.
        #
        # This also gives the window its first minimum size. It has always
        # carried wx.RESIZE_BORDER with no floor, so it could be dragged to
        # nothing with no feedback.
        content_min = self.ClientToWindowSize(sizer.CalcMin())
        fitted = wx.Size(
            max(TIMER_ALERT_FRAME_SIZE[0], content_min.GetWidth()),
            max(TIMER_ALERT_FRAME_SIZE[1], content_min.GetHeight()),
        )
        self.SetMinSize(fitted)
        if fitted.GetWidth() > self.GetSize().GetWidth() or (
            fitted.GetHeight() > self.GetSize().GetHeight()
        ):
            self.SetSize(fitted)
        # ...but never past the display. init_top_level_window already clamped
        # the constructor's size; this window is the one that resizes itself
        # afterwards, so it re-clamps by hand.
        clamp_to_display(self)

        self.Bind(wx.EVT_SIZE, self._on_resize)

    def _add_threshold_panel(self) -> None:
        panel = ThresholdPanel(self.threshold_container, on_remove=self._remove_threshold_panel)
        self.threshold_panels.append(panel)
        self.threshold_container_sizer.Add(panel, 0, wx.EXPAND | wx.BOTTOM, SPACE_XS)
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
    from controllers.app_controller import get_deck_selector_controller
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = TimerAlertFrame(controller=get_deck_selector_controller())
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()


__all__ = ["SOUND_OPTIONS", "ThresholdPanel", "TimerAlertFrame", "main"]
