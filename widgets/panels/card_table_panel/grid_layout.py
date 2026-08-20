"""Grid geometry for :class:`DeckGridView`.

Pure layout math — cell/grid constants plus the coordinate helpers that turn a
card index into a rectangle, a point into a card index, and a drag point into an
insertion slot. Nothing here touches the image cache, the canvas or any drawing;
it only reads ``self._cards`` / ``self._cols`` and calls scroll-window geometry
methods, so it is the lowest-risk band and is mixed in first.

This is the package's view-collaborator style: a thin mixin that the concrete
``DeckGridView`` inherits, with all instance state still declared in the view's
``__init__`` and ``wx.ScrolledWindow`` kept last in the MRO.
"""

from __future__ import annotations

from math import ceil

import wx

from utils.constants import (
    DECK_CARD_ACTION_BUTTON_SIZE,
    DECK_CARD_BUTTON_MARGIN,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
)

# Match the grid sizer's old geometry: DECK_CARD_WIDTH×HEIGHT cells with a
# GRID_GAP (== CardTablePanel.GRID_GAP) right/bottom margin between them.
_CARD_WIDTH = DECK_CARD_WIDTH
_CARD_HEIGHT = DECK_CARD_HEIGHT
_GAP = 8
_CELL_WIDTH = _CARD_WIDTH + _GAP
_CELL_HEIGHT = _CARD_HEIGHT + _GAP

_ACTION_GLYPHS = ("+", "−", "×")
_ACTION_SPACING = 2  # px gap between the drawn +/−/× hit-zones
_ACTION_BUTTON_RADIUS = 4

# Fallback column count before the window has a real client width to wrap to.
_DEFAULT_COLUMNS = 4

# Above this virtual width/height (px) we skip the cached full-content bitmap
# and fall back to direct culled drawing, so a pathologically large deck can't
# allocate a multi-hundred-MB canvas. Comfortably clears any real deck zone.
_MAX_CANVAS_PX = 20000


class GridLayoutMixin:
    """Pure grid geometry for :class:`DeckGridView`."""

    # ----- layout -----
    def _recompute_layout(self) -> None:
        client_w = self.GetClientSize().GetWidth()
        cols = max(1, client_w // _CELL_WIDTH) if client_w > 0 else self._cols
        self._cols = cols
        n = len(self._cards)
        rows = ceil(n / cols) if n else 0
        self.SetVirtualSize((cols * _CELL_WIDTH, rows * _CELL_HEIGHT))
        # Layout (column count / card count) changed — the cached image no
        # longer matches; rebuild it on the next paint.
        self._invalidate_canvas()

    def _card_rect(self, index: int) -> wx.Rect:
        cols = max(1, self._cols)
        row, col = divmod(index, cols)
        return wx.Rect(col * _CELL_WIDTH, row * _CELL_HEIGHT, _CARD_WIDTH, _CARD_HEIGHT)

    def _hit_test(self, point: wx.Point) -> int | None:
        cols = max(1, self._cols)
        if point.x < 0 or point.y < 0:
            return None
        col = point.x // _CELL_WIDTH
        row = point.y // _CELL_HEIGHT
        if col >= cols:
            return None
        idx = row * cols + col
        if 0 <= idx < len(self._cards) and self._card_rect(idx).Contains(point):
            return idx
        return None

    def _to_logical(self, screen_point: wx.Point) -> wx.Point:
        x, y = self.CalcUnscrolledPosition(screen_point)
        return wx.Point(x, y)

    def _ensure_visible(self, rect: wx.Rect) -> None:
        _ppu_x, ppu_y = self.GetScrollPixelsPerUnit()
        if ppu_y <= 0:
            return
        view_y = self.GetViewStart()[1] * ppu_y
        client_h = self.GetClientSize().GetHeight()
        if rect.y < view_y:
            self.Scroll(-1, rect.y // ppu_y)
        elif rect.y + rect.height > view_y + client_h:
            self.Scroll(-1, (rect.y + rect.height - client_h) // ppu_y + 1)

    # ----- action (+/−/×) hit-zones -----
    def _action_button_rects(self, card_rect: wx.Rect) -> list[wx.Rect]:
        btn_w, btn_h = DECK_CARD_ACTION_BUTTON_SIZE
        x = card_rect.x + DECK_CARD_BUTTON_MARGIN
        y = card_rect.y + card_rect.height - DECK_CARD_BUTTON_MARGIN - btn_h
        return [
            wx.Rect(x + i * (btn_w + _ACTION_SPACING), y, btn_w, btn_h)
            for i in range(len(_ACTION_GLYPHS))
        ]

    def _drop_index_at(self, point: wx.Point) -> int:
        """Insertion index in ``self._cards`` for a drop at ``point``.

        Cards snap to the nearest cell gap: the x within a cell decides whether
        the drop lands before or after that column, so dropping on the right
        half of a cell inserts after it.
        """
        cols = max(1, self._cols)
        n = len(self._cards)
        if n == 0:
            return 0
        row = max(0, point.y // _CELL_HEIGHT)
        col_f = point.x / _CELL_WIDTH
        col = int(max(0, min(cols, round(col_f))))
        idx = int(row) * cols + col
        return max(0, min(n, idx))
