"""Shared ``self`` contract that the :class:`DeckGoldfishPanel` mixins assume."""

from __future__ import annotations

from typing import Protocol

import wx

from services.deck_service.goldfish import GoldfishTable
from widgets.panels.deck_goldfish_panel.card_art import GoldfishArtCache
from widgets.panels.deck_goldfish_panel.table_view import GoldfishTableView


class DeckGoldfishPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckGoldfishPanel``."""

    table: GoldfishTable
    status_label: wx.StaticText
    new_hand_button: wx.Button
    mulligan_button: wx.Button
    draw_button: wx.Button
    _art: GoldfishArtCache
    _view: GoldfishTableView

    def _t(self, key: str, **kwargs: object) -> str: ...
