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
from widgets.panels.card_table_panel.marquee import MarqueeController
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
    sort_table_rows,
)
from widgets.panels.card_table_panel.table_columns import (
    COLUMN_WIDTH_CAPS,
    cell_text,
    fit_to_width,
)
from widgets.panels.card_table_panel.table_dnd import TableDragController
from widgets.panels.card_table_panel.table_renderers import (
    _ACTIONS_COL_WIDTH,
    _ActionCellRenderer,
    _EllipsisStringRenderer,
    _font_height,
    _InlineSymbolStringRenderer,
    _ManaIconCellRenderer,
)

# Mana/color icons are sized larger than text icons (by 4px) so they fill the
# row height without top/bottom padding.
_CELL_ICON_SIZE_BONUS = 4

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
        on_zone_transfer: Callable[[list[str], wx.Point], bool] | None = None,
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
        self._on_zone_transfer = on_zone_transfer

        self._cards: list[dict[str, Any]] = []
        self._rows: list[dict[str, Any]] = []  # cards in current display order
        self._sort_column: str = COL_NAME
        self._sort_descending: bool = False
        # Multi-selection by card name; a single click selects exactly one row,
        # a marquee can select several. Native row selection renders the set.
        self._selected_names: set[str] = set()
        self._hover_row: int = -1
        self._needs_autosize: bool = True
        # Suppress the panel's set_selected() echo while we report our own
        # (possibly multi-) selection, so an echoed None can't wipe the set.
        self._suppress_set_selected: bool = False
        self._marquee_base: set[str] | None = None
        # Drag-to-reorder state lives in the controller (issue #779); a reorder
        # rearranges rows visually only, so the arranged order lands back in
        # self._rows via the on_reorder callback until the next sort / set_cards.
        self._manual_overrides = False
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

        # Rubber-band selection lives on the grid's inner window (the surface the
        # rows are drawn on and the one that carries the scroll offset).
        grid_window = self.grid.GetGridWindow()
        self._grid_window = grid_window
        self._marquee = MarqueeController(
            grid_window,
            to_logical=self._to_logical,
            on_begin=self._marquee_begin,
            on_select=self._marquee_select,
            on_finish=self._marquee_finish,
        )
        self._drag = TableDragController(
            self.grid,
            grid_window,
            rows=lambda: self._rows,
            names_in_visual_order=self._names_in_visual_order,
            on_reorder=self._apply_reorder,
            on_zone_transfer=self._on_zone_transfer,
        )

        self.grid.Bind(gridlib.EVT_GRID_LABEL_LEFT_CLICK, self._on_header_click)
        self.grid.Bind(gridlib.EVT_GRID_SELECT_CELL, self._on_cell_select)
        grid_window.Bind(wx.EVT_LEFT_DOWN, self._on_grid_left_down)
        grid_window.Bind(wx.EVT_LEFT_UP, self._on_grid_left_up)
        grid_window.Bind(wx.EVT_MOTION, self._on_grid_motion)
        grid_window.Bind(wx.EVT_LEAVE_WINDOW, self._on_grid_leave)
        grid_window.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_grid_capture_lost)
        self.Bind(wx.EVT_SIZE, self._on_panel_resize)

    # ----- public API consumed by CardTablePanel -----
    def set_cards(self, cards: list[dict[str, Any]]) -> None:
        self._cards = list(cards)
        # Content changed — recompute column widths from the new data, and drop
        # any manual reorder / in-flight drag (the new content re-sorts).
        self._needs_autosize = True
        self._manual_overrides = False
        self._drag.reset()
        self._refresh()

    def set_selected(self, name: str | None) -> None:
        # Ignored while we broadcast our own selection (the panel echoes it back
        # and a bare name can't represent a multi-select set).
        if self._suppress_set_selected:
            return
        self._selected_names = {name} if name else set()
        self._apply_selection_highlight()

    def get_selected_name(self) -> str | None:
        if len(self._selected_names) != 1:
            return None
        return next(iter(self._selected_names))

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
        # An explicit (column) sort supersedes any manual drag arrangement.
        self._rows = sort_table_rows(
            self._cards, self._get_metadata, self._sort_column, self._sort_descending
        )
        self._populate_grid()
        if self._needs_autosize and self.grid.GetNumberRows() > 0:
            self._autosize_columns()
            self._needs_autosize = False

    def _populate_grid(self) -> None:
        """Render ``self._rows`` into the grid in their current order (no sort)."""
        self.grid.BeginBatch()
        try:
            current = self.grid.GetNumberRows()
            needed = len(self._rows)
            if needed > current:
                self.grid.AppendRows(needed - current)
            elif needed < current:
                self.grid.DeleteRows(needed, current - needed)
            for row_idx, card in enumerate(self._rows):
                meta = self._get_metadata(card["name"]) or {}
                for col_idx, col_id in enumerate(TABLE_COLUMNS):
                    self.grid.SetCellValue(row_idx, col_idx, cell_text(card, meta, col_id))
            self._apply_selection_highlight()
            self._update_sort_indicator()
        finally:
            self.grid.EndBatch()

    def _autosize_columns(self) -> None:
        """Auto-size columns to their content, then fit-to-width.

        Each column's renderer reports its natural width via ``GetBestSize``.
        Type/Text are capped so a single huge oracle text can't dominate. The
        results are stored in ``_natural_widths`` so :meth:`_fit_to_width` can
        re-expand columns when the viewport grows.
        """
        self._natural_widths = {}
        for idx, col_id in enumerate(TABLE_COLUMNS):
            self.grid.AutoSizeColumn(idx, setAsMin=False)
            size = self.grid.GetColSize(idx)
            cap = COLUMN_WIDTH_CAPS.get(col_id)
            if cap is not None and size > cap:
                size = cap
            self._natural_widths[idx] = size
        self._fit_to_width()

    def _fit_to_width(self) -> None:
        """Shrink Type/Text columns so the row fits the visible grid width.

        Starts from ``_natural_widths`` so a panel resize re-expands the
        columns back toward their natural widths. Other columns (mana, name,
        color) are never shrunk. The proportional-shrink math lives in
        :func:`table_columns.fit_to_width`; this only applies the result.
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
        sizes = fit_to_width(
            self._natural_widths,
            available,
            TABLE_COLUMNS.index(COL_TYPE),
            TABLE_COLUMNS.index(COL_TEXT),
        )
        for idx, size in sizes.items():
            self.grid.SetColSize(idx, size)

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
        if not self._selected_names:
            return
        wanted = {n.lower() for n in self._selected_names}
        first = True
        for idx, card in enumerate(self._rows):
            if card["name"].lower() in wanted:
                self.grid.SelectRow(idx, addToSelected=not first)
                if first:
                    self.grid.MakeCellVisible(idx, 0)
                    first = False

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
        self._manual_overrides = False
        self._refresh()

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
        if self._marquee.active:
            self._marquee.update(event.GetPosition())
            return
        if self._drag.primed and event.LeftIsDown():
            self._drag.update(event.GetPosition())
            return
        if self._selected_names or self._on_hover is None:
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

    # ----- rubber-band marquee -----
    def begin_marquee_at_screen(self, screen_point: wx.Point, *, additive: bool = False) -> None:
        """Start a marquee from anywhere in the app (e.g. the frame background)."""
        self._marquee.begin_at_screen(screen_point, additive=additive)

    def _on_grid_left_down(self, event: wx.MouseEvent) -> None:
        """Own every press on the grid surface.

        Not skipping to the native grid is what suppresses its press-drag
        range-select (the "selects everything from the top down" bug, #779): a
        press on a row selects exactly that row (Shift/Ctrl toggle a set) and
        primes a drag-to-reorder; a press below the rows starts a marquee.
        """
        x, y = self.grid.CalcUnscrolledPosition(event.GetPosition())
        row = self.grid.YToRow(y)
        if row == wx.NOT_FOUND or not (0 <= row < len(self._rows)):
            self._marquee.begin(event.GetPosition(), additive=event.ShiftDown())
            return

        card = self._rows[row]
        name = card["name"]
        if self.grid.XToCol(x) == _ACTIONS_COL:
            # A +/-/x click edits the quantity; never selects or starts a drag.
            self._handle_action_click(row, name, event.GetPosition())
            return

        if event.ShiftDown() or event.ControlDown():
            if name in self._selected_names:
                self._selected_names.discard(name)
            else:
                self._selected_names.add(name)
            self._apply_selection_highlight()
            self._notify_selection_for_set()
        elif self._selected_names == {name}:
            # Second click on the only selected row clears it; no drag.
            self._selected_names = set()
            self._apply_selection_highlight()
            self._notify_selection(None)
            return
        elif name not in self._selected_names:
            self._selected_names = {name}
            self._apply_selection_highlight()
            self._notify_selection(card)

        # Prime a potential drag-to-reorder (begins once the pointer moves).
        self._drag.prime(wx.Point(x, y), self._selected_names)

    def _on_grid_left_up(self, event: wx.MouseEvent) -> None:
        if self._marquee.active:
            self._marquee.finish()
            return
        if self._grid_window.HasCapture():
            self._grid_window.ReleaseMouse()
        if self._drag.active:
            self._drag.finish(event.GetPosition())
            return
        self._drag.clear_press()
        event.Skip()

    def _on_grid_capture_lost(self, _event: wx.MouseCaptureLostEvent) -> None:
        self._marquee.cancel()
        self._drag.reset()

    # ----- drag-to-reorder -----
    def _names_in_visual_order(self, names: set[str]) -> list[str]:
        """Return ``names`` in current top-to-bottom row order."""
        return [card["name"] for card in self._rows if card["name"] in names]

    def _apply_reorder(self, new_rows: list[dict[str, Any]]) -> None:
        """Adopt a drag-reordered row list and re-render (issue #779).

        Visual rearrangement only; zone quantities are untouched and nothing is
        reported upward. Persists until the next sort / set_cards.
        """
        self._rows = new_rows
        self._manual_overrides = True
        self._populate_grid()

    def _notify_selection_for_set(self) -> None:
        if len(self._selected_names) == 1:
            self._notify_selection(self._card_for(next(iter(self._selected_names))))
        else:
            self._notify_selection(None)

    def _to_logical(self, client_point: wx.Point) -> wx.Point:
        x, y = self.grid.CalcUnscrolledPosition(client_point)
        return wx.Point(x, y)

    def _marquee_begin(self, additive: bool) -> None:
        if not additive and self._selected_names:
            self._selected_names = set()
            self._apply_selection_highlight()
            self._notify_selection(None)
        self._marquee_base = set(self._selected_names)

    def _marquee_select(self, rect: wx.Rect) -> None:
        chosen: set[str] = set(self._marquee_base or ())
        for idx, card in enumerate(self._rows):
            row_rect = self.grid.CellToRect(idx, 0)
            # Full-row selection: a row is in the box when their vertical spans
            # overlap (the horizontal position within the row is irrelevant).
            if rect.GetTop() <= row_rect.GetBottom() and rect.GetBottom() >= row_rect.GetTop():
                chosen.add(card["name"])
        if chosen != self._selected_names:
            self._selected_names = chosen
            self._apply_selection_highlight()
            # One row chosen reports that card; several (or none) report None so
            # the inspector falls back to hover, mirroring the other views.
            if len(chosen) == 1:
                self._notify_selection(self._card_for(next(iter(chosen))))
            else:
                self._notify_selection(None)

    def _marquee_finish(self) -> None:
        self._marquee_base = None

    def _card_for(self, name: str) -> dict[str, Any] | None:
        for card in self._rows:
            if card["name"] == name:
                return card
        return None

    def _notify_selection(self, card: dict[str, Any] | None) -> None:
        """Report selection to the panel, guarding the set_selected echo."""
        self._suppress_set_selected = True
        try:
            self._on_select(card)
        finally:
            self._suppress_set_selected = False
