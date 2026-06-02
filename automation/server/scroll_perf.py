"""Mouse-wheel scroll-latency command handlers.

Drives a burst of real wheel notches through a deck card view (grid or pile)
and reads back the per-event perf trace so a test can assert the rendered view
never lags the input by more than a threshold.

``wheel_scroll_start`` kicks the burst off from a background thread and returns
immediately so the UI thread stays free to process the injected notches *and*
the paints they trigger — measuring the natural backlog is the whole point, so
we must not block the event loop while it happens. ``get_scroll_perf`` then
reads the recorded ``input``/``paint`` event stream back out.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

import wx

from widgets.panels.card_table_panel import scroll_perf
from widgets.panels.card_table_panel.scrolling import inject_wheel_notches

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class ScrollPerfMixin(_Base):
    """Commands for measuring mouse-wheel scroll responsiveness."""

    def _scroll_view_window(self, zone: str, view: str) -> Any | None:
        """Return the grid/pile ScrolledWindow for ``zone`` (or ``None``)."""
        table = getattr(self.frame, f"{zone}_table", None)
        if table is None:
            return None
        attr = "pile_view" if view == "pile" else "grid_view"
        return getattr(table, attr, None)

    def _handle_wheel_scroll_start(
        self,
        zone: str = "main",
        view: str = "grid",
        count: int = 10,
        direction: str = "down",
        interval_ms: float = 4.0,
    ) -> dict[str, Any]:
        """Begin a wheel-scroll burst and start recording its perf trace.

        Switches the zone's card panel to ``view``, parks the scroll origin at
        the end opposite ``direction`` so every notch has somewhere to go, then
        fires ``count`` notches spaced ``interval_ms`` apart from a worker
        thread. Returns once the burst is scheduled (not finished).
        """
        table = getattr(self.frame, f"{zone}_table", None)
        if table is None:
            return {"started": False, "error": f"No table for zone: {zone}"}
        if view not in ("grid", "pile"):
            return {"started": False, "error": f"Unknown view: {view}"}

        # Bring the zone's notebook page to the front so its view actually
        # receives paints (tab text is localized, so match by page identity).
        notebook = getattr(self.frame, "deck_tabs", None)
        if notebook is not None:
            for i in range(notebook.GetPageCount()):
                if notebook.GetPage(i) is table:
                    notebook.SetSelection(i)
                    break
        # Make the requested view the visible page so its paints actually fire.
        if hasattr(table, "set_view_mode"):
            table.set_view_mode(view, persist=False)
        # A minimized window receives no WM_PAINT, so the view would never
        # repaint and we'd measure nothing. Restore + raise it before the burst.
        try:
            if self.frame.IsIconized():
                self.frame.Iconize(False)
            self.frame.Show(True)
            self.frame.Raise()
        except Exception:
            pass

        window = self._scroll_view_window(zone, view)
        if window is None:
            return {"started": False, "error": f"No {view} view for zone: {zone}"}

        up = direction == "up"
        # Park at the opposite end so the burst has full travel room, flush that
        # repositioning paint, then start clean so it isn't counted as latency.
        window._wheel_accum = 0  # type: ignore[attr-defined]
        window.Scroll(0, 0 if not up else 10**7)
        window.Update()
        scroll_perf.enable(window)

        def burst() -> None:
            for _ in range(count):
                wx.CallAfter(inject_wheel_notches, window, 1, up=up)
                time.sleep(max(0.0, interval_ms / 1000.0))

        threading.Thread(target=burst, daemon=True).start()
        return {
            "started": True,
            "zone": zone,
            "view": view,
            "count": count,
            "direction": direction,
            "interval_ms": interval_ms,
        }

    def _handle_get_scroll_perf(self, zone: str = "main", view: str = "grid") -> dict[str, Any]:
        """Return the recorded wheel-scroll perf trace for ``zone``/``view``."""
        window = self._scroll_view_window(zone, view)
        if window is None:
            return {"events": [], "error": f"No {view} view for zone: {zone}"}
        return {"events": scroll_perf.snapshot(window)}
