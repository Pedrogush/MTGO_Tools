"""Shared ``self`` contract that the :class:`DeckStatsPanel` mixins assume."""

from __future__ import annotations

from typing import Any, Protocol

import wx
import wx.html2

from services.deck_service import DeckService
from utils.card_data import CardDataManager


class DeckStatsPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckStatsPanel``."""

    card_manager: CardDataManager | None
    deck_service: DeckService
    zone_cards: dict[str, list[dict[str, Any]]]
    summary_label: wx.StaticText
    _webview: wx.html2.WebView

    def _count_lands(self) -> tuple[int, int]: ...
    def _curve_items(self) -> list[tuple[str, str, float, str, str]]: ...
    def _color_items(self) -> list[tuple[str, str, float, str, str]]: ...
    def _type_items(self) -> list[tuple[str, int, int, str, str]]: ...
    def _hand_items(
        self, deck_size: int | float, land_count: int | float
    ) -> list[tuple[str, str, float, str, str]]: ...
