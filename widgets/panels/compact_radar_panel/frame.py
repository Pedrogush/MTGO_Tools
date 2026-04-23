"""UI construction for the compact radar panel.

Displays archetype card frequency in a small format, designed for embedding
in the opponent tracker overlay.
"""

from __future__ import annotations

import wx

from services.radar_service import RadarData
from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from widgets.panels.compact_radar_panel.handlers import CompactRadarHandlersMixin
from widgets.panels.compact_radar_panel.properties import (
    CompactRadarPropertiesMixin,
    RadarViewMode,
)


class CompactRadarPanel(CompactRadarHandlersMixin, CompactRadarPropertiesMixin, wx.Panel):
    """Compact panel for displaying radar data in small overlays."""

    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.current_radar: RadarData | None = None
        self._view_mode: RadarViewMode = RadarViewMode.TOP_CARDS

        self._build_ui()
        self.Hide()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Header row: label + view toggle button
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 4)

        self.header_label = wx.StaticText(self, label="Radar: Loading...")
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        font = self.header_label.GetFont()
        font = font.Bold()
        self.header_label.SetFont(font)
        header_sizer.Add(self.header_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.view_toggle_btn = wx.Button(self, label="Full Decklist", size=(90, 22))
        self.view_toggle_btn.SetBackgroundColour(DARK_BG)
        self.view_toggle_btn.SetForegroundColour(LIGHT_TEXT)
        self.view_toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_view)
        self.view_toggle_btn.Hide()
        header_sizer.Add(self.view_toggle_btn, 0, wx.LEFT, 4)

        # Status label (for loading/errors)
        self.status_label = wx.StaticText(self, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        # Scrollable list for cards
        self.card_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.card_list.SetBackgroundColour(DARK_BG)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.card_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
