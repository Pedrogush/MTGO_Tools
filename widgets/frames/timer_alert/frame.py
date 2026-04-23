"""UI construction for the timer alert widget."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import re
from typing import Any

import wx
from loguru import logger

from utils.constants import (
    DARK_ACCENT,
    DARK_ALT,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_BASE,
    PADDING_MD,
    PADDING_SM,
    PADDING_XL,
    SUBDUED_TEXT,
    TIMER_ALERT_CHALLENGE_WRAP_WIDTH,
    TIMER_ALERT_DEFAULT_THRESHOLD_VALUE,
    TIMER_ALERT_FRAME_SIZE,
    TIMER_ALERT_POLL_INTERVAL_MAX_MS,
    TIMER_ALERT_POLL_INTERVAL_MIN_MS,
    TIMER_ALERT_POLL_INTERVAL_MS,
    TIMER_ALERT_REMOVE_BUTTON_SIZE,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_SECONDS,
    TIMER_ALERT_REPEAT_INTERVAL_MAX_SECONDS,
    TIMER_ALERT_REPEAT_INTERVAL_MIN_SECONDS,
    TIMER_ALERT_SCROLL_RATE_Y,
    TIMER_ALERT_STATUS_MIN_HEIGHT,
    TIMER_ALERT_THRESHOLD_INPUT_SIZE,
    TIMER_ALERT_WATCH_INTERVAL_MS,
)
from utils.i18n import translate
from utils.mtgo_bridge_client import BridgeWatcher
from widgets.frames.timer_alert.handlers import TimerAlertHandlersMixin
from widgets.frames.timer_alert.properties import TimerAlertPropertiesMixin

# Built-in Windows sounds (always available)
SOUND_OPTIONS = {
    "Beep": "SystemAsterisk",
    "Alert": "SystemExclamation",
    "Warning": "SystemHand",
    "Question": "SystemQuestion",
    "Default": "SystemDefault",
}


class ThresholdPanel(wx.Panel):
    """Individual threshold entry with MM:SS format."""

    def __init__(self, parent: wx.Window, on_remove: callable = None) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(DARK_BG)
        self.on_remove_callback = on_remove

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(sizer)

        # MM:SS input
        self.time_input = wx.TextCtrl(
            self, size=TIMER_ALERT_THRESHOLD_INPUT_SIZE, value=TIMER_ALERT_DEFAULT_THRESHOLD_VALUE
        )
        self._stylize_entry(self.time_input)
        sizer.Add(self.time_input, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_BASE)

        # Remove button
        self.remove_btn = wx.Button(self, label="✕", size=TIMER_ALERT_REMOVE_BUTTON_SIZE)
        self._stylize_remove_button(self.remove_btn)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove)
        sizer.Add(self.remove_btn, 0, wx.ALIGN_CENTER_VERTICAL)

    def _stylize_entry(self, entry: wx.TextCtrl) -> None:
        entry.SetBackgroundColour(DARK_ALT)
        entry.SetForegroundColour(LIGHT_TEXT)

    def _stylize_remove_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(wx.Colour(139, 35, 35))
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _on_remove(self, _event: wx.CommandEvent) -> None:
        if self.on_remove_callback:
            self.on_remove_callback(self)

    def get_seconds(self) -> int | None:
        value = self.time_input.GetValue().strip()
        match = re.match(r"^(\d+):(\d{2})$", value)
        if not match:
            return None
        minutes, seconds = match.groups()
        return int(minutes) * 60 + int(seconds)

    def set_enabled(self, enabled: bool) -> None:
        self.time_input.Enable(enabled)
        self.remove_btn.Enable(enabled)


class TimerAlertFrame(TimerAlertHandlersMixin, TimerAlertPropertiesMixin, wx.Frame):
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

    # ------------------------------------------------------------------ UI build
    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Thresholds section
        threshold_box = wx.StaticBox(panel, label=self._t("timer.section.thresholds"))
        threshold_box.SetForegroundColour(LIGHT_TEXT)
        threshold_box.SetBackgroundColour(DARK_PANEL)
        threshold_sizer = wx.StaticBoxSizer(threshold_box, wx.VERTICAL)
        box_parent = threshold_sizer.GetStaticBox()

        instructions = wx.StaticText(
            box_parent, label="Enter time in MM:SS format (e.g., 05:00 for 5 minutes)"
        )
        instructions.SetForegroundColour(SUBDUED_TEXT)
        threshold_sizer.Add(instructions, 0, wx.ALL, PADDING_SM)

        # Scrollable threshold container
        self.threshold_container = wx.ScrolledWindow(box_parent, style=wx.VSCROLL)
        self.threshold_container.SetBackgroundColour(DARK_BG)
        self.threshold_container.SetScrollRate(0, TIMER_ALERT_SCROLL_RATE_Y)
        self.threshold_container_sizer = wx.BoxSizer(wx.VERTICAL)
        self.threshold_container.SetSizer(self.threshold_container_sizer)
        threshold_sizer.Add(self.threshold_container, 1, wx.EXPAND | wx.ALL, PADDING_SM)

        self._add_threshold_panel()

        add_btn = wx.Button(box_parent, label="+ Add Another Threshold")
        self._stylize_secondary_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._add_threshold_panel())
        threshold_sizer.Add(add_btn, 0, wx.ALL, PADDING_SM)

        sizer.Add(threshold_sizer, 1, wx.ALL | wx.EXPAND, PADDING_XL)

        # Options section
        options_grid = wx.FlexGridSizer(cols=2, hgap=PADDING_BASE, vgap=PADDING_BASE)
        options_grid.AddGrowableCol(1, 1)

        options_grid.Add(
            self._static_text(panel, self._t("timer.label.sound")), 0, wx.ALIGN_CENTER_VERTICAL
        )
        self.sound_choice = wx.Choice(panel, choices=list(SOUND_OPTIONS.keys()))
        self._stylize_choice(self.sound_choice)
        self.sound_choice.SetSelection(0)
        options_grid.Add(self.sound_choice, 0, wx.EXPAND)

        options_grid.Add(
            self._static_text(panel, self._t("timer.label.check_interval")),
            0,
            wx.ALIGN_CENTER_VERTICAL,
        )
        self.poll_interval_ctrl = wx.SpinCtrl(
            panel,
            min=TIMER_ALERT_POLL_INTERVAL_MIN_MS,
            max=TIMER_ALERT_POLL_INTERVAL_MAX_MS,
            initial=TIMER_ALERT_POLL_INTERVAL_MS,
        )
        self._stylize_spin(self.poll_interval_ctrl)
        options_grid.Add(self.poll_interval_ctrl, 0, wx.EXPAND)

        options_grid.Add(
            self._static_text(panel, self._t("timer.label.repeat_interval")),
            0,
            wx.ALIGN_CENTER_VERTICAL,
        )
        self.repeat_interval_ctrl = wx.SpinCtrl(
            panel,
            min=TIMER_ALERT_REPEAT_INTERVAL_MIN_SECONDS,
            max=TIMER_ALERT_REPEAT_INTERVAL_MAX_SECONDS,
            initial=TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_SECONDS,
        )
        self._stylize_spin(self.repeat_interval_ctrl)
        options_grid.Add(self.repeat_interval_ctrl, 0, wx.EXPAND)

        sizer.Add(options_grid, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, PADDING_XL)

        # Checkboxes
        self.start_alert_checkbox = wx.CheckBox(panel, label=self._t("timer.check.start_alert"))
        self.start_alert_checkbox.SetValue(True)
        self.start_alert_checkbox.SetForegroundColour(LIGHT_TEXT)
        self.start_alert_checkbox.SetBackgroundColour(DARK_BG)
        sizer.Add(self.start_alert_checkbox, 0, wx.LEFT | wx.RIGHT | wx.TOP, PADDING_XL)

        self.repeat_alarm_checkbox = wx.CheckBox(panel, label=self._t("timer.check.repeat_alarm"))
        self.repeat_alarm_checkbox.SetValue(False)
        self.repeat_alarm_checkbox.SetForegroundColour(LIGHT_TEXT)
        self.repeat_alarm_checkbox.SetBackgroundColour(DARK_BG)
        sizer.Add(self.repeat_alarm_checkbox, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_XL)

        # Control buttons
        button_row = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_row, 0, wx.ALL | wx.EXPAND, PADDING_XL)

        start_btn = wx.Button(panel, label=self._t("timer.btn.start"))
        self._stylize_primary_button(start_btn)
        start_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.start_monitoring())
        button_row.Add(start_btn, 0, wx.RIGHT, PADDING_MD)

        stop_btn = wx.Button(panel, label=self._t("timer.btn.stop"))
        self._stylize_secondary_button(stop_btn)
        stop_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.stop_monitoring())
        button_row.Add(stop_btn, 0, wx.RIGHT, PADDING_MD)

        test_btn = wx.Button(panel, label=self._t("timer.btn.test"))
        self._stylize_secondary_button(test_btn)
        test_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.test_alert())
        button_row.Add(test_btn, 0)

        # Status display
        self.status_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.BORDER_NONE,
        )
        self.status_text.SetMinSize((-1, TIMER_ALERT_STATUS_MIN_HEIGHT))
        self.status_text.SetBackgroundColour(DARK_ALT)
        self.status_text.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.status_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, PADDING_XL)

        # Challenge timer display
        challenge_box = wx.StaticBox(panel, label=self._t("timer.section.challenge"))
        challenge_box.SetForegroundColour(LIGHT_TEXT)
        challenge_box.SetBackgroundColour(DARK_PANEL)
        challenge_sizer = wx.StaticBoxSizer(challenge_box, wx.VERTICAL)
        self.challenge_text = wx.StaticText(challenge_box, label=self._t("timer.no_challenge"))
        self.challenge_text.SetForegroundColour(LIGHT_TEXT)
        self.challenge_text.SetBackgroundColour(DARK_PANEL)
        self.challenge_text.Wrap(TIMER_ALERT_CHALLENGE_WRAP_WIDTH)
        challenge_sizer.Add(self.challenge_text, 0, wx.ALL | wx.EXPAND, PADDING_BASE)
        sizer.Add(challenge_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, PADDING_XL)

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

    def _static_text(self, parent: wx.Window, label: str) -> wx.StaticText:
        text = wx.StaticText(parent, label=label)
        text.SetForegroundColour(LIGHT_TEXT)
        text.SetBackgroundColour(DARK_BG)
        return text

    def _stylize_choice(self, choice: wx.Choice) -> None:
        choice.SetBackgroundColour(DARK_ALT)
        choice.SetForegroundColour(LIGHT_TEXT)

    def _stylize_spin(self, ctrl: wx.SpinCtrl) -> None:
        ctrl.SetBackgroundColour(DARK_ALT)
        ctrl.SetForegroundColour(LIGHT_TEXT)

    def _stylize_primary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_ACCENT)
        button.SetForegroundColour(wx.Colour(12, 14, 18))
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)


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
