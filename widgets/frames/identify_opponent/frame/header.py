"""Top-of-window header construction (deck label, status, action buttons)."""

from __future__ import annotations

import wx

from utils.constants import (
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
    OPPONENT_TRACKER_SECTION_PADDING,
    SUBDUED_TEXT,
)


class HeaderBuilderMixin:
    """Builds the deck-name label, status line, and the row of header buttons.

    Kept as a mixin (no ``__init__``) so :class:`MTGOpponentDeckSpy` remains the
    single source of truth for instance-state initialization.
    """

    deck_label: wx.StaticText
    status_label: wx.StaticText
    load_arch_btn: wx.Button

    def _stylize_label(
        self, label: wx.StaticText, *, bold: bool = False, subtle: bool = False
    ) -> None:
        label.SetForegroundColour(SUBDUED_TEXT if subtle else LIGHT_TEXT)
        label.SetBackgroundColour(DARK_BG)
        font = label.GetFont()
        if bold:
            font.MakeBold()
            font.SetPointSize(font.GetPointSize() + 1)
        label.SetFont(font)

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _build_header(self, panel: wx.Panel, outer_sizer: wx.Sizer) -> None:
        self.deck_label = wx.StaticText(panel, label=self._t("tracker.label.not_detected"))
        self._stylize_label(self.deck_label)
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        outer_sizer.Add(self.deck_label, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        self.status_label = wx.StaticText(panel, label=self._t("tracker.label.watching"))
        self._stylize_label(self.status_label, subtle=True)
        self.status_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        outer_sizer.Add(
            self.status_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            OPPONENT_TRACKER_SECTION_PADDING,
        )

        divider = wx.StaticLine(panel)
        outer_sizer.Add(
            divider, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING
        )

        controls = wx.BoxSizer(wx.HORIZONTAL)
        outer_sizer.Add(controls, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        controls.AddStretchSpacer(1)

        refresh_button = wx.Button(panel, label=self._t("tracker.btn.refresh"))
        self._stylize_secondary_button(refresh_button)
        refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self._manual_refresh(force=True))
        controls.Add(refresh_button, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        self.load_arch_btn = wx.Button(panel, label=self._t("tracker.btn.load_archetype"))
        self._stylize_secondary_button(self.load_arch_btn)
        self.load_arch_btn.Bind(wx.EVT_BUTTON, self._on_load_archetype_clicked)
        controls.Add(self.load_arch_btn, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        close_button = wx.Button(panel, label=self._t("tracker.btn.close"))
        self._stylize_secondary_button(close_button)
        close_button.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        controls.Add(close_button, 0)
