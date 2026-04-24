"""Builders for each section of the timer alert frame: thresholds, options, status."""

from __future__ import annotations

import wx

from utils.constants import (
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
    TIMER_ALERT_POLL_INTERVAL_MAX_MS,
    TIMER_ALERT_POLL_INTERVAL_MIN_MS,
    TIMER_ALERT_POLL_INTERVAL_MS,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_SECONDS,
    TIMER_ALERT_REPEAT_INTERVAL_MAX_SECONDS,
    TIMER_ALERT_REPEAT_INTERVAL_MIN_SECONDS,
    TIMER_ALERT_SCROLL_RATE_Y,
    TIMER_ALERT_STATUS_MIN_HEIGHT,
)
from widgets.frames.timer_alert.frame.threshold_panel import SOUND_OPTIONS, ThresholdPanel


class SectionsBuilderMixin:
    """Builds the three top-level sections of the timer alert frame.

    Kept as a mixin (no ``__init__``) so :class:`TimerAlertFrame` remains the
    single source of truth for instance-state initialization.
    """

    threshold_container: wx.ScrolledWindow
    threshold_container_sizer: wx.BoxSizer
    sound_choice: wx.Choice
    poll_interval_ctrl: wx.SpinCtrl
    repeat_interval_ctrl: wx.SpinCtrl
    start_alert_checkbox: wx.CheckBox
    repeat_alarm_checkbox: wx.CheckBox
    status_text: wx.TextCtrl
    challenge_text: wx.StaticText | None

    def _build_thresholds_section(self, panel: wx.Panel, sizer: wx.Sizer) -> None:
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

    def _build_options_section(self, panel: wx.Panel, sizer: wx.Sizer) -> None:
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

    def _build_status_section(self, panel: wx.Panel, sizer: wx.Sizer) -> None:
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
