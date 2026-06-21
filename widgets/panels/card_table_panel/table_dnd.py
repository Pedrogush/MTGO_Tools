"""Drag-to-reorder controller for :class:`DeckTableView`.

A sibling to :class:`MarqueeController`: the table view forwards its grid-window
mouse events here and this owns the drag-to-reorder gesture's state machine,
mouse capture and the wx.Overlay insertion line. A reorder rearranges rows
visually only — zone quantities never change, so the rearranged order lives in
the view's ``_rows`` until the next sort / set_cards (issue #779).

The view supplies a target ``grid``/``grid_window`` plus a small set of
callbacks so the controller can read the live row list, map a name set to its
visual order, hand off a cross-zone drop, and ask the view to re-populate after
a within-zone reorder. The controller keeps the row list itself (the same
coupling :mod:`marquee` accepts) so the view delegates the whole gesture.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.grid as gridlib

from utils.constants import DARK_ACCENT

# Pointer travel (logical px) before a primed press becomes an active drag, so a
# plain click that wobbles slightly still selects rather than reorders.
_DRAG_THRESHOLD = 4


class TableDragController:
    """Drives one table view's drag-to-reorder gesture.

    The view supplies:

    * ``grid`` / ``grid_window`` — the wx grid and its inner window (the surface
      rows are drawn on and the one that owns mouse capture + the overlay).
    * ``rows()`` — the live display-order list of card dicts.
    * ``names_in_visual_order(names)`` — ``names`` in current top-to-bottom order.
    * ``on_zone_transfer(names, screen_point)`` — optional; move ``names`` to the
      other zone, returning True if it handled the drop.
    * ``on_reorder(new_rows)`` — apply a within-zone reorder; the view stores the
      new order and re-populates the grid.
    """

    def __init__(
        self,
        grid: gridlib.Grid,
        grid_window: wx.Window,
        *,
        rows: Callable[[], list[dict[str, Any]]],
        names_in_visual_order: Callable[[set[str]], list[str]],
        on_reorder: Callable[[list[dict[str, Any]]], None],
        on_zone_transfer: Callable[[list[str], wx.Point], bool] | None = None,
    ) -> None:
        self._grid = grid
        self._grid_window = grid_window
        self._rows = rows
        self._names_in_visual_order = names_in_visual_order
        self._on_reorder = on_reorder
        self._on_zone_transfer = on_zone_transfer

        # Drag-to-reorder state. ``_press`` is the logical press point (set once
        # a drag is primed); ``_active`` flips once the pointer clears the
        # threshold; ``_names`` is the dragged set in visual order; ``_drop_row``
        # is the current insertion index.
        self._press: wx.Point | None = None
        self._active = False
        self._names: list[str] = []
        self._drop_row: int | None = None
        # Insertion-line feedback is drawn over the native grid with an overlay so
        # it survives the grid's own repaints without us owning its paint cycle.
        self._overlay = wx.Overlay()

    @property
    def active(self) -> bool:
        return self._active

    # ----- lifecycle -----
    def prime(self, press_logical: wx.Point, selected_names: set[str]) -> None:
        """Prime a potential drag (begins once the pointer moves past threshold)."""
        self._press = press_logical
        self._names = self._names_in_visual_order(selected_names)
        if not self._grid_window.HasCapture():
            self._grid_window.CaptureMouse()

    def update(self, client_point: wx.Point) -> None:
        """Advance the drag from a motion event while the button is held.

        Returns nothing; once a primed press clears the threshold the drag goes
        active and the insertion line tracks the cursor.
        """
        if self._press is None:
            return
        x, y = self._grid.CalcUnscrolledPosition(client_point)
        if not self._active and (
            abs(x - self._press.x) > _DRAG_THRESHOLD or abs(y - self._press.y) > _DRAG_THRESHOLD
        ):
            self._active = True
        if self._active:
            self._drop_row = self._drop_row_at(y)
            self._draw_drop_line(self._drop_row)

    def finish(self, client_point: wx.Point) -> None:
        """Commit an active drag: zone-transfer the cards or reorder in place."""
        # A drop over the other zone's pane moves the cards there; otherwise it's
        # a within-zone reorder.
        transferred = False
        if self._on_zone_transfer is not None:
            transferred = self._on_zone_transfer(
                self._names, self._grid_window.ClientToScreen(client_point)
            )
        if not transferred:
            _x, y = self._grid.CalcUnscrolledPosition(client_point)
            self._perform_drop(self._drop_row_at(y))
        self.reset()

    @property
    def primed(self) -> bool:
        return self._press is not None

    def clear_press(self) -> None:
        """Drop a primed-but-not-active press (a plain click that never moved)."""
        self._press = None
        self._names = []

    def reset(self) -> None:
        """Tear the gesture down and clear the overlay."""
        self._press = None
        self._active = False
        self._names = []
        self._drop_row = None
        self._overlay.Reset()
        self._grid_window.Refresh()

    # ----- internals -----
    def _drop_row_at(self, y_logical: int) -> int:
        """Insertion row index for a drop at logical y (before the row whose
        midpoint sits below the cursor)."""
        rows = self._rows()
        n = len(rows)
        for idx in range(n):
            rect = self._grid.CellToRect(idx, 0)
            if y_logical < rect.y + rect.height / 2:
                return idx
        return n

    def _perform_drop(self, insert_row: int) -> None:
        """Reorder the rows so the dragged rows land at ``insert_row``.

        Visual rearrangement only; zone quantities are untouched and nothing is
        reported upward. The new order is handed to ``on_reorder``.
        """
        if not self._names:
            return
        rows = self._rows()
        dragged = set(self._names)
        before = sum(1 for c in rows[:insert_row] if c["name"] in dragged)
        insert_row -= before
        order = {name: i for i, name in enumerate(self._names)}
        moved = sorted(
            (c for c in rows if c["name"] in dragged),
            key=lambda c: order.get(c["name"], 0),
        )
        if not moved:
            return
        kept = [c for c in rows if c["name"] not in dragged]
        insert_row = max(0, min(len(kept), insert_row))
        self._on_reorder(kept[:insert_row] + moved + kept[insert_row:])

    def _draw_drop_line(self, insert_row: int) -> None:
        """Draw the insertion line over the grid at ``insert_row`` via overlay."""
        rows = self._rows()
        n = len(rows)
        if n == 0:
            return
        if insert_row < n:
            rect = self._grid.CellToRect(insert_row, 0)
            logical_y = rect.y
        else:
            rect = self._grid.CellToRect(n - 1, 0)
            logical_y = rect.GetBottom()
        _x, device_y = self._grid.CalcScrolledPosition(0, logical_y)
        dc = wx.ClientDC(self._grid_window)
        odc = wx.DCOverlay(self._overlay, dc)
        odc.Clear()
        dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 3))
        width = self._grid_window.GetClientSize().GetWidth()
        dc.DrawLine(0, device_y, width, device_y)
        del odc
