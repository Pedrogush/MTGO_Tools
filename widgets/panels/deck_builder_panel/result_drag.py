"""Drag a card-search result onto the mainboard or sideboard (issue #1033).

The deck zones already accept drops: a card view drags cards across by holding
the mouse itself and, on release, offering the *screen point* to the frame,
which hit-tests the zone panes (``_handle_zone_transfer``, #781). This is the
same gesture with a different source, so it uses the same mechanism rather than
OLE drag-and-drop: the results list holds the mouse, and on release it hands the
card name and the screen point to the frame, which resolves the zone with the
same hit test and adds the copy through the card search's one add route -- the
route that refuses while a sideboard guide is being recorded.

Two presses can start a drag, and they are detected differently because the
native list treats them differently:

* **An unselected row.** The press goes to ``SysListView32``, which selects the
  row and runs its own drag detection against the system drag rectangle
  (``SM_CXDRAG`` / ``SM_CYDRAG``). Only when the pointer leaves it does the list
  send ``LVN_BEGINDRAG`` -- wx's ``EVT_LIST_BEGIN_DRAG`` -- so a plain click and
  a double-click never reach this module at all.
* **The row that is already selected.** A press there has always cleared the
  selection, and the panel swallows it before the native list sees it, so no
  ``LVN_BEGINDRAG`` can follow. Here the controller primes the press itself and
  applies the same system threshold: past it, the drag begins; released inside
  it, the press is the click it always was and the selection clears -- on
  release rather than on press, which is the only observable difference.

The controller never mutates a deck. ``on_drop`` decides what a drop means.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

#: Used when the system drag metrics cannot be read (``GetMetric`` returns -1).
#: Matches the Windows default and the card views' own ``_DRAG_THRESHOLD``.
_FALLBACK_DRAG_THRESHOLD = 4


def system_drag_threshold() -> tuple[int, int]:
    """The pointer travel, in pixels per axis, before a press becomes a drag.

    ``wx.SYS_DRAG_X`` / ``wx.SYS_DRAG_Y`` are ``SM_CXDRAG`` / ``SM_CYDRAG`` on
    MSW -- the same rectangle the native list's own drag detection uses, so both
    ways of starting a drag from the results list need the same travel.
    """
    x = wx.SystemSettings.GetMetric(wx.SYS_DRAG_X)
    y = wx.SystemSettings.GetMetric(wx.SYS_DRAG_Y)
    return (
        x if x > 0 else _FALLBACK_DRAG_THRESHOLD,
        y if y > 0 else _FALLBACK_DRAG_THRESHOLD,
    )


class SearchResultDragController:
    """Owns the results list's drag-a-card gesture.

    The panel supplies:

    * ``card_at(index)`` -- the result dict behind a row, or ``None``.
    * ``zone_at(screen_point)`` -- the deck zone a drop there would land in, or
      ``None``; used only for the pointer feedback while the drag is live.
    * ``on_drop(name, screen_point)`` -- commit a release; returns whether a card
      was added.
    * ``on_click_selected(index)`` -- a press on the selected row that never
      became a drag (the list's click-to-deselect).
    """

    def __init__(
        self,
        list_ctrl: wx.ListCtrl,
        *,
        card_at: Callable[[int], dict[str, Any] | None],
        zone_at: Callable[[wx.Point], str | None],
        on_drop: Callable[[str, wx.Point], bool],
        on_click_selected: Callable[[int], None],
    ) -> None:
        self._list = list_ctrl
        self._card_at = card_at
        self._zone_at = zone_at
        self._on_drop = on_drop
        self._on_click_selected = on_click_selected

        # A press on the selected row, waiting to find out whether it is a click
        # or the start of a drag (client coordinates of the press).
        self._press: wx.Point | None = None
        self._press_index: int = wx.NOT_FOUND
        # The card being dragged, once a drag is live.
        self._name: str | None = None

    @property
    def primed(self) -> bool:
        return self._press is not None

    @property
    def active(self) -> bool:
        return self._name is not None

    @property
    def dragged_name(self) -> str | None:
        return self._name

    # ----- starting -----
    def prime(self, index: int, client_point: wx.Point) -> None:
        """Hold a press on the selected row until it is a click or a drag."""
        self._press = wx.Point(client_point)
        self._press_index = index
        self._capture()

    def begin(self, index: int) -> bool:
        """Start dragging the card on row ``index``; returns whether it started."""
        card = self._card_at(index)
        name = card.get("name") if card else None
        self._press = None
        self._press_index = wx.NOT_FOUND
        if not name:
            self._release()
            return False
        self._name = name
        self._capture()
        self._show_feedback(None)
        return True

    # ----- mouse events, forwarded by the panel (each returns "handled") -----
    def handle_motion(self, event: wx.MouseEvent) -> bool:
        if self.active:
            self._show_feedback(self._list.ClientToScreen(event.GetPosition()))
            return True
        if not self.primed:
            return False
        assert self._press is not None
        pos = event.GetPosition()
        limit_x, limit_y = system_drag_threshold()
        if abs(pos.x - self._press.x) > limit_x or abs(pos.y - self._press.y) > limit_y:
            if self.begin(self._press_index):
                self._show_feedback(self._list.ClientToScreen(pos))
        return True

    def handle_left_up(self, event: wx.MouseEvent) -> bool:
        if self.active:
            name = self._name
            screen_point = self._list.ClientToScreen(event.GetPosition())
            self._finish()
            assert name is not None
            self._on_drop(name, screen_point)
            return True
        if self.primed:
            index = self._press_index
            self._finish()
            self._on_click_selected(index)
            return True
        return False

    def cancel(self) -> None:
        """Abandon the gesture (Escape, lost capture) without dropping anything."""
        self._finish()

    # ----- internals -----
    def _finish(self) -> None:
        was_active = self.active
        self._press = None
        self._press_index = wx.NOT_FOUND
        self._name = None
        self._release()
        if was_active:
            wx.SetCursor(wx.STANDARD_CURSOR)

    def _capture(self) -> None:
        if not self._list.HasCapture():
            self._list.CaptureMouse()

    def _release(self) -> None:
        if self._list.HasCapture():
            self._list.ReleaseMouse()

    def _show_feedback(self, screen_point: wx.Point | None) -> None:
        """Say with the pointer whether a release here would add the card.

        Set process-wide rather than on the list: the pointer is over the deck
        zones for most of the gesture, and while the list holds the capture
        Windows sends no ``WM_SETCURSOR`` to anything, so nothing resets it.
        """
        droppable = screen_point is not None and self._zone_at(screen_point) is not None
        wx.SetCursor(wx.Cursor(wx.CURSOR_HAND if droppable else wx.CURSOR_NO_ENTRY))


__all__ = ["SearchResultDragController", "system_drag_threshold"]
