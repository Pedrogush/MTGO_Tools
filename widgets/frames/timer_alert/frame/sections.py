"""Builders for each section of the timer alert frame: thresholds, options, status."""

from __future__ import annotations

import wx

from utils.constants import (
    DARK_ALT,
    DARK_PANEL,
    LIGHT_TEXT,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
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
from widgets.checkbox import DarkCheckBox
from widgets.frames.timer_alert.frame.threshold_panel import SOUND_OPTIONS
from widgets.section import SectionPanel
from widgets.stylize import stylize_scrollable


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
    start_alert_checkbox: DarkCheckBox
    repeat_alarm_checkbox: DarkCheckBox
    status_text: wx.TextCtrl
    challenge_text: wx.StaticText | None

    def _build_thresholds_section(self, panel: wx.Panel, sizer: wx.Sizer) -> None:
        # padding=0: every child below already adds its own SPACE_XS inset, and
        # this window has a fixed 580px height that phase 3 only just got the
        # threshold list to fit inside.
        threshold_section = SectionPanel(
            panel, title=self._t("timer.section.thresholds"), padding=0
        )
        threshold_sizer = threshold_section.sizer
        box_parent = threshold_section.body

        instructions = wx.StaticText(
            box_parent, label="Enter time in MM:SS format (e.g., 05:00 for 5 minutes)"
        )
        instructions.SetForegroundColour(SUBDUED_TEXT)
        threshold_sizer.Add(instructions, 0, wx.ALL, SPACE_XS)

        # Scrollable threshold container
        self.threshold_container = wx.ScrolledWindow(box_parent, style=wx.VSCROLL)
        stylize_scrollable(self.threshold_container, surface="base")
        self.threshold_container.SetScrollRate(0, TIMER_ALERT_SCROLL_RATE_Y)
        self.threshold_container_sizer = wx.BoxSizer(wx.VERTICAL)
        self.threshold_container.SetSizer(self.threshold_container_sizer)
        threshold_sizer.Add(self.threshold_container, 1, wx.EXPAND | wx.ALL, SPACE_XS)

        self._add_threshold_panel()

        add_btn = wx.Button(box_parent, label="+ Add Another Threshold")
        self._stylize_secondary_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._add_threshold_panel())
        threshold_sizer.Add(add_btn, 0, wx.ALL, SPACE_XS)

        sizer.Add(threshold_section, 1, wx.ALL | wx.EXPAND, SPACE_MD)

    def _build_options_section(self, panel: wx.Panel, sizer: wx.Sizer) -> None:
        options_grid = wx.FlexGridSizer(cols=2, hgap=SPACE_SM, vgap=SPACE_SM)
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

        sizer.Add(options_grid, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, SPACE_MD)

        # Checkboxes
        self.start_alert_checkbox = DarkCheckBox(panel, label=self._t("timer.check.start_alert"))
        self.start_alert_checkbox.SetValue(True)
        self._stylize_checkbox(self.start_alert_checkbox)
        sizer.Add(self.start_alert_checkbox, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_MD)

        self.repeat_alarm_checkbox = DarkCheckBox(panel, label=self._t("timer.check.repeat_alarm"))
        self.repeat_alarm_checkbox.SetValue(False)
        self._stylize_checkbox(self.repeat_alarm_checkbox)
        sizer.Add(self.repeat_alarm_checkbox, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        # Control buttons.
        #
        # A2: three buttons at their three natural label widths, packed left with
        # 8px between them, gave a row that ended nowhere in particular. A
        # wx.GridSizer with wx.EXPAND makes the three cells identical by
        # construction and lands the row's right edge on the same margin as the
        # option fields above it.
        button_row = wx.GridSizer(1, 3, 0, SPACE_SM)
        sizer.Add(button_row, 0, wx.ALL | wx.EXPAND, SPACE_MD)

        start_btn = wx.Button(panel, label=self._t("timer.btn.start"))
        self._stylize_primary_button(start_btn)
        start_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.start_monitoring())
        button_row.Add(start_btn, 0, wx.EXPAND)

        stop_btn = wx.Button(panel, label=self._t("timer.btn.stop"))
        self._stylize_secondary_button(stop_btn)
        stop_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.stop_monitoring())
        button_row.Add(stop_btn, 0, wx.EXPAND)

        test_btn = wx.Button(panel, label=self._t("timer.btn.test"))
        self._stylize_secondary_button(test_btn)
        test_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.test_alert())
        button_row.Add(test_btn, 0, wx.EXPAND)

    def _build_status_section(self, panel: wx.Panel, sizer: wx.Sizer) -> None:
        # Status display
        self.status_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.BORDER_NONE,
        )
        self.status_text.SetMinSize((-1, TIMER_ALERT_STATUS_MIN_HEIGHT))
        self.status_text.SetBackgroundColour(DARK_ALT)
        self.status_text.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.status_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, SPACE_MD)

        # Challenge timer display
        challenge_section = SectionPanel(
            panel, title=self._t("timer.section.challenge"), padding=SPACE_SM
        )
        self.challenge_text = wx.StaticText(
            challenge_section.body, label=self._t("timer.no_challenge")
        )
        self.challenge_text.SetForegroundColour(LIGHT_TEXT)
        self.challenge_text.SetBackgroundColour(DARK_PANEL)
        self.challenge_text.Wrap(TIMER_ALERT_CHALLENGE_WRAP_WIDTH)
        challenge_section.sizer.Add(self.challenge_text, 0, wx.EXPAND)
        sizer.Add(challenge_section, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, SPACE_MD)
