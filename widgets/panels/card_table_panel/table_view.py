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

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
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

# Safety cap on raw oracle text stored in cells. The inline-symbol renderer
# does pixel-precise ellipsis truncation, but storing massive strings still
# costs memory in the grid table.
_MAX_TEXT_CHARS = 400

_MANA_CELL_PADDING = 4
_CELL_TEXT_PADDING = 4

# Mana/color icons are sized larger than text icons (by 4px) so they fill the
# row height without top/bottom padding, and rendered with no inter-icon gap
# so adjacent symbols sit flush against each other.
_CELL_ICON_SIZE_BONUS = 4
_MANA_ICON_GAP = 0

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

# Cache of (token, target-size) → wx.Bitmap shared across all renderer
# instances. Bitmap creation + scaling is expensive; oracle text repeats
# {T}/{G}/etc. across many rows.
_SCALED_BITMAP_CACHE: dict[tuple[str, int], wx.Bitmap | None] = {}


def _scaled_bitmap(
    factory: ManaIconFactory, token: str, size: int
) -> wx.Bitmap | None:
    """Return a bitmap for ``token`` rescaled to ``size`` px, cached."""
    key = (token.lower(), size)
    if key in _SCALED_BITMAP_CACHE:
        return _SCALED_BITMAP_CACHE[key]
    # Pull from the hires (pre-downscale) bitmap so we don't re-downscale an
    # already-downscaled image.
    base = factory.bitmap_for_symbol_hires(token) or factory.bitmap_for_symbol(token)
    if base is None:
        _SCALED_BITMAP_CACHE[key] = None
        return None
    if base.GetHeight() == size and base.GetWidth() == size:
        result = base
    else:
        img = base.ConvertToImage()
        img = img.Scale(size, size, wx.IMAGE_QUALITY_HIGH)
        result = wx.Bitmap(img)
    _SCALED_BITMAP_CACHE[key] = result
    return result


def _split_inline_symbols(text: str) -> list[tuple[str, str]]:
    """Split ``text`` into ``("text", str)`` / ``("sym", token)`` runs.

    ``{T}: Add {G}.`` → ``[("sym", "T"), ("text", ": Add "), ("sym", "G"), ("text", ".")]``.
    Unmatched ``{`` is treated as plain text.
    """
    runs: list[tuple[str, str]] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            end = text.find("}", i + 1)
            if end != -1:
                if buf:
                    runs.append(("text", "".join(buf)))
                    buf.clear()
                runs.append(("sym", text[i + 1 : end]))
                i = end + 1
                continue
        buf.append(ch)
        i += 1
    if buf:
        runs.append(("text", "".join(buf)))
    return runs


def _font_height(font: wx.Font) -> int:
    """Return the pixel line height of ``font`` using a probe DC."""
    bmp = wx.Bitmap(1, 1)
    dc = wx.MemoryDC(bmp)
    dc.SetFont(font)
    h = dc.GetCharHeight()
    dc.SelectObject(wx.NullBitmap)
    return max(10, h)


