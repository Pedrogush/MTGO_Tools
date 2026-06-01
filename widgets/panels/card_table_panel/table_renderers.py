"""Custom ``wx.grid`` cell renderers for the deck table view.

These stateless renderers paint the :class:`DeckTableView` grid:

* :class:`_ManaIconCellRenderer` paints the mana and color columns as a row of
  :class:`ManaIconFactory` bitmaps scaled to the cell font height.
* :class:`_EllipsisStringRenderer` draws the Name/Type columns, truncating with
  ``…`` when the content is wider than the cell.
* :class:`_InlineSymbolStringRenderer` draws oracle text with inline mana
  symbols (e.g. ``{T}: Add {G}.``).
* :class:`_ActionCellRenderer` draws the trailing ``+ − ×`` row controls.

All renderers share :func:`_paint_row_background`, which keeps cell backgrounds
at ``DARK_ALT`` and signals selection with a vertical accent bar painted on the
leftmost visible cell only.
"""

from __future__ import annotations

import wx
import wx.grid as gridlib

from utils.constants import DARK_ACCENT
from widgets.mana_icon_factory import ManaIconFactory, tokenize_mana_symbols

_MANA_CELL_PADDING = 4
_CELL_TEXT_PADDING = 4

# Width of the colored bar painted on the leftmost cell of a selected row.
# The bar is the only visible selection signal — cell backgrounds stay at
# DARK_ALT so the mana/color icons (which bake DARK_ALT into their bitmap
# corners) don't end up reading as "circle on top of a gray square on top of
# a blue row".
_SELECTION_BAR_WIDTH = 3

# Mana/color icons are rendered with no inter-icon gap so adjacent symbols sit
# flush against each other.
_MANA_ICON_GAP = 0

# Trailing, non-data "actions" column glyphs and width, rendered with the same
# +/-/x controls the grid view shows on a selected card.
_ACTION_GLYPHS = ("+", "−", "×")
_ACTIONS_COL_WIDTH = 66

# Cache of (token, target-size) → wx.Bitmap shared across all renderer
# instances. Bitmap creation + scaling is expensive; oracle text repeats
# {T}/{G}/etc. across many rows.
_SCALED_BITMAP_CACHE: dict[tuple[str, int], wx.Bitmap | None] = {}


def _scaled_bitmap(factory: ManaIconFactory, token: str, size: int) -> wx.Bitmap | None:
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


def _paint_row_background(
    grid: gridlib.Grid,
    dc: wx.DC,
    rect: wx.Rect,
    col: int,
    is_selected: bool,
) -> None:
    """Fill ``rect`` with the cell background, then overlay the selection bar.

    The cell background is always ``DARK_ALT`` regardless of selection state,
    so the mana/color icon bitmaps (which fill their corners with ``DARK_ALT``)
    blend cleanly into the row in both states. Selection is signalled by a
    vertical accent bar on the leftmost visible cell only.
    """
    dc.SetBrush(wx.Brush(grid.GetDefaultCellBackgroundColour()))
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.DrawRectangle(rect)
    if is_selected and grid.GetColPos(col) == 0:
        dc.SetBrush(wx.Brush(wx.Colour(*DARK_ACCENT)))
        dc.DrawRectangle(rect.x, rect.y, _SELECTION_BAR_WIDTH, rect.height)


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
        _paint_row_background(grid, dc, rect, col, isSelected)

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

    def Clone(self) -> _ManaIconCellRenderer:
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
        _paint_row_background(grid, dc, rect, col, isSelected)

        font = grid.GetDefaultCellFont()
        if isSelected:
            font = font.Bold()
        dc.SetFont(font)
        dc.SetTextForeground(grid.GetDefaultCellTextColour())

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

    def Clone(self) -> _EllipsisStringRenderer:
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
        _paint_row_background(grid, dc, rect, col, isSelected)
        font = grid.GetDefaultCellFont()
        if isSelected:
            font = font.Bold()
        dc.SetFont(font)
        dc.SetTextForeground(grid.GetDefaultCellTextColour())

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

    def Clone(self) -> _InlineSymbolStringRenderer:
        return _InlineSymbolStringRenderer(self._factory, self._icon_size)


class _ActionCellRenderer(gridlib.GridCellRenderer):
    """Draws the ``+ − ×`` row controls, each glyph centered in an equal slot."""

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
        _paint_row_background(grid, dc, rect, col, isSelected)
        dc.SetFont(grid.GetDefaultCellFont().Bold())
        dc.SetTextForeground(grid.GetDefaultCellTextColour())
        slot_w = rect.width / len(_ACTION_GLYPHS)
        char_h = dc.GetCharHeight()
        y = rect.y + max(0, (rect.height - char_h) // 2)
        for idx, glyph in enumerate(_ACTION_GLYPHS):
            tw = dc.GetTextExtent(glyph)[0]
            x = rect.x + int(slot_w * idx + (slot_w - tw) / 2)
            dc.DrawText(glyph, x, y)

    def GetBestSize(
        self,
        grid: gridlib.Grid,
        attr: gridlib.GridCellAttr,
        dc: wx.DC,
        row: int,
        col: int,
    ) -> wx.Size:
        return wx.Size(_ACTIONS_COL_WIDTH, grid.GetDefaultRowSize())

    def Clone(self) -> _ActionCellRenderer:
        return _ActionCellRenderer()
