"""Table view for CardTablePanel.

Renders the cards in a sortable, reorderable grid powered by ``wx.grid.Grid``:

* Column headers are click-to-sort (clicking the active column toggles ascending
  / descending).
* Columns can be dragged to reorder via the native grid header drag.
* A single row is the "selection". Clicking the selected row clears it. Hover
  fires the on_hover callback for the row under the mouse, mirroring the grid
  view's selection/hover contract.

The mana and color columns use ``_ManaIconCellRenderer`` which paints each
``{W}/{U}/...`` token as a :class:`ManaIconFactory` bitmap, scaled to the
cell font height so icons match surrounding text. The text column uses
``_InlineSymbolStringRenderer`` which draws oracle text with inline mana
symbols (e.g. ``{T}: Add {G}.``). Type and Text are truncated with ``…`` when
the column is narrower than the content, and are auto-shrunk so the whole row
fits the visible grid width.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.grid as gridlib

from utils.constants import DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel.sorting import (
    COL_COLOR,
    COL_MANA,
    COL_NAME,
    COL_TEXT,
    COL_TYPE,
    TABLE_ACTION_ADD,
    TABLE_ACTION_REMOVE,
    TABLE_ACTION_SUB,
    TABLE_COLUMNS,
    action_slot_at,
    card_colors,
    card_mana_value,
    card_type_line,
    sort_table_rows,
)
from widgets.panels.card_table_panel.table_renderers import (
    _ACTIONS_COL_WIDTH,
    _ActionCellRenderer,
    _EllipsisStringRenderer,
    _font_height,
    _InlineSymbolStringRenderer,
    _ManaIconCellRenderer,
)

# Safety cap on raw oracle text stored in cells. The inline-symbol renderer
# does pixel-precise ellipsis truncation, but storing massive strings still
# costs memory in the grid table.
_MAX_TEXT_CHARS = 400

# Mana/color icons are sized larger than text icons (by 4px) so they fill the
# row height without top/bottom padding.
_CELL_ICON_SIZE_BONUS = 4

# Natural-width caps applied during AutoSize. _fit_to_width then shrinks
# further so the whole row fits the visible viewport.
_MAX_TYPE_WIDTH = 220
_MAX_TEXT_WIDTH = 540
_MIN_TYPE_WIDTH = 70
_MIN_TEXT_WIDTH = 100

_COLUMN_LABELS: dict[str, str] = {
    COL_MANA: "Mana",
    COL_NAME: "Name",
    COL_TYPE: "Type",
    COL_TEXT: "Text",
    COL_COLOR: "Color",
}

# Trailing, non-data "actions" column rendered with the same +/-/x controls the
# grid view shows on a selected card. It is not part of TABLE_COLUMNS so it
# never participates in sorting or fit-to-width; it is appended after the data
# columns and clicks on it are routed by x-position to add/remove/delete.
_ACTIONS_COL = len(TABLE_COLUMNS)


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
        on_delta: Callable[[str, int], None] | None = None,
        on_remove: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self._get_metadata = get_metadata
        self._on_select = on_select
        self._on_hover = on_hover
        self._icon_factory = icon_factory
        self._labels = label_for_column or _COLUMN_LABELS.get
        self._on_delta = on_delta
        self._on_remove = on_remove

        self._cards: list[dict[str, Any]] = []
        self._rows: list[dict[str, Any]] = []  # cards in current display order
        self._sort_column: str = COL_NAME
        self._sort_descending: bool = False
        self._selected_name: str | None = None
        self._hover_row: int = -1
        self._needs_autosize: bool = True
        # Natural widths populated by _autosize_columns; _fit_to_width starts
        # from these so resizing the panel wider re-expands the columns.
        self._natural_widths: dict[int, int] = {}

        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self.grid = gridlib.Grid(self)
        # One extra trailing column hosts the +/-/x row controls.
        self.grid.CreateGrid(0, len(TABLE_COLUMNS) + 1)
        self.grid.EnableEditing(False)
        self.grid.EnableDragColMove(True)
        self.grid.EnableDragColSize(True)
        self.grid.EnableDragRowSize(False)
        self.grid.SetRowLabelSize(0)
        self.grid.SetSelectionMode(gridlib.Grid.GridSelectRows)
        self.grid.SetDefaultCellBackgroundColour(wx.Colour(*DARK_ALT))
        self.grid.SetDefaultCellTextColour(wx.Colour(*LIGHT_TEXT))
        self.grid.SetLabelBackgroundColour(wx.Colour(*DARK_BG))
        self.grid.SetLabelTextColour(wx.Colour(*SUBDUED_TEXT))
        self.grid.SetGridLineColour(wx.Colour(*DARK_BG))
        # Selection background matches the cell background so the native row
        # fill is invisible; renderers paint the accent bar themselves. The
        # cell-highlight pen is what would otherwise draw a black focus rect
        # around the current cell (most visibly cell (0,0) at startup).
        self.grid.SetSelectionBackground(wx.Colour(*DARK_ALT))
        self.grid.SetSelectionForeground(wx.Colour(*LIGHT_TEXT))
        self.grid.SetCellHighlightPenWidth(0)
        self.grid.SetCellHighlightROPenWidth(0)

        # All mana symbols (mana/color cells and inline-in-text) share one
        # icon size that fills the row height — no visible top/bottom padding.
        # That size is the cell-font line height plus a small bonus so the
        # symbols look consistent across columns. The row is 1 px taller than
        # the icon so the top pixel row isn't clipped against the grid line.
        self._icon_size = _font_height(self.grid.GetDefaultCellFont())
        self._cell_icon_size = self._icon_size + _CELL_ICON_SIZE_BONUS
        self.grid.SetDefaultRowSize(self._cell_icon_size + 1)

        for idx, col_id in enumerate(TABLE_COLUMNS):
            self.grid.SetColLabelValue(idx, self._label(col_id))
            renderer: gridlib.GridCellRenderer
            if col_id in (COL_MANA, COL_COLOR):
                renderer = _ManaIconCellRenderer(icon_factory, self._cell_icon_size)
            elif col_id == COL_TEXT:
                renderer = _InlineSymbolStringRenderer(icon_factory, self._cell_icon_size)
            else:
                # Name + Type share the same ellipsis-truncating renderer so
                # they participate in the selection bar / bold-text styling.
                renderer = _EllipsisStringRenderer()
            attr = gridlib.GridCellAttr()
            attr.SetRenderer(renderer)
            self.grid.SetColAttr(idx, attr)

        # Actions column: fixed width, non-sortable, non-resizable.
        self.grid.SetColLabelValue(_ACTIONS_COL, "")
        actions_attr = gridlib.GridCellAttr()
        actions_attr.SetRenderer(_ActionCellRenderer())
        self.grid.SetColAttr(_ACTIONS_COL, actions_attr)
        self.grid.SetColSize(_ACTIONS_COL, _ACTIONS_COL_WIDTH)
        self.grid.DisableColResize(_ACTIONS_COL)

        sizer.Add(self.grid, 1, wx.EXPAND)

        self.grid.Bind(gridlib.EVT_GRID_LABEL_LEFT_CLICK, self._on_header_click)
        self.grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self._on_cell_click)
        self.grid.Bind(gridlib.EVT_GRID_SELECT_CELL, self._on_cell_select)
        self.grid.GetGridWindow().Bind(wx.EVT_MOTION, self._on_grid_motion)
        self.grid.GetGridWindow().Bind(wx.EVT_LEAVE_WINDOW, self._on_grid_leave)
        self.Bind(wx.EVT_SIZE, self._on_panel_resize)

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
                return "{C}"
            return "".join(f"{{{c}}}" for c in cols)
        return ""

    def _autosize_columns(self) -> None:
        """Auto-size columns to their content, then fit-to-width.

        Each column's renderer reports its natural width via ``GetBestSize``.
        Type/Text are capped so a single huge oracle text can't dominate. The
        results are stored in ``_natural_widths`` so :meth:`_fit_to_width` can
        re-expand columns when the viewport grows.
        """
        caps: dict[str, int] = {COL_TYPE: _MAX_TYPE_WIDTH, COL_TEXT: _MAX_TEXT_WIDTH}
        self._natural_widths = {}
        for idx, col_id in enumerate(TABLE_COLUMNS):
            self.grid.AutoSizeColumn(idx, setAsMin=False)
            size = self.grid.GetColSize(idx)
            cap = caps.get(col_id)
            if cap is not None and size > cap:
                size = cap
            self._natural_widths[idx] = size
        self._fit_to_width()

    def _fit_to_width(self) -> None:
        """Shrink Type/Text columns so the row fits the visible grid width.

        Starts from ``_natural_widths`` so a panel resize re-expands the
        columns back toward their natural widths. Other columns (mana, name,
        color) are never shrunk.
        """
        if not self._natural_widths:
            return
        # Reset to natural widths so we always work from the autosize baseline.
        for idx, w in self._natural_widths.items():
            if self.grid.GetColSize(idx) != w:
                self.grid.SetColSize(idx, w)
        # Reserve room for the fixed actions column so the data columns shrink
        # to fit beside it rather than pushing it off-screen.
        available = self.grid.GetClientSize().GetWidth() - _ACTIONS_COL_WIDTH
        if available <= 0:
            return
        total = sum(self._natural_widths.values())
        overflow = total - available
        if overflow <= 0:
            return
        type_idx = TABLE_COLUMNS.index(COL_TYPE)
        text_idx = TABLE_COLUMNS.index(COL_TEXT)
        type_size = self._natural_widths.get(type_idx, 0)
        text_size = self._natural_widths.get(text_idx, 0)
        type_room = max(0, type_size - _MIN_TYPE_WIDTH)
        text_room = max(0, text_size - _MIN_TEXT_WIDTH)
        total_room = type_room + text_room
        if total_room <= 0:
            return
        take = min(overflow, total_room)
        # Text has more filler than type, so distribute proportionally to room.
        text_take = int(round(take * text_room / total_room))
        type_take = take - text_take
        if text_size:
            self.grid.SetColSize(text_idx, text_size - text_take)
        if type_size:
            self.grid.SetColSize(type_idx, type_size - type_take)

    def _on_panel_resize(self, event: wx.SizeEvent) -> None:
        event.Skip()
        # Re-fit the type/text columns now that the visible width changed.
        wx.CallAfter(self._fit_to_width)

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
        if col < 0 or col == _ACTIONS_COL:
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
        if event.GetCol() == _ACTIONS_COL:
            self._handle_action_click(row, card["name"], event.GetPosition())
            return
        if self._selected_name and card["name"].lower() == self._selected_name.lower():
            self._selected_name = None
            self._apply_selection_highlight()
            self._on_select(None)
            return
        self._selected_name = card["name"]
        self._apply_selection_highlight()
        self._on_select(card)

    def _handle_action_click(self, row: int, name: str, pos: wx.Point) -> None:
        # Convert the event position (device coords on the grid window) into an
        # offset within the actions cell, then route to the matching callback.
        # CellToRect returns logical (scroll-aware, col-move-aware) coords, so
        # compare against the unscrolled click position.
        col = _ACTIONS_COL
        rect = self.grid.CellToRect(row, col)
        x_logical, _ = self.grid.CalcUnscrolledPosition(pos)
        x_in_cell = x_logical - rect.x
        action = action_slot_at(x_in_cell, rect.width)
        if action == TABLE_ACTION_ADD and self._on_delta:
            self._on_delta(name, 1)
        elif action == TABLE_ACTION_SUB and self._on_delta:
            self._on_delta(name, -1)
        elif action == TABLE_ACTION_REMOVE and self._on_remove:
            self._on_remove(name)

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
