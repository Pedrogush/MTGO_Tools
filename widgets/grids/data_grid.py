"""A read-only tabular view whose every pixel is ours.

Why not ``wx.ListCtrl``
-----------------------
Measured on wxWidgets 3.2.8 / wxPython 4.2.4, with Windows dark mode on:

* a **focused** ``wx.ListCtrl`` paints the selected row in the *system* accent
  (``#0078D7`` here) — a user setting, not a token of ours, and the same colour
  whatever the app's theme is;
* an **unfocused** one paints a hairline outline and no fill at all, which is the
  ~1.1:1 "selection" the UI review measured in Top Cards;
* ``SetItemBackgroundColour`` on the selected row is overpainted in both states,
  so there is no wx-level fix. Phase 2 measured this and moved the finding here.

``wx.dataview.DataViewListCtrl`` was tried too and is worse: it draws its own
alternate-row bands out of the light theme, so half the rows come back light grey
on a dark surface.

``wx.grid.Grid`` alone does not fix it either — with focus it honours
``SetSelectionBackground``, but **without focus it draws the selection in
``COLOR_BTNSHADOW`` (#A0A0A0), a light grey band, and ignores the colour you
set**. What does fix it is what the deck workspace's table view already does: a
cell renderer that fills its own background. wxGrid hands the whole cell to the
renderer, selection included, so the native fill never gets drawn.

So this is that renderer, generalised: per-column alignment, zebra striping and
the phase-2 selection token.

The header is ours too
----------------------
``wx.grid.Grid.SetColLabelAlignment`` is **grid-wide**, so it cannot right-align
a numeric column's header while leaving ``Card``'s alone — and a right-aligned
number under a centred header reads as two different columns. Overriding
``DrawColLabel`` is the documented C++ escape hatch and **wxPython never calls
it**: a subclass that counts its own invocations records zero after a full paint
(measured, wxPython 4.2.4). So the column labels are a plain ``wx.Panel`` drawn
by hand and scrolled in step with the grid, and the grid's own label row is
switched off with ``SetColLabelSize(0)``.
"""

from __future__ import annotations

from typing import NamedTuple

import wx
import wx.grid as gridlib

