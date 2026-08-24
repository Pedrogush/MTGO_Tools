"""UI construction for the compact radar panel.

Displays archetype card frequency in a small format, designed for embedding
in the opponent tracker overlay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SPACE_XS, SUBDUED_TEXT
from utils.constants.ui_layout import COMPACT_RADAR_TOGGLE_BTN_SIZE
from widgets.empty_state import EmptyState
from widgets.panels.compact_radar_panel.handlers import CompactRadarHandlersMixin
from widgets.panels.compact_radar_panel.properties import (
    CompactRadarPropertiesMixin,
    RadarViewMode,
)
from widgets.stylize import apply_type_level, strip_native_client_edge, stylize_button

if TYPE_CHECKING:
    from services.radar_service import RadarData


class CompactRadarPanel(CompactRadarHandlersMixin, CompactRadarPropertiesMixin, wx.Panel):
    """Compact panel for displaying radar data in small overlays."""

    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.current_radar: RadarData | None = None
        self._view_mode: RadarViewMode = RadarViewMode.TOP_CARDS
        # Unwrapped heading text; ``wx.StaticText.Wrap`` rewrites the label in
        # place, so the source string is needed to re-wrap on a resize.
        self._header_text: str = "Radar: Loading..."
        self._resizing: bool = False

        self._build_ui()
        self.Bind(wx.EVT_SIZE, self._on_resized)
        self.Hide()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Header row: label + view toggle button
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, SPACE_XS)

        self.header_label = wx.StaticText(self, label=self._header_text)
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        # It names the pane below it, so it is a heading -- which is what the
        # ladder's "heading" level is. Hand-rolled ``font.Bold()`` left it at
        # the base size, so the tracker's two panes were captioned a full step
        # smaller than "Hypergeometric Calculator" beside them.
        apply_type_level(self.header_label, "heading")
        header_sizer.Add(self.header_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.view_toggle_btn = wx.Button(
            self, label="Full Decklist", size=COMPACT_RADAR_TOGGLE_BTN_SIZE
        )
        # Was a hand-set DARK_BG fill on a DARK_PANEL surface -- a chip
        # *darker* than its own background -- inside wxMSW's 2px #ADADAD/#E1E1E1
        # frame, which is what actually read. ``ghost`` on ``panel`` steps the
        # neutral up instead of down; the frame goes with stylize_button.
        stylize_button(self.view_toggle_btn, kind="ghost", surface="panel")
        self.view_toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_view)
        self.view_toggle_btn.Hide()
        header_sizer.Add(self.view_toggle_btn, 0, wx.LEFT, SPACE_XS)

        # Status label (for loading/errors)
        self.status_label = wx.StaticText(self, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)

        # Scrollable list for cards
        self.card_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.card_list.SetBackgroundColour(DARK_BG)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        strip_native_client_edge(self.card_list)
        sizer.Add(self.card_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)

        # S4: with no opponent detected this pane was ~325px of empty white-
        # bordered ListBox under a one-line status label -- half of the tracker's
        # height given to a rectangle that said nothing. The list is hidden while
        # it is empty and the app's one empty-state block takes its place, so the
        # message sits in the middle of the space it is explaining.
        self.empty_state = EmptyState(
            self,
            message="Waiting for opponent\u2026",
            hint="The archetype radar fills in as soon as a match is detected.",
            surface="panel",
        )
        sizer.Add(self.empty_state, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)
        self.empty_state.Hide()
