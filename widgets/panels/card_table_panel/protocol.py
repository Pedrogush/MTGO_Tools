"""Shared ``self`` contract that the :class:`CardTablePanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Protocol

import wx

from widgets.panels.card_table_panel.grid_view import DeckGridView
from widgets.panels.card_table_panel.pile_view import DeckPileView
from widgets.panels.card_table_panel.table_view import DeckTableView


class CardTablePanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardTablePanel``."""

    GRID_COLUMNS: ClassVar[int]
    GRID_GAP: ClassVar[int]

    zone: str
    cards: list[dict[str, Any]]
    selected_name: str | None
    count_label: wx.StaticText
    _content_book: wx.Simplebook
    _loading_state: wx.Panel
    _get_metadata: Callable[[str], dict[str, Any] | None]
    _on_select: Callable[[str, dict[str, Any] | None], None]
    view_mode: str
    pile_sort: str
    grid_view: DeckGridView
    table_view: DeckTableView
    pile_view: DeckPileView

    def _switch_content_page(self) -> None: ...

    def _notify_selection(self, card: dict[str, Any] | None) -> None: ...
