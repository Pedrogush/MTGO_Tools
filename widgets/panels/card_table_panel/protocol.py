"""Shared ``self`` contract that the :class:`CardTablePanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Protocol

import wx
import wx.lib.scrolledpanel as scrolled

from widgets.panels.card_box_panel import CardBoxPanel
from widgets.panels.card_table_panel.pile_view import DeckPileView
from widgets.panels.card_table_panel.table_view import DeckTableView


class CardTablePanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardTablePanel``."""

    GRID_COLUMNS: ClassVar[int]
    GRID_GAP: ClassVar[int]

    zone: str
    cards: list[dict[str, Any]]
    card_widgets: list[CardBoxPanel]
    _pool: list[CardBoxPanel]
    active_panel: CardBoxPanel | None
    selected_name: str | None
    _scroll_count: int
    count_label: wx.StaticText
    scroller: scrolled.ScrolledPanel
    grid_sizer: wx.WrapSizer
    _content_book: wx.Simplebook
    _loading_state: wx.Panel
    _get_metadata: Callable[[str], dict[str, Any] | None]
    _on_select: Callable[[str, dict[str, Any] | None], None]
    view_mode: str
    pile_sort: str
    table_view: DeckTableView
    pile_view: DeckPileView

    def _switch_content_page(self) -> None: ...

    def _ensure_pool(self, size: int) -> None: ...
