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
    GRID_MIN_COLUMNS: ClassVar[int]
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

    # Toolbar surface (created in ``CardTablePanel.__init__``) reached by the
    # toolbar mixin.
    _locale: str | None
    _view_mode_buttons: dict[str, wx.Button]
    pile_sort_button: wx.Button
    printing_button: wx.Button | None
    _on_pile_sort_change: Callable[[str, str], None] | None
    _on_printing_mode: Callable[[str, str | None], None] | None

    def _t(self, key: str) -> str: ...

    def set_view_mode(self, mode: str, *, persist: bool = ...) -> None: ...

    def set_pile_sort(self, sort_mode: str, *, persist: bool = ...) -> None: ...

    def _switch_content_page(self) -> None: ...

    def _notify_selection(self, card: dict[str, Any] | None) -> None: ...
