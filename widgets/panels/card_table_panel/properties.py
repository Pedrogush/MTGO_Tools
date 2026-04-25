"""Pure-data helpers and read-only getters for the card table panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from utils.constants import DECK_CARD_WIDTH

if TYPE_CHECKING:
    from widgets.panels.card_table_panel.protocol import CardTablePanelProto

    _Base = CardTablePanelProto
else:
    _Base = object


class CardTablePanelPropertiesMixin(_Base):
    """Read-only getters and pure-data helpers for :class:`CardTablePanel`.

    Kept as a mixin (no ``__init__``) so :class:`CardTablePanel` remains the
    single source of truth for instance-state initialization.
    """

    @classmethod
    def grid_width(cls) -> int:
        scrollbar_width = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        if scrollbar_width <= 0:
            scrollbar_width = 16
        # Each panel has GRID_GAP right-border, so effective width per column is
        # DECK_CARD_WIDTH + GRID_GAP. The scroller must be wide enough for exactly
        # GRID_COLUMNS panels plus the vertical scrollbar.
        return (DECK_CARD_WIDTH + cls.GRID_GAP) * cls.GRID_COLUMNS + scrollbar_width

    def get_selected_card(self) -> dict[str, Any] | None:
        if self.active_panel:
            return self.active_panel.card
        return None