class _ManaIconCellRenderer(gridlib.GridCellRenderer):
    """Draws a cell as a horizontal row of mana-symbol bitmaps."""

    def __init__(
        self,
        icon_factory: ManaIconFactory,
        icon_size: int,
        gap: int = _MANA_ICON_GAP,
    ) -> None:
        super().__init__()
        self._factory = icon_factory
        self._icon_size = icon_size
        self._gap = gap

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
        max_x = rect.x + rect.width - _MANA_CELL_PADDING
        for idx, token in enumerate(tokens):
            bmp = _scaled_bitmap(self._factory, token, self._icon_size)
            if bmp is None:
                continue
            w = bmp.GetWidth()
            if x + w > max_x:
                break
            y = rect.y + (rect.height - bmp.GetHeight()) // 2
            dc.DrawBitmap(bmp, x, y, True)
            x += w
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
        return _ManaIconCellRenderer(self._factory, self._icon_size, self._gap)


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
            ell_w = dc.GetTextExtent(self._ELLIPSIS)[0]
            budget = max(0, available - ell_w)
            while text and dc.GetTextExtent(text)[0] > budget:
                text = text[:-1]
            text = (text + self._ELLIPSIS) if text else self._ELLIPSIS

        y = rect.y + max(0, (rect.height - dc.GetCharHeight()) // 2)
        dc.DrawText(text, rect.x + _CELL_TEXT_PADDING, y)

    def Clone(self) -> "_EllipsisStringRenderer":
        return _EllipsisStringRenderer()


class _InlineSymbolStringRenderer(gridlib.GridCellRenderer):
    """Draws text with inline ``{X}`` mana symbols, ellipsis-truncating overflow.

    AutoSizeColumn calls :meth:`GetBestSize` to compute the natural column
    width — symbols are sized as ``icon_size`` and text via the cell font.
    """

    _ELLIPSIS = "…"

    def __init__(self, icon_factory: ManaIconFactory, icon_size: int) -> None:
        super().__init__()
        self._factory = icon_factory
        self._icon_size = icon_size

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

        runs = _split_inline_symbols(grid.GetCellValue(row, col))

        x = rect.x + _CELL_TEXT_PADDING
        max_x = rect.x + rect.width - _CELL_TEXT_PADDING
        char_h = dc.GetCharHeight()
        y_text = rect.y + max(0, (rect.height - char_h) // 2)
        ell_w = dc.GetTextExtent(self._ELLIPSIS)[0]

        for kind, content in runs:
            if kind == "text":
                tw = dc.GetTextExtent(content)[0]
                if x + tw <= max_x:
                    dc.DrawText(content, x, y_text)
                    x += tw
                    continue
                # Truncate this run in place with an ellipsis suffix.
                budget = max(0, max_x - x - ell_w)
                truncated = content
                while truncated and dc.GetTextExtent(truncated)[0] > budget:
                    truncated = truncated[:-1]
                dc.DrawText(truncated + self._ELLIPSIS, x, y_text)
                return
            # Symbol run.
            bmp = _scaled_bitmap(self._factory, content, self._icon_size)
            if bmp is None:
                continue
            w = bmp.GetWidth()
            if x + w > max_x:
                if x + ell_w <= max_x:
                    dc.DrawText(self._ELLIPSIS, x, y_text)
                return
            y_bmp = rect.y + (rect.height - bmp.GetHeight()) // 2
            dc.DrawBitmap(bmp, x, y_bmp, True)
            x += w

    def GetBestSize(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        row: int,
        col: int,
    ) -> wx.Size:
        dc.SetFont(grid.GetDefaultCellFont())
        width = _CELL_TEXT_PADDING * 2
        for kind, content in _split_inline_symbols(grid.GetCellValue(row, col)):
            if kind == "text":
                width += dc.GetTextExtent(content)[0]
            else:
                width += self._icon_size
        char_h = dc.GetCharHeight()
        return wx.Size(width, max(char_h, self._icon_size))

    def Clone(self) -> "_InlineSymbolStringRenderer":
        return _InlineSymbolStringRenderer(self._factory, self._icon_size)


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
        # Natural widths populated by _autosize_columns; _fit_to_width starts
        # from these so resizing the panel wider re-expands the columns.
        self._natural_widths: dict[int, int] = {}

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
        self.grid.SetDefaultCellBackgroundColour(wx.Colour(*DARK_ALT))
        self.grid.SetDefaultCellTextColour(wx.Colour(*LIGHT_TEXT))
        self.grid.SetLabelBackgroundColour(wx.Colour(*DARK_BG))
        self.grid.SetLabelTextColour(wx.Colour(*SUBDUED_TEXT))
        self.grid.SetGridLineColour(wx.Colour(*DARK_BG))
        self.grid.SetSelectionBackground(wx.Colour(*DARK_ACCENT))
        self.grid.SetSelectionForeground(wx.Colour(*LIGHT_TEXT))

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
            renderer: gridlib.GridCellRenderer | None
            if col_id in (COL_MANA, COL_COLOR):
                renderer = _ManaIconCellRenderer(icon_factory, self._cell_icon_size)
            elif col_id == COL_TEXT:
                renderer = _InlineSymbolStringRenderer(icon_factory, self._cell_icon_size)
            elif col_id == COL_TYPE:
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
        available = self.grid.GetClientSize().GetWidth()
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
