"""Pile-view drag-and-drop command handlers.

The pile view's whole interaction model is a mouse drag -- pick copies up, drop
them into another column, or (since #991) past the rightmost one to make a
column of your own. None of that is reachable through the widget-clicking
commands, so a change to it could only ever be argued about rather than watched.

``pile_drag`` posts real ``wx.MouseEvent`` objects into the view's own event
handler from a **worker thread**, one per step, exactly the way ``sash_drag``
posts one ``SetSashPosition`` per step: the events go through the same binding
table a physical mouse's do, and spacing them out lets the UI thread run the
paints between them, so a background video grab sees the frames a real drag
produces. It returns as soon as the gesture is scheduled.

``pile_state`` reads back what the columns actually are afterwards -- their
labels, their counts and their geometry -- which is what turns "the card moved"
from a claim into a measurement.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import wx

from widgets.panels.card_table_panel.pile_view import (
    VIRTUAL_PILE_LABEL,
    DeckPileView,
)

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


def _mouse_event(event_type: int, position: wx.Point, *, left_down: bool) -> wx.MouseEvent:
    """A mouse event carrying the fields the pile view's handlers read."""
    event = wx.MouseEvent(event_type)
    event.SetPosition(position)
    event.SetLeftDown(left_down)
    return event


class PileDragMixin(_Base):
    """Commands for inspecting and dragging the pile view's columns."""

    def _pile_view(self, zone: str) -> DeckPileView | None:
        table = getattr(self.frame, f"{zone}_table", None)
        if table is None:
            return None
        view = getattr(table, "pile_view", None)
        return view if isinstance(view, DeckPileView) else None

    def _show_pile_view(self, zone: str) -> DeckPileView | None:
        """Bring ``zone``'s pile view to the front so it actually paints."""
        table = getattr(self.frame, f"{zone}_table", None)
        if table is None:
            return None
        notebook = getattr(self.frame, "deck_tabs", None)
        if notebook is not None:
            for i in range(notebook.GetPageCount()):
                if notebook.GetPage(i) is table:
                    notebook.SetSelection(i)
                    break
        if hasattr(table, "set_view_mode"):
            table.set_view_mode("pile", persist=False)
        try:
            if self.frame.IsIconized():
                self.frame.Iconize(False)
            self.frame.Raise()
        except Exception:
            pass
        return self._pile_view(zone)

    def _handle_pile_state(self, zone: str = "main") -> dict[str, Any]:
        """Report every pile column: label, copy count, geometry, members.

        ``virtual`` marks a column the user made by dropping past the rightmost
        one (#991); those carry no bucket label, so ``label`` is empty for them.
        """
        view = self._pile_view(zone)
        if view is None:
            return {"error": f"No pile view for zone: {zone}"}
        view_x, view_y = view.GetViewStart()
        piles: list[dict[str, Any]] = []
        for index, (label, members) in enumerate(view._piles):
            header = view._pile_header_rect(index)
            piles.append(
                {
                    "index": index,
                    "label": label,
                    "virtual": label == VIRTUAL_PILE_LABEL,
                    "count": len(members),
                    "x": header.x,
                    "client_x": header.x - view_x,
                    "names": [entry["name"] for entry in members],
                }
            )
        return {
            "zone": zone,
            "piles": piles,
            "view_start": [view_x, view_y],
            "client_size": list(view.GetClientSize()),
            "virtual_size": list(view.GetVirtualSize()),
            "content_width": view.scroll_content_width(),
        }

    def _handle_pile_drag(
        self,
        zone: str = "main",
        pile: int = 0,
        member: int = -1,
        to_x: int | None = None,
        to_y: int | None = None,
        dx: int = 0,
        dy: int = 0,
        steps: int = 12,
        interval_ms: float = 40.0,
    ) -> dict[str, Any]:
        """Drag one copy out of ``pile`` and drop it somewhere else.

        ``member`` indexes the copy inside the pile (``-1`` = the bottom card,
        the fully visible one). The destination is either absolute *client*
        coordinates (``to_x``/``to_y``) or an offset from the grab point
        (``dx``/``dy``). Returns once the gesture is scheduled.
        """
        view = self._show_pile_view(zone)
        if view is None:
            return {"started": False, "error": f"No pile view for zone: {zone}"}
        piles = view._piles
        if not 0 <= pile < len(piles):
            return {"started": False, "error": f"No pile {pile} (have {len(piles)})"}
        members = piles[pile][1]
        if not members:
            return {"started": False, "error": f"Pile {pile} is empty"}
        member_idx = member if member >= 0 else len(members) + member
        if not 0 <= member_idx < len(members):
            return {"started": False, "error": f"No member {member} in pile {pile}"}

        rect = view._card_rect(pile, member_idx, len(members))
        view_x, view_y = view.GetViewStart()
        # Grab inside the copy's *visible* band: every card but the bottom one
        # shows only its top name strip, and pressing below that hits the card
        # stacked over it instead.
        grab = wx.Point(rect.x + rect.width // 2 - view_x, rect.y + 12 - view_y)
        target = wx.Point(
            grab.x + int(dx) if to_x is None else int(to_x),
            grab.y + int(dy) if to_y is None else int(to_y),
        )
        steps = max(1, int(steps))

        def gesture() -> None:
            wx.CallAfter(
                view.GetEventHandler().ProcessEvent,
                _mouse_event(wx.wxEVT_LEFT_DOWN, grab, left_down=True),
            )
            time.sleep(max(0.0, interval_ms / 1000.0))
            for i in range(1, steps + 1):
                frac = i / steps
                point = wx.Point(
                    int(grab.x + (target.x - grab.x) * frac),
                    int(grab.y + (target.y - grab.y) * frac),
                )
                wx.CallAfter(
                    view.GetEventHandler().ProcessEvent,
                    _mouse_event(wx.wxEVT_MOTION, point, left_down=True),
                )
                time.sleep(max(0.0, interval_ms / 1000.0))
            wx.CallAfter(
                view.GetEventHandler().ProcessEvent,
                _mouse_event(wx.wxEVT_LEFT_UP, target, left_down=False),
            )

        threading.Thread(target=gesture, daemon=True).start()
        return {
            "started": True,
            "zone": zone,
            "pile": pile,
            "member": member_idx,
            "name": members[member_idx]["name"],
            "from": [grab.x, grab.y],
            "to": [target.x, target.y],
            "steps": steps,
            "interval_ms": interval_ms,
        }
