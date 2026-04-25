"""UI construction for the compact sideboard guide panel.

Displays the cards to side in/out and notes for the detected opponent archetype,
sourced from the pinned deck's sideboard guide.
"""

from __future__ import annotations

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, PADDING_SM, SUBDUED_TEXT
from utils.constants.ui_layout import COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE
from widgets.panels.compact_sideboard_panel.handlers import CompactSideboardHandlersMixin


class CompactSideboardPanel(CompactSideboardHandlersMixin, wx.Panel):
    """Compact panel for displaying a single sideboard guide entry in the opponent tracker."""

    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self._current_entry: dict | None = None
        self._play_first: bool = True  # True = on play, False = on draw

        self._build_ui()
        self.Hide()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        header = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header, 0, wx.EXPAND | wx.ALL, PADDING_SM)

        self.header_label = wx.StaticText(self, label="Guide: —")
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        font = self.header_label.GetFont()
        self.header_label.SetFont(font.Bold())
        header.Add(self.header_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.toggle_btn = wx.Button(self, label="On Draw", size=COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE)
        self.toggle_btn.SetBackgroundColour(DARK_BG)
        self.toggle_btn.SetForegroundColour(LIGHT_TEXT)
        self.toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_play_draw)
        self.toggle_btn.Hide()
        header.Add(self.toggle_btn, 0, wx.LEFT, PADDING_SM)

        self.status_label = wx.StaticText(self, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

        self.card_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.card_list.SetBackgroundColour(DARK_BG)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.card_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)
