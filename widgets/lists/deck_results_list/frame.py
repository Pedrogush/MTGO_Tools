"""UI construction for the deck results list widget."""

from __future__ import annotations

import wx

from utils.constants import (
    DARK_PANEL,
    LIGHT_TEXT,
    SELECTION_BORDER,
    SELECTION_BORDER_WIDTH,
    SELECTION_FILL_ON_PANEL,
    SUBDUED_TEXT,
)
from widgets.lists.deck_results_list.handlers import DeckResultsListHandlersMixin
from widgets.lists.deck_results_list.properties import DeckResultsListPropertiesMixin
from widgets.stylize import stylize_scrollable


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
        # C9/G1. Before phase 2 every row was outlined in the full-chroma accent
        # and the selected one was *filled* with it, so a 43-row list read as a
        # ladder of blue rectangles and selection read as fill-versus-stroke.
        # Now an unselected row has no border at all and the selected one is the
        # app's single selection idiom: a 16% accent tint plus a 2px accent edge,
        # i.e. presence-versus-absence.
        self._selection_bg = wx.Colour(*SELECTION_FILL_ON_PANEL)
        self._selection_border = wx.Colour(*SELECTION_BORDER)
        self._selection_border_width = SELECTION_BORDER_WIDTH
        stylize_scrollable(self, surface="alt")
        self.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
        self.SetItemCount(0)