from utils.constants.theme import (
    BORDER_SUBTLE,
    SELECTION_BORDER,
    SELECTION_BORDER_WIDTH,
    SELECTION_FILLS,
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    SURFACE_RAISED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.constants.ui_layout import (
    GRID_CELL_PADDING,
    GRID_HEADER_HEIGHT,
    GRID_ROW_HEIGHT,
)

_SURFACES = {
    "base": SURFACE_BASE,
    "panel": SURFACE_PANEL,
    "alt": SURFACE_ALT,
    "raised": SURFACE_RAISED,
}

#: Zebra partner for each surface. One step along the surface scale, which is the
#: smallest difference the scale offers and exactly what row banding wants: enough
#: to track a row across eleven columns, not enough to read as a state.
_ZEBRA = {
    "base": SURFACE_PANEL,
    "panel": SURFACE_ALT,
    "alt": SURFACE_RAISED,
    "raised": SURFACE_ALT,
}


class GridColumn(NamedTuple):
    """One column's identity, geometry and alignment.

    ``align`` is ``wx.ALIGN_LEFT`` or ``wx.ALIGN_RIGHT`` and applies to the data
    *and* the header, because a right-aligned number under a centred header
    reads as two columns.
    """

    label: str
    width: int
    align: int = wx.ALIGN_LEFT
    tooltip: str = ""


class _CellRenderer(gridlib.GridCellRenderer):
    """Draws one cell: background, selection, zebra and aligned text."""

    def __init__(self, surface: str = "panel") -> None:
        super().__init__()
        self._surface = surface

    def _background(self, row: int, is_selected: bool) -> wx.Colour:
        if is_selected:
            return wx.Colour(*SELECTION_FILLS[self._surface])
        if row % 2:
            return wx.Colour(*_ZEBRA[self._surface])
        return wx.Colour(*_SURFACES[self._surface])

    def Draw(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        rect: wx.Rect,
        row: int,
        col: int,
        is_selected: bool,
    ) -> None:
        dc.SetBrush(wx.Brush(self._background(row, is_selected)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        if is_selected:
            # Fill alone is a 1.14:1 step off the zebra row beside it, which is
            # why phase 2's token is fill *plus* a stroke. Only the top and
            # bottom edges are drawn, so the stroke reads as one band across the
            # row rather than a box around each of eleven cells.
            dc.SetPen(wx.Pen(wx.Colour(*SELECTION_BORDER), SELECTION_BORDER_WIDTH))
            top = rect.y + SELECTION_BORDER_WIDTH // 2
            bottom = rect.y + rect.height - 1 - SELECTION_BORDER_WIDTH // 2
            dc.DrawLine(rect.x, top, rect.x + rect.width, top)
            dc.DrawLine(rect.x, bottom, rect.x + rect.width, bottom)

        dc.SetFont(attr.GetFont())
        dc.SetTextForeground(attr.GetTextColour())
        text = grid.GetCellValue(row, col)
        if not text:
            return
        horiz, _vert = attr.GetAlignment()
        dc.SetClippingRegion(rect)
        _draw_aligned_text(dc, text, rect, horiz)
        dc.DestroyClippingRegion()

    def GetBestSize(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        row: int,
        col: int,
    ) -> wx.Size:
        dc.SetFont(attr.GetFont())
        width, height = dc.GetTextExtent(grid.GetCellValue(row, col))
        return wx.Size(width + GRID_CELL_PADDING * 2, height)

    def Clone(self) -> _CellRenderer:
        return _CellRenderer(self._surface)


class _GridHeader(wx.Panel):
    """The column labels, drawn by hand so each can carry its column's alignment.

    Scrolls with the grid: the x offset comes from the grid's own
    ``CalcScrolledPosition``, so a horizontally scrolled table keeps its headers
    over their data.
    """

    def __init__(self, parent: wx.Window, grid: gridlib.Grid, surface: str) -> None:
        super().__init__(parent, size=(-1, GRID_HEADER_HEIGHT))
        self._grid = grid
        self._columns: list[GridColumn] = []
        self.SetBackgroundColour(wx.Colour(*_ZEBRA[surface]))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        # Required by the buffered paint DCs below: without it wxMSW leaves
        # the window's backing store untouched, and a panel that draws
        # nothing (an empty sparkline) shows whatever was last blitted
        # there -- observed as a deck-list row appearing inside the
        # archetype summary.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda _evt: None)

    def set_columns(self, columns: list[GridColumn]) -> None:
        self._columns = list(columns)
        self.Refresh()

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.BufferedPaintDC(self)
        width, height = self.GetClientSize()
        dc.SetBrush(wx.Brush(self.GetBackgroundColour()))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, width, height)

        dc.SetPen(wx.Pen(wx.Colour(*BORDER_SUBTLE)))
        dc.DrawLine(0, height - 1, width, height - 1)

        dc.SetFont(self.GetFont())
        dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
        for index, column in enumerate(self._columns):
            if index >= self._grid.GetNumberCols():
                break
            left = self._grid.CalcScrolledPosition(self._grid.GetColLeft(index), 0)[0]
            size = self._grid.GetColSize(index)
            if left + size < 0 or left > width:
                continue
            rect = wx.Rect(left, 0, size, height - 1)
            dc.SetClippingRegion(rect)
            _draw_aligned_text(dc, column.label, rect, column.align)
            dc.DestroyClippingRegion()


def _ellipsize(dc: wx.DC, text: str, available: int) -> str:
    """Trim ``text`` to ``available`` px, marking the cut with an ellipsis.

    Clipping alone hides the fact that a value was cut, which is what made the
    Formats column read as "truncates mid-word" -- "Legacy, Modern, Pauper," with
    no sign that anything followed.
    """
    if available <= 0 or dc.GetTextExtent(text)[0] <= available:
        return text
    ellipsis = "\u2026"
    trimmed = text
    while trimmed and dc.GetTextExtent(trimmed + ellipsis)[0] > available:
        trimmed = trimmed[:-1]
    return (trimmed.rstrip(" ,") + ellipsis) if trimmed else ellipsis


def _draw_aligned_text(dc: wx.DC, text: str, rect: wx.Rect, align: int) -> None:
    """Draw ``text`` inside ``rect``, honouring left/right/centre.

    Handles embedded newlines, which is how a header says "Main avg / when
    played" without needing a 130px column to say it on one line. ``DrawText``
    itself does not wrap, so the lines are laid out here.
    """
    if not text:
        return
    lines = text.split("\n")
    line_height = dc.GetCharHeight()
    block_height = line_height * len(lines)
    y = rect.y + max(0, (rect.height - block_height) // 2)
    available = rect.width - GRID_CELL_PADDING * 2
    for line in lines:
        line = _ellipsize(dc, line, available)
        width, _height = dc.GetTextExtent(line)
        if align == wx.ALIGN_RIGHT:
            x = rect.x + rect.width - GRID_CELL_PADDING - width
        elif align == wx.ALIGN_CENTRE:
            x = rect.x + (rect.width - width) // 2
        else:
            x = rect.x + GRID_CELL_PADDING
        dc.DrawText(line, x, y)
        y += line_height


class DataGrid(wx.Panel):
    """A read-only, own-drawn table with per-column alignment, header included."""

    def __init__(self, parent: wx.Window, *, surface: str = "panel") -> None:
        super().__init__(parent)
        self._surface = surface
        self._columns: list[GridColumn] = []

        base = wx.Colour(*_SURFACES[surface])
        self.SetBackgroundColour(base)

        self.grid = gridlib.Grid(self, style=wx.BORDER_NONE)
        self.grid.CreateGrid(0, 0)
        self.grid.EnableEditing(False)
        self.grid.EnableDragRowSize(False)
        self.grid.EnableDragColMove(False)
        self.grid.EnableDragColSize(False)
        self.grid.SetRowLabelSize(0)
        # The grid's own label row is off; _GridHeader draws it instead.
        self.grid.SetColLabelSize(0)
        self.grid.SetSelectionMode(gridlib.Grid.GridSelectRows)
        self.grid.SetDefaultRowSize(GRID_ROW_HEIGHT)
        self.grid.SetDefaultCellBackgroundColour(base)
        self.grid.SetDefaultCellTextColour(wx.Colour(*TEXT_PRIMARY))
        # No grid lines. Eleven vertical rules turn a table into a spreadsheet;
        # alignment and the zebra bands do the separating instead.
        self.grid.EnableGridLines(False)
        # Belt and braces: the renderer paints every cell, so neither of these
        # should ever be visible. They are set anyway because an unpainted region
        # (an empty grid, a partially scrolled row) falls back to them.
        self.grid.SetSelectionBackground(base)
        self.grid.SetSelectionForeground(wx.Colour(*TEXT_PRIMARY))
        self.grid.SetCellHighlightPenWidth(0)
        self.grid.SetCellHighlightROPenWidth(0)
        self.grid.SetBackgroundColour(base)
        self.grid.GetGridWindow().SetBackgroundColour(base)

        self.header = _GridHeader(self, self.grid, surface)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.header, 0, wx.EXPAND)
        sizer.Add(self.grid, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.grid.GetGridWindow().Bind(wx.EVT_SCROLLWIN, self._on_grid_scroll)
        self.grid.Bind(wx.EVT_SCROLLWIN, self._on_grid_scroll)

    def _on_grid_scroll(self, event: wx.ScrollWinEvent) -> None:
        event.Skip()
        # The scroll position is only current after the grid has handled the
        # event, so repaint on the next idle turn rather than inline.
        wx.CallAfter(self.header.Refresh)

    def set_columns(self, columns: list[GridColumn]) -> None:
        """Declare the columns. Clears any existing ones."""
        if self.grid.GetNumberCols():
            self.grid.DeleteCols(0, self.grid.GetNumberCols())
        self._columns = list(columns)
        self.grid.AppendCols(len(columns))
        for index, column in enumerate(columns):
            self.grid.SetColSize(index, column.width)
            attr = gridlib.GridCellAttr()
            attr.SetRenderer(_CellRenderer(self._surface))
            attr.SetAlignment(column.align, wx.ALIGN_CENTRE)
            attr.SetTextColour(wx.Colour(*TEXT_PRIMARY))
            self.grid.SetColAttr(index, attr)
        self.header.set_columns(self._columns)

    def set_rows(self, rows: list[list[str]]) -> None:
        """Replace every row. ``rows`` are already-formatted display strings."""
        if self.grid.GetNumberRows():
            self.grid.DeleteRows(0, self.grid.GetNumberRows())
        if rows:
            self.grid.AppendRows(len(rows))
            for row_index, values in enumerate(rows):
                for col_index, value in enumerate(values):
                    self.grid.SetCellValue(row_index, col_index, value)
        self.grid.ForceRefresh()
        self.header.Refresh()

    def column_at(self, x: int) -> int | None:
        """The column index under an x position in the header's coordinates."""
        unscrolled = self.grid.CalcUnscrolledPosition(wx.Point(x, 0)).x
        col = self.grid.XToCol(unscrolled)
        return col if col is not None and col >= 0 else None

    def total_column_width(self) -> int:
        """Sum of the declared column widths — what the table wants to be."""
        return sum(column.width for column in self._columns)
