"""UI construction for the deck stats panel.

Displays deck statistics using an HTML/CSS visualization rendered inside a
``wx.html2.WebView``.  Shows summary statistics, mana curve breakdown, color
distribution, type counts, and opening-hand land probability analysis.
"""

from __future__ import annotations

from typing import Any

import wx
import wx.html2

from services.deck_service import DeckService, get_deck_service
from utils.card_data import CardDataManager
from utils.constants import DARK_PANEL
from widgets.panels.deck_stats_panel.handlers import DeckStatsPanelHandlersMixin
from widgets.panels.deck_stats_panel.properties import (
    _EMPTY_HTML,
    DeckStatsPanelPropertiesMixin,
)


class DeckStatsPanel(DeckStatsPanelHandlersMixin, DeckStatsPanelPropertiesMixin, wx.Panel):
    """Panel that displays deck statistics using an embedded HTML view."""

    def __init__(
        self,
        parent: wx.Window,
        card_manager: CardDataManager | None = None,
        deck_service: DeckService | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.card_manager = card_manager
        self.deck_service = deck_service or get_deck_service()
        self.zone_cards: dict[str, list[dict[str, Any]]] = {}

        self._webview = wx.html2.WebView.New(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._webview.SetPage(_EMPTY_HTML, "")

        # Hidden label kept for test/automation compatibility (summary text readable via GetLabel)
        self.summary_label = wx.StaticText(self, label="No deck loaded.")
        self.summary_label.Hide()
