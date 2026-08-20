"""Splitter-sash command handlers.

The deck workspace's mainboard/sideboard split is the app's one draggable sash
(``widgets/splitter.DarkSplitter``, ``SP_LIVE_UPDATE``). Dragging it is the only
gesture that resizes a deck card view *vertically* without changing anything
else, which makes it the repro for any bug in viewport-anchored painting -- the
edge fade in particular (#983).

``sash_drag`` runs the sweep from a **worker thread**, posting one
``SetSashPosition`` per step through ``wx.CallAfter``, for the same reason
``wheel_scroll_start`` does: the point is to let the UI thread process each
resize and the paints it triggers, so the frames a background video grab picks
up are the frames a real drag produces. ``SetSashPosition`` is the same call
``wxSplitterWindow`` makes for every mouse-move of a live drag, so the resize /
repaint path under test is the real one.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class SashMixin(_Base):
    """Commands for reading and dragging a splitter sash."""

    def _resolve_splitter(self, name: str) -> wx.SplitterWindow | None:
        window = getattr(self.frame, name, None)
        return window if isinstance(window, wx.SplitterWindow) else None

    def _handle_get_sash(self, splitter: str = "deck_split") -> dict[str, Any]:
        """Report a splitter's current sash position and its legal range."""
        window = self._resolve_splitter(splitter)
        if window is None:
            return {"error": f"No splitter: {splitter}"}
        minimum = window.GetMinimumPaneSize()
        height = window.GetClientSize().GetHeight()
        return {
            "splitter": splitter,
            "position": window.GetSashPosition(),
            "min": minimum,
            "max": max(minimum, height - minimum - window.GetSashSize()),
            "client_height": height,
        }

    def _handle_set_sash(self, splitter: str = "deck_split", position: int = 0) -> dict[str, Any]:
        """Move a sash to ``position`` synchronously and flush the repaint."""
        window = self._resolve_splitter(splitter)
        if window is None:
            return {"error": f"No splitter: {splitter}"}
        window.SetSashPosition(position)
        window.Update()
        return {"position": window.GetSashPosition()}

    def _handle_sash_drag(
        self,
        splitter: str = "deck_split",
        start: int | None = None,
        end: int | None = None,
        steps: int = 12,
        cycles: int = 1,
        interval_ms: float = 25.0,
    ) -> dict[str, Any]:
        """Sweep a sash between ``start`` and ``end`` and back, ``cycles`` times.

        Returns as soon as the sweep is scheduled (not finished) so the caller
        can be recording while it runs; poll ``get-sash`` to see it land.
        """
        window = self._resolve_splitter(splitter)
        if window is None:
            return {"started": False, "error": f"No splitter: {splitter}"}
        if window.GetSplitMode() != wx.SPLIT_HORIZONTAL:
            return {"started": False, "error": f"{splitter} is not split horizontally"}

        # Bring the split to the front, otherwise it is resized but never
        # painted and the sweep proves nothing.
        notebook = getattr(self.frame, "deck_tabs", None)
        if notebook is not None:
            for i in range(notebook.GetPageCount()):
                if notebook.GetPage(i) is window:
                    notebook.SetSelection(i)
                    break
        if self.frame.IsIconized():
            self.frame.Iconize(False)
        self.frame.Raise()

        info = self._handle_get_sash(splitter)
        low = int(info["min"]) if start is None else int(start)
        high = int(info["max"]) if end is None else int(end)
        low, high = min(low, high), max(low, high)
        steps = max(1, int(steps))

        def sweep() -> None:
            for _ in range(max(1, int(cycles))):
                for direction in (1, -1):
                    for i in range(steps + 1):
                        frac = i / steps if direction > 0 else 1 - i / steps
                        wx.CallAfter(window.SetSashPosition, int(low + (high - low) * frac))
                        time.sleep(max(0.0, interval_ms / 1000.0))

        threading.Thread(target=sweep, daemon=True).start()
        return {
            "started": True,
            "splitter": splitter,
            "start": low,
            "end": high,
            "steps": steps,
            "cycles": cycles,
            "interval_ms": interval_ms,
        }
