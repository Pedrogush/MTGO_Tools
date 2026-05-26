"""UI construction for the deck stats panel.

Displays deck statistics using an optional HTML/CSS visualization rendered
inside a ``wx.html2.WebView``.  Shows summary statistics, mana curve breakdown,
color distribution, type counts, and opening-hand land probability analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.constants import DARK_PANEL
from widgets.panels.deck_stats_panel.handlers import DeckStatsPanelHandlersMixin
from widgets.panels.deck_stats_panel.properties import (
    _EMPTY_HTML,
    DeckStatsPanelPropertiesMixin,
)

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager
    from services.deck_service import DeckService


class DeckStatsPanel(DeckStatsPanelHandlersMixin, DeckStatsPanelPropertiesMixin, wx.Panel):
    """Panel that displays deck statistics using an embedded HTML view."""

    def __init__(
        self,
        parent: wx.Window,
        controller: Any,
        card_manager: CardDataManager | None = None,
        *,
        create_webview: bool = True,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.controller = controller
        self.card_manager = card_manager
        self.deck_service: DeckService = controller.deck_service
        self.zone_cards: dict[str, list[dict[str, Any]]] = {}
        self._webview_html = _EMPTY_HTML
        self._webview = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Hidden label kept for test/automation compatibility (summary text readable via GetLabel)
        self.summary_label = wx.StaticText(self, label="No deck loaded.")
        self.summary_label.Hide()

        if create_webview:
            self._create_webview()

    def _create_webview(self) -> None:
        if self._webview is not None:
            return
        try:
            import wx.html2

            self._webview = wx.html2.WebView.New(self)
        except Exception as exc:
            logger.warning(f"Deck stats WebView unavailable; using summary-only stats: {exc}")
            return

        sizer = self.GetSizer()
        if sizer is not None:
            sizer.Add(self._webview, 1, wx.EXPAND)
            self.Layout()
        self._webview.SetPage(self._webview_html, "")
