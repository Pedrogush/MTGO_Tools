"""UI construction for the compact sideboard guide panel.

Displays the cards to side in/out and notes for the detected opponent archetype,
sourced from the pinned deck's sideboard guide.
"""

from __future__ import annotations

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SPACE_XS, SUBDUED_TEXT
from utils.constants.ui_layout import COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE
from widgets.empty_state import EmptyState
from widgets.panels.compact_sideboard_panel.handlers import CompactSideboardHandlersMixin
from widgets.stylize import apply_type_level, strip_native_client_edge, stylize_button


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
        sizer.Add(header, 0, wx.EXPAND | wx.ALL, SPACE_XS)

        self.header_label = wx.StaticText(self, label="Guide: —")
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        # See the compact radar panel: a pane heading, on the ladder.
        apply_type_level(self.header_label, "heading")
        header.Add(self.header_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.toggle_btn = wx.Button(self, label="On Draw", size=COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE)
        stylize_button(self.toggle_btn, kind="ghost", surface="panel")
        self.toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_play_draw)
        self.toggle_btn.Hide()
        header.Add(self.toggle_btn, 0, wx.LEFT, SPACE_XS)

        self.status_label = wx.StaticText(self, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)

        self.card_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.card_list.SetBackgroundColour(DARK_BG)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        strip_native_client_edge(self.card_list)
        sizer.Add(self.card_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)

        # S4, the taller half of the tracker's two empty bordered rectangles.
        # See the compact radar panel for the reasoning; both use the one
        # empty-state component rather than an empty list with a caption above it.
        self.empty_state = EmptyState(
            self,
            message="Waiting for opponent\u2026",
            hint="Your sideboard plan appears here once the matchup is known.",
            surface="panel",
        )
        sizer.Add(self.empty_state, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)
        self.empty_state.Hide()
