"""Table view for CardTablePanel.

Renders the cards in a sortable, reorderable grid powered by ``wx.grid.Grid``:

* Column headers are click-to-sort (clicking the active column toggles ascending
  / descending).
* Columns can be dragged to reorder via the native grid header drag.
* A single row is the "selection". Clicking the selected row clears it. Hover
  fires the on_hover callback for the row under the mouse, mirroring the grid
  view's selection/hover contract.

The view delegates owned-status colouring of the qty column to the same
``owned_status`` callable used by the grid view.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.grid as gridlib

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from widgets.panels.card_table_panel.sorting import (
    COL_COLOR,
    COL_MANA,
    COL_NAME,
    COL_TEXT,
    COL_TYPE,
    TABLE_COLUMNS,
    card_colors,
    card_mana_value,
    card_type_line,
    sort_table_rows,
)

_MAX_TEXT_CHARS = 80
_ROW_HEIGHT = 22

_COLUMN_LABELS: dict[str, str] = {
    COL_MANA: "Mana",
    COL_NAME: "Name",
    COL_TYPE: "Type",
    COL_TEXT: "Text",
    COL_COLOR: "Color",
}

_COLUMN_WIDTHS: dict[str, int] = {
    COL_MANA: 70,
    COL_NAME: 200,
    COL_TYPE: 160,
    COL_TEXT: 320,
    COL_COLOR: 90,
}


class DeckTableView(wx.Panel):
    """A wx.grid-backed sortable/reorderable table of deck cards."""

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        get_metadata: Callable[[str], Any],
        on_select: Callable[[dict[str, Any] | None], None],
        on_hover: Callable[[dict[str, Any]], None] | None,
        label_for_column: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self._get_metadata = get_metadata
        self._on_select = on_select
        self._on_hover = on_hover
        self._labels = label_for_column or _COLUMN_LABELS.get

        self._cards: list[dict[str, Any]] = []
        self._rows: list[dict[str, Any]] = []  # cards in current display order
        self._sort_column: str = COL_NAME
        self._sort_descending: bool = False
        self._selected_name: str | None = None
        self._hover_row: int = -1

        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self.grid = gridlib.Grid(self)
        self.grid.CreateGrid(0, len(TABLE_COLUMNS))
        self.grid.EnableEditing(False)
        self.grid.EnableDragColMove(True)
        self.grid.EnableDragColSize(True)
        self.grid.EnableDragRowSize(False)
        self.grid.SetRowLabelSize(0)
        self.grid.SetSelectionMode(gridlib.Grid.GridSelectRows)
        self.grid.SetDefaultRowSize(_ROW_HEIGHT)
        self.grid.SetDefaultCellBackgroundColour(wx.Colour(*DARK_ALT))
        self.grid.SetDefaultCellTextColour(wx.Colour(*LIGHT_TEXT))
        self.grid.SetLabelBackgroundColour(wx.Colour(*DARK_BG))
        self.grid.SetLabelTextColour(wx.Colour(*SUBDUED_TEXT))
        self.grid.SetGridLineColour(wx.Colour(*DARK_BG))
        # Disable the native cell-selection highlight; we draw our own row
        # background so the active selection survives reorders.
        self.grid.SetSelectionBackground(wx.Colour(*DARK_ACCENT))
        self.grid.SetSelectionForeground(wx.Colour(*LIGHT_TEXT))

        for idx, col_id in enumerate(TABLE_COLUMNS):
            self.grid.SetColLabelValue(idx, self._label(col_id))
            self.grid.SetColSize(idx, _COLUMN_WIDTHS.get(col_id, 120))

        sizer.Add(self.grid, 1, wx.EXPAND)

        self.grid.Bind(gridlib.EVT_GRID_LABEL_LEFT_CLICK, self._on_header_click)
        self.grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self._on_cell_click)
        self.grid.Bind(gridlib.EVT_GRID_SELECT_CELL, self._on_cell_select)
        self.grid.GetGridWindow().Bind(wx.EVT_MOTION, self._on_grid_motion)
        self.grid.GetGridWindow().Bind(wx.EVT_LEAVE_WINDOW, self._on_grid_leave)

    # ----- public API consumed by CardTablePanel -----
    def set_cards(self, cards: list[dict[str, Any]]) -> None:
        self._cards = list(cards)
        self._refresh()

    def set_selected(self, name: str | None) -> None:
        self._selected_name = name
        self._apply_selection_highlight()

    def get_selected_name(self) -> str | None:
        return self._selected_name

    # ----- internal helpers -----
    def _label(self, col_id: str) -> str:
        translated = self._labels(col_id) if callable(self._labels) else None
        return translated or _COLUMN_LABELS.get(col_id, col_id)

    def _column_id_at(self, native_col: int) -> str:
        """Translate a visual column index (post-reorder) back to its column id."""
        if 0 <= native_col < len(TABLE_COLUMNS):
            return TABLE_COLUMNS[native_col]
        return TABLE_COLUMNS[0]

    def _refresh(self) -> None:
        sorted_cards = sort_table_rows(
            self._cards, self._get_metadata, self._sort_column, self._sort_descending
        )
        self._rows = sorted_cards
        self.grid.BeginBatch()
        try:
            current = self.grid.GetNumberRows()
            needed = len(sorted_cards)
            if needed > current:
                self.grid.AppendRows(needed - current)
            elif needed < current:
                self.grid.DeleteRows(needed, current - needed)
            for row_idx, card in enumerate(sorted_cards):
                meta = self._get_metadata(card["name"]) or {}
                for col_idx, col_id in enumerate(TABLE_COLUMNS):
                    self.grid.SetCellValue(row_idx, col_idx, self._cell_text(card, meta, col_id))
            self._apply_selection_highlight()
            self._update_sort_indicator()
        finally:
            self.grid.EndBatch()

    @staticmethod
    def _cell_text(card: dict[str, Any], meta: Any, col_id: str) -> str:
        if col_id == COL_NAME:
            qty = card.get("qty", 1)
            return f"{qty}× {card['name']}"
        if col_id == COL_MANA:
            cost = meta.get("mana_cost")
            if cost:
                return cost
            mv = card_mana_value(meta)
            return (
                "" if mv == 0 and "land" in (card_type_line(meta) or "").lower() else str(int(mv))
            )
        if col_id == COL_TYPE:
            return card_type_line(meta)
        if col_id == COL_TEXT:
            text = (meta.get("oracle_text") or "").replace("\n", " ")
            if len(text) > _MAX_TEXT_CHARS:
                return text[: _MAX_TEXT_CHARS - 1] + "…"
            return text
        if col_id == COL_COLOR:
            cols = card_colors(meta)
            if not cols:
                return "C"
            return "".join(cols)
        return ""

    def _update_sort_indicator(self) -> None:
        arrow = " ▼" if self._sort_descending else " ▲"
        for idx, col_id in enumerate(TABLE_COLUMNS):
            base = self._label(col_id)
            label = base + arrow if col_id == self._sort_column else base
            self.grid.SetColLabelValue(idx, label)

    def _apply_selection_highlight(self) -> None:
        self.grid.ClearSelection()
        if not self._selected_name:
            return
        for idx, card in enumerate(self._rows):
            if card["name"].lower() == self._selected_name.lower():
                self.grid.SelectRow(idx)
                self.grid.MakeCellVisible(idx, 0)
                return

    # ----- event handlers -----
    def _on_header_click(self, event: gridlib.GridEvent) -> None:
        col = event.GetCol()
        if col < 0:
            event.Skip()
            return
        col_id = self._column_id_at(col)
        if col_id == self._sort_column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = col_id
            self._sort_descending = False
        self._refresh()

    def _on_cell_click(self, event: gridlib.GridEvent) -> None:
        row = event.GetRow()
        if not (0 <= row < len(self._rows)):
            event.Skip()
            return
        card = self._rows[row]
        if self._selected_name and card["name"].lower() == self._selected_name.lower():
            self._selected_name = None
            self._apply_selection_highlight()
            self._on_select(None)
            return
        self._selected_name = card["name"]
        self._apply_selection_highlight()
        self._on_select(card)

    def _on_cell_select(self, event: gridlib.GridEvent) -> None:
        # Suppress the native single-cell highlight; we manage row selection.
        event.Veto()

    def _on_grid_motion(self, event: wx.MouseEvent) -> None:
        if self._selected_name or self._on_hover is None:
            event.Skip()
            return
        x, y = self.grid.CalcUnscrolledPosition(event.GetPosition())
        row = self.grid.YToRow(y)
        if row == self._hover_row:
            event.Skip()
            return
        self._hover_row = row
        if 0 <= row < len(self._rows):
            self._on_hover(self._rows[row])
        event.Skip()

    def _on_grid_leave(self, event: wx.MouseEvent) -> None:
        self._hover_row = -1
        event.Skip()
