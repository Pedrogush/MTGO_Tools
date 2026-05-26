"""Table view for CardTablePanel.

Renders the cards in a sortable, reorderable grid powered by ``wx.grid.Grid``:

* Column headers are click-to-sort (clicking the active column toggles ascending
  / descending).
* Columns can be dragged to reorder via the native grid header drag.
* A single row is the "selection". Clicking the selected row clears it. Hover
  fires the on_hover callback for the row under the mouse, mirroring the grid
  view's selection/hover contract.

The mana column uses a custom renderer that draws each ``{W}/{U}/{B}/{R}/{G}/{N}``
token as a :class:`ManaIconFactory` bitmap instead of raw braced text. The
``type`` and ``text`` columns use an ellipsis-truncating renderer so a narrow
column shows ``…`` rather than clipping mid-glyph.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.grid as gridlib

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.constants.ui_images import MANA_COST_BITMAP_GAP, MANA_ICON_DEFAULT_SIZE
from widgets.mana_icon_service import ManaIconFactory, tokenize_mana_symbols
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

# Hard cap on raw oracle text stored in cells (the renderer further truncates
# visually with ellipsis). Larger than the pixel-fit needs so the renderer has
# room to ellipsize precisely.
_MAX_TEXT_CHARS = 220
_ROW_HEIGHT = MANA_ICON_DEFAULT_SIZE + 4
_MANA_CELL_PADDING = 4
_CELL_TEXT_PADDING = 4

# Caps applied after auto-sizing so the truncatable columns can't monopolise
# the view width on long oracle texts or type lines.
_MAX_TYPE_WIDTH = 220
_MAX_TEXT_WIDTH = 480

_COLUMN_LABELS: dict[str, str] = {
    COL_MANA: "Mana",
    COL_NAME: "Name",
    COL_TYPE: "Type",
    COL_TEXT: "Text",
    COL_COLOR: "Color",
}


class _ManaIconCellRenderer(gridlib.GridCellRenderer):
    """Draws the mana column as a horizontal row of mana-symbol bitmaps."""

    def __init__(
        self, icon_factory: ManaIconFactory, icon_size: int = MANA_ICON_DEFAULT_SIZE
    ) -> None:
        super().__init__()
        self._factory = icon_factory
        self._icon_size = icon_size
        self._gap = MANA_COST_BITMAP_GAP

    def Draw(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        rect: wx.Rect,
        row: int,
        col: int,
        isSelected: bool,
    ) -> None:
        bg = (
            grid.GetSelectionBackground() if isSelected else grid.GetDefaultCellBackgroundColour()
        )
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        tokens = tokenize_mana_symbols(grid.GetCellValue(row, col))
        if not tokens:
            return

        x = rect.x + _MANA_CELL_PADDING
        for idx, token in enumerate(tokens):
            try:
                bmp = self._factory.bitmap_for_symbol(token)
            except Exception:
                bmp = None
            if bmp is None:
                continue
            y = rect.y + (rect.height - bmp.GetHeight()) // 2
            dc.DrawBitmap(bmp, x, y, True)
            x += bmp.GetWidth()
            if idx < len(tokens) - 1:
                x += self._gap

    def GetBestSize(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        row: int,
        col: int,
    ) -> wx.Size:
        tokens = tokenize_mana_symbols(grid.GetCellValue(row, col))
        if not tokens:
            return wx.Size(self._icon_size, self._icon_size)
        width = (
            _MANA_CELL_PADDING * 2
            + len(tokens) * self._icon_size
            + max(0, len(tokens) - 1) * self._gap
        )
        return wx.Size(width, self._icon_size)

    def Clone(self) -> "_ManaIconCellRenderer":
        return _ManaIconCellRenderer(self._factory, self._icon_size)


class _EllipsisStringRenderer(gridlib.GridCellStringRenderer):
    """String renderer that truncates with ``…`` when content exceeds cell width."""

    _ELLIPSIS = "…"

    def Draw(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        rect: wx.Rect,
        row: int,
        col: int,
        isSelected: bool,
    ) -> None:
        if isSelected:
            bg = grid.GetSelectionBackground()
            fg = grid.GetSelectionForeground()
        else:
            bg = grid.GetDefaultCellBackgroundColour()
            fg = grid.GetDefaultCellTextColour()
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        dc.SetFont(grid.GetDefaultCellFont())
        dc.SetTextForeground(fg)

        text = grid.GetCellValue(row, col)
        available = rect.width - _CELL_TEXT_PADDING * 2
        if available > 0 and dc.GetTextExtent(text)[0] > available:
            while text and dc.GetTextExtent(text + self._ELLIPSIS)[0] > available:
                text = text[:-1]
            text = (text + self._ELLIPSIS) if text else self._ELLIPSIS

        y = rect.y + max(0, (rect.height - dc.GetCharHeight()) // 2)
        dc.DrawText(text, rect.x + _CELL_TEXT_PADDING, y)

    def Clone(self) -> "_EllipsisStringRenderer":
        return _EllipsisStringRenderer()


class DeckTableView(wx.Panel):
    """A wx.grid-backed sortable/reorderable table of deck cards."""

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        get_metadata: Callable[[str], Any],
        on_select: Callable[[dict[str, Any] | None], None],
        on_hover: Callable[[dict[str, Any]], None] | None,
        icon_factory: ManaIconFactory,
        label_for_column: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self._get_metadata = get_metadata
        self._on_select = on_select
        self._on_hover = on_hover
        self._icon_factory = icon_factory
        self._labels = label_for_column or _COLUMN_LABELS.get

        self._cards: list[dict[str, Any]] = []
        self._rows: list[dict[str, Any]] = []  # cards in current display order
        self._sort_column: str = COL_NAME
        self._sort_descending: bool = False
        self._selected_name: str | None = None
        self._hover_row: int = -1
        self._needs_autosize: bool = True

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
            renderer: gridlib.GridCellRenderer | None
            if col_id == COL_MANA:
                renderer = _ManaIconCellRenderer(icon_factory)
            elif col_id in (COL_TYPE, COL_TEXT):
                renderer = _EllipsisStringRenderer()
            else:
                renderer = None
            if renderer is not None:
                attr = gridlib.GridCellAttr()
                attr.SetRenderer(renderer)
                self.grid.SetColAttr(idx, attr)

        sizer.Add(self.grid, 1, wx.EXPAND)

        self.grid.Bind(gridlib.EVT_GRID_LABEL_LEFT_CLICK, self._on_header_click)
        self.grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self._on_cell_click)
        self.grid.Bind(gridlib.EVT_GRID_SELECT_CELL, self._on_cell_select)
        self.grid.GetGridWindow().Bind(wx.EVT_MOTION, self._on_grid_motion)
        self.grid.GetGridWindow().Bind(wx.EVT_LEAVE_WINDOW, self._on_grid_leave)

    # ----- public API consumed by CardTablePanel -----
    def set_cards(self, cards: list[dict[str, Any]]) -> None:
        self._cards = list(cards)
        # Content changed — recompute column widths from the new data.
        self._needs_autosize = True
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
        if self._needs_autosize and self.grid.GetNumberRows() > 0:
            self._autosize_columns()
            self._needs_autosize = False

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
            if mv == 0 and "land" in (card_type_line(meta) or "").lower():
                return ""
            # Brace the bare numeric so the renderer can tokenize it as {N}.
            return f"{{{int(mv)}}}"
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

    def _autosize_columns(self) -> None:
        """Size each column to fit its content.

        Mana and color never truncate, so they keep whatever AutoSizeColumn
        produces. Type and text are capped so a single huge oracle text can't
        push the rest of the columns off-screen; the cell renderer then draws
        an ellipsis when content exceeds the visible width.
        """
        caps: dict[str, int] = {COL_TYPE: _MAX_TYPE_WIDTH, COL_TEXT: _MAX_TEXT_WIDTH}
        for idx, col_id in enumerate(TABLE_COLUMNS):
            self.grid.AutoSizeColumn(idx, setAsMin=False)
            cap = caps.get(col_id)
            if cap is not None and self.grid.GetColSize(idx) > cap:
                self.grid.SetColSize(idx, cap)

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
