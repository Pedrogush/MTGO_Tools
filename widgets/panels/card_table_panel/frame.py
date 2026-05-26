"""UI construction for the card table panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.lib.scrolledpanel as scrolled

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import translate as _i18n_translate
from widgets.mana_icon_service import ManaIconFactory
from widgets.panels.card_box_panel import CardBoxPanel
from widgets.panels.card_table_panel.handlers import CardTablePanelHandlersMixin
from widgets.panels.card_table_panel.pile_view import DeckPileView
from widgets.panels.card_table_panel.properties import CardTablePanelPropertiesMixin
from widgets.panels.card_table_panel.sorting import (
    COL_COLOR,
    COL_MANA,
    COL_NAME,
    COL_TEXT,
    COL_TYPE,
    PILE_SORT_COLOR,
    PILE_SORT_MV,
    PILE_SORT_TYPE,
)
from widgets.panels.card_table_panel.table_view import DeckTableView

_EMPTY_STATE_HEADING_SIZE = 13
_EMPTY_STATE_HINT_SIZE = 10
_EMPTY_STATE_HEADING_GAP = 6

_ZONE_EMPTY_HEADING = {
    "main": "No deck loaded",
    "side": "Sideboard is empty",
    "out": "No cards out",
}
_ZONE_EMPTY_HINT = {
    "main": "Select a deck from the list, or load one from file",
}

# Simplebook page indices (alphabetical-by-mode after the bookend states).
_PAGE_EMPTY = 0
_PAGE_GRID = 1
_PAGE_TABLE = 2
_PAGE_PILE = 3
_PAGE_LOADING = 4

VIEW_MODES = ("grid", "table", "pile")


class CardTablePanel(CardTablePanelHandlersMixin, CardTablePanelPropertiesMixin, wx.Panel):
    GRID_COLUMNS = 4
    GRID_GAP = 8
    POOL_SIZE = 60

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        icon_factory: ManaIconFactory,
        get_metadata: Callable[[str], dict[str, Any] | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_add: Callable[[str], None],
        on_select: Callable[[str, dict[str, Any] | None], None],
        get_card_image: Callable[[str, str], Any],
        on_hover: Callable[[str, dict[str, Any]], None] | None = None,
        locale: str | None = None,
        initial_view_mode: str = "grid",
        initial_pile_sort: str = PILE_SORT_MV,
        on_view_mode_change: Callable[[str, str], None] | None = None,
        on_pile_sort_change: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self.icon_factory = icon_factory
        self._get_metadata = get_metadata
        self._owned_status = owned_status
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_add = on_add
        self._on_select = on_select
        self._get_card_image = get_card_image
        self._on_hover = on_hover
        self._locale = locale
        self._on_view_mode_change = on_view_mode_change
        self._on_pile_sort_change = on_pile_sort_change

        self.cards: list[dict[str, Any]] = []
        self.card_widgets: list[CardBoxPanel] = []
        self._pool: list[CardBoxPanel] = []
        self.active_panel: CardBoxPanel | None = None
        self.selected_name: str | None = None
        self.view_mode: str = initial_view_mode if initial_view_mode in VIEW_MODES else "grid"
        self.pile_sort: str = (
            initial_pile_sort
            if initial_pile_sort in (PILE_SORT_MV, PILE_SORT_COLOR, PILE_SORT_TYPE)
            else PILE_SORT_MV
        )

        self.SetBackgroundColour(DARK_PANEL)
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        header = wx.BoxSizer(wx.HORIZONTAL)
        self.count_label = wx.StaticText(self, label="0 cards")
        self.count_label.SetForegroundColour(SUBDUED_TEXT)
        header.Add(self.count_label, 0, wx.ALIGN_CENTER_VERTICAL)
        header.AddStretchSpacer(1)

        self._view_mode_buttons: dict[str, wx.Button] = {}
        for mode in VIEW_MODES:
            btn = wx.Button(self, label=self._t(f"tabs.view.{mode}"), style=wx.BU_EXACTFIT)
            btn.SetToolTip(self._t(f"tabs.view.tooltip.{mode}"))
            btn.Bind(wx.EVT_BUTTON, lambda _evt, m=mode: self._on_view_button(m))
            self._view_mode_buttons[mode] = btn
            header.Add(btn, 0, wx.LEFT, 4)

        self.pile_sort_button = wx.Button(self, label="⋯", style=wx.BU_EXACTFIT)
        self.pile_sort_button.SetToolTip(self._t("tabs.view.pile_sort"))
        self.pile_sort_button.Bind(wx.EVT_BUTTON, self._open_pile_sort_menu)
        header.Add(self.pile_sort_button, 0, wx.LEFT, 4)

        outer.Add(header, 0, wx.EXPAND | wx.BOTTOM, 4)

        self._content_book = wx.Simplebook(self)
        self._content_book.SetBackgroundColour(DARK_PANEL)

        # Page 0: empty state.
        self._empty_state = self._build_empty_state(self._content_book, zone)
        self._content_book.AddPage(self._empty_state, "empty")

        # Page 1: grid view (existing implementation).
        self.scroller = scrolled.ScrolledPanel(self._content_book, style=wx.VSCROLL)
        self.scroller.SetBackgroundColour(DARK_PANEL)
        self.grid_sizer = wx.WrapSizer(wx.HORIZONTAL)
        for _ in range(self.POOL_SIZE):
            cell = CardBoxPanel(
                self.scroller,
                zone,
                {"name": "", "qty": 0},
                icon_factory,
                get_metadata,
                owned_status,
                on_delta,
                on_remove,
                self._handle_card_click,
                get_card_image,
                on_hover,
            )
            self.grid_sizer.Add(cell, 0, wx.RIGHT | wx.BOTTOM, self.GRID_GAP)
            self.grid_sizer.Show(cell, False)
            self._pool.append(cell)
        self.scroller.SetSizer(self.grid_sizer)
        self.scroller.SetupScrolling(scroll_x=False, scroll_y=True, rate_x=5, rate_y=5)
        self._content_book.AddPage(self.scroller, "grid")

        # Page 2: table view.
        self.table_view = DeckTableView(
            self._content_book,
            zone,
            get_metadata,
            on_select=self._handle_view_select,
            on_hover=self._handle_view_hover,
            label_for_column=self._column_label,
        )
        self._content_book.AddPage(self.table_view, "table")

        # Page 3: pile view.
        self.pile_view = DeckPileView(
            self._content_book,
            zone,
            get_metadata,
            get_card_image,
            on_select=self._handle_view_select,
            on_hover=self._handle_view_hover,
            get_sort_mode=lambda: self.pile_sort,
        )
        self._content_book.AddPage(self.pile_view, "pile")

        # Page 4: loading state.
        self._loading_state = self._build_loading_state(self._content_book)
        self._content_book.AddPage(self._loading_state, "loading")

        outer.Add(self._content_book, 1, wx.EXPAND)

        self._refresh_view_mode_buttons()
        self._update_pile_sort_button_visibility()

    # ----- public API -----
    def set_view_mode(self, mode: str, *, persist: bool = True) -> None:
        if mode not in VIEW_MODES:
            return
        if mode == self.view_mode:
            return
        self.view_mode = mode
        if persist and self._on_view_mode_change:
            self._on_view_mode_change(self.zone, mode)
        self._refresh_view_mode_buttons()
        self._update_pile_sort_button_visibility()
        # Re-populate the now-active view if we have cards.
        if self.cards:
            if mode == "table":
                self.table_view.set_cards(self.cards)
                self.table_view.set_selected(self.selected_name)
            elif mode == "pile":
                self.pile_view.set_cards(self.cards)
                self.pile_view.set_selected(self.selected_name)
            self._switch_content_page()

    def set_pile_sort(self, sort_mode: str, *, persist: bool = True) -> None:
        if sort_mode not in (PILE_SORT_MV, PILE_SORT_COLOR, PILE_SORT_TYPE):
            return
        self.pile_sort = sort_mode
        if persist and self._on_pile_sort_change:
            self._on_pile_sort_change(self.zone, sort_mode)
        if self.view_mode == "pile":
            self.pile_view.refresh_sort()

    # ----- header helpers -----
    def _t(self, key: str) -> str:
        return _i18n_translate(self._locale, key)

    def _column_label(self, col_id: str) -> str:
        return self._t(f"tabs.view.col.{col_id}")

    def _refresh_view_mode_buttons(self) -> None:
        for mode, btn in self._view_mode_buttons.items():
            active = mode == self.view_mode
            btn.SetBackgroundColour(wx.Colour(*(DARK_ACCENT if active else DARK_ALT)))
            btn.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
            btn.Refresh()

    def _update_pile_sort_button_visibility(self) -> None:
        self.pile_sort_button.Show(self.view_mode == "pile")
        self.Layout()

    def _on_view_button(self, mode: str) -> None:
        self.set_view_mode(mode)

    def _open_pile_sort_menu(self, _event: wx.CommandEvent) -> None:
        menu = wx.Menu()
        items = (
            (PILE_SORT_MV, self._t("tabs.view.pile_sort.mv")),
            (PILE_SORT_COLOR, self._t("tabs.view.pile_sort.color")),
            (PILE_SORT_TYPE, self._t("tabs.view.pile_sort.type")),
        )
        for sort_mode, label in items:
            item = menu.AppendCheckItem(wx.ID_ANY, label)
            item.Check(sort_mode == self.pile_sort)
            menu.Bind(wx.EVT_MENU, lambda _evt, m=sort_mode: self.set_pile_sort(m), item)
        self.PopupMenu(menu, self.pile_sort_button.GetPosition())
        menu.Destroy()

    def _switch_content_page(self) -> None:
        if not self.cards:
            target = _PAGE_EMPTY
        elif self.view_mode == "table":
            target = _PAGE_TABLE
        elif self.view_mode == "pile":
            target = _PAGE_PILE
        else:
            target = _PAGE_GRID
        if self._content_book.GetSelection() != target:
            self._content_book.ChangeSelection(target)

    # ----- selection plumbing for the new views -----
    def _handle_view_select(self, card: dict[str, Any] | None) -> None:
        if card is None:
            self.selected_name = None
            self._sync_grid_selection()
            self._notify_selection(None)
            return
        self.selected_name = card["name"]
        # Mirror to grid view so the inspector stays consistent if user switches.
        self._sync_grid_selection()
        self._notify_selection(card)

    def _handle_view_hover(self, card: dict[str, Any]) -> None:
        if self._on_hover is None:
            return
        self._on_hover(self.zone, card)

    def _sync_grid_selection(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        if not self.selected_name:
            return
        for widget in self.card_widgets:
            if widget.card["name"].lower() == self.selected_name.lower():
                self.active_panel = widget
                widget.set_active(True)
                return

    @staticmethod
    def _build_loading_state(parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        sizer.AddStretchSpacer(2)
        label = wx.StaticText(panel, label="")
        label.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
        label.SetFont(
            wx.Font(
                _EMPTY_STATE_HEADING_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
        sizer.AddStretchSpacer(3)
        panel._label = label  # type: ignore[attr-defined]
        return panel

    @staticmethod
    def _build_empty_state(parent: wx.Window, zone: str) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        heading_text = _ZONE_EMPTY_HEADING.get(zone, "")
        hint_text = _ZONE_EMPTY_HINT.get(zone, "")

        sizer.AddStretchSpacer(2)

        if heading_text:
            heading = wx.StaticText(panel, label=heading_text)
            heading.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
            heading_font = wx.Font(
                _EMPTY_STATE_HEADING_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            heading.SetFont(heading_font)
            sizer.Add(
                heading,
                0,
                wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM,
                _EMPTY_STATE_HEADING_GAP,
            )

        if hint_text:
            hint = wx.StaticText(panel, label=hint_text)
            hint.SetForegroundColour(wx.Colour(*(max(c - 40, 0) for c in SUBDUED_TEXT)))
            hint_font = wx.Font(
                _EMPTY_STATE_HINT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            hint.SetFont(hint_font)
            sizer.Add(hint, 0, wx.ALIGN_CENTER_HORIZONTAL)

        sizer.AddStretchSpacer(3)
        return panel


# Re-export sort-mode tokens for callers that want to programmatically set
# pile sort mode without importing from sorting directly.
__all__ = [
    "CardTablePanel",
    "PILE_SORT_COLOR",
    "PILE_SORT_MV",
    "PILE_SORT_TYPE",
    "VIEW_MODES",
    "COL_COLOR",
    "COL_MANA",
    "COL_NAME",
    "COL_TEXT",
    "COL_TYPE",
]
