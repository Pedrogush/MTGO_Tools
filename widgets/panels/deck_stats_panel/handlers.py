"""Public state setters and UI populators for the deck stats panel."""

from __future__ import annotations

from typing import Any

import wx
import wx.html2

from services.deck_service import DeckService
from utils.card_data import CardDataManager
from widgets.panels.deck_stats_panel.properties import _EMPTY_HTML, _build_html


class DeckStatsPanelHandlersMixin:
    """Public API methods that read state and drive the embedded WebView for :class:`DeckStatsPanel`."""

    card_manager: CardDataManager | None
    deck_service: DeckService
    zone_cards: dict[str, list[dict[str, Any]]]
    summary_label: wx.StaticText
    _webview: wx.html2.WebView

    def update_stats(self, deck_text: str, zone_cards: dict[str, list[dict[str, Any]]]) -> None:
        self.zone_cards = zone_cards

        if not deck_text.strip():
            self.summary_label.SetLabel("No deck loaded.")
            self._webview.SetPage(_EMPTY_HTML, "")
            return

        stats = self.deck_service.analyze_deck(deck_text)
        land_count, mdfc_count = self._count_lands()
        total_land_count = land_count + mdfc_count

        land_label = f"{land_count} land{'s' if land_count != 1 else ''}"
        if mdfc_count:
            land_label += f" + {mdfc_count} MDFC{'s' if mdfc_count != 1 else ''}"
        summary = (
            f"Mainboard: {stats['mainboard_count']} cards ({stats['unique_mainboard']} unique)"
            f"  |  Sideboard: {stats['sideboard_count']} cards ({stats['unique_sideboard']} unique)"
            f"  |  Lands: {land_label}"
        )

        self.summary_label.SetLabel(summary)

        html = _build_html(
            summary,
            self._curve_items(),
            self._color_items(),
            self._type_items(),
            self._hand_items(stats["mainboard_count"], total_land_count),
        )
        self._webview.SetPage(html, "")

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        self.card_manager = card_manager

    def clear(self) -> None:
        self.summary_label.SetLabel("No deck loaded.")
        self._webview.SetPage(_EMPTY_HTML, "")
