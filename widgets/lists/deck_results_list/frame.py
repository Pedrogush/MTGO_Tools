"""UI construction for the deck results list widget."""

from __future__ import annotations

import wx

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from widgets.lists.deck_results_list.handlers import DeckResultsListHandlersMixin
from widgets.lists.deck_results_list.properties import DeckResultsListPropertiesMixin


class DeckResultsList(DeckResultsListHandlersMixin, DeckResultsListPropertiesMixin, wx.VListBox):
    _ITEM_MARGIN = 6
    _CARD_RADIUS = 8
    _CARD_PADDING = 8
    _MIN_FONT_SIZE = 8
    _RIGHT_COL_RATIO = 0.30  # fraction of card width reserved for right column

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        # Each item is (is_structured, data).
        # Plain:  data = (emoji, line_one, line_two)
        # Deck:   data = (emoji, player, archetype, event, result, date)
        self._items: list[tuple[bool, tuple]] = []
        self._line_one_color = wx.Colour(*LIGHT_TEXT)
        self._line_two_color = wx.Colour(*SUBDUED_TEXT)
        self._card_bg = wx.Colour(*DARK_PANEL)
        self._card_border = wx.Colour(*DARK_ACCENT)
        self._selection_fg = wx.Colour(15, 17, 22)
        self.SetBackgroundColour(DARK_ALT)
        self.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
        self.SetItemCount(0)
