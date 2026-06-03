"""Shared rubber-band (marquee) selection machinery for the card views.

Every card view — pile, grid and table — supports the same gesture: press on an
empty surface and drag a rectangle to multi-select the cards it covers. The
mechanics of that gesture (mouse capture, a cursor-polling timer so the box
keeps growing past the window edge, the app-level outline overlay, auto-scroll)
are identical across the views; only *which* items a rectangle selects differs.

:class:`MarqueeController` owns the shared mechanics for one view. The view hands
it a target window plus a few callbacks and otherwise just forwards its mouse
events. The selection itself stays in the view (it knows its own layout and
selection model), driven by the ``on_select`` callback.

The opt-in *surface marker* lets the application decide which background windows
may originate a marquee. A press is routed to the active view's controller only
when it lands on a window that was explicitly marked — see
``mark_marquee_surface``. This is what makes "drag from any non-interactive zone"
work without binding a handler onto every panel: an app-level event filter checks
the marker and forwards. Card-view canvases are deliberately *not* marked; they
begin their own marquee from their empty-space press so a click on a card still
selects the card.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from widgets.panels.card_table_panel.marquee_overlay import MarqueeOverlay

# While a rubber-band is active a timer polls the global cursor so the box keeps
# tracking (and the view keeps auto-scrolling) even when the pointer is dragged
# past the window edge — the OS only delivers motion events while the cursor is
# over the window, which would otherwise freeze the box at the edge.
_RUBBER_POLL_MS = 30
# Per-tick auto-scroll step while the pointer is held beyond a viewport edge.
RUBBER_AUTOSCROLL_PX = 24

# Windows carrying this attribute (set truthy) are valid marquee origins.
_MARQUEE_SURFACE_ATTR = "_marquee_surface"

# Plain background/decoration window types that a recursive mark treats as
# non-interactive surfaces. Exact-type checks (not isinstance) so the card-view
# canvases and the panels that subclass wx.Panel are never swept in — only
# vanilla backgrounds and static chrome opt in.
_RECURSIVE_SURFACE_TYPES = (wx.Panel, wx.StaticText, wx.StaticLine)


def mark_marquee_surface(window: wx.Window) -> None:
    """Mark ``window`` as a surface a marquee may be started from."""
    setattr(window, _MARQUEE_SURFACE_ATTR, True)


def is_marquee_surface(window: wx.Window | None) -> bool:
    """Whether ``window`` was opted in as a marquee surface."""
    return bool(getattr(window, _MARQUEE_SURFACE_ATTR, False))


def mark_marquee_surfaces_recursively(root: wx.Window) -> None:
    """Opt ``root`` and its plain background/static descendants into marquee.

    Sweeps the tree once and marks every vanilla ``wx.Panel`` / ``wx.StaticText``
    / ``wx.StaticLine`` (by exact type, so custom panels and controls are left
    out). Run on the app's chrome after it is built; the card-view canvases are
    intentionally excluded and originate their own marquee.
    """
    stack: list[wx.Window] = [root]
    while stack:
        window = stack.pop()
        if type(window) in _RECURSIVE_SURFACE_TYPES:
            mark_marquee_surface(window)
        stack.extend(window.GetChildren())


class MarqueeController:
    """Drives one view's rubber-band selection.

    The view supplies:

    * ``to_logical(client_point)`` — map a client point on ``window`` to the
      view's logical (scroll-aware) coordinates.
    * ``on_begin(additive)`` — called once when a marquee starts; the view
      snapshots/clears its selection here (``additive`` is the Shift state).
    * ``on_select(logical_rect)`` — called whenever the rectangle changes; the
      view selects the items it covers.
    * ``on_finish()`` — called when the marquee ends (commit or cancel); the
      view drops any per-drag state.
    * ``autoscroll(client_point)`` — optional; scroll one step toward an edge
      the pointer is held beyond.
    """

    def __init__(
        self,
        window: wx.Window,
        *,
        to_logical: Callable[[wx.Point], wx.Point],
        on_begin: Callable[[bool], None],
        on_select: Callable[[wx.Rect], None],
        on_finish: Callable[[], None],
        autoscroll: Callable[[wx.Point], None] | None = None,
    ) -> None:
        self._window = window
        self._to_logical = to_logical
        self._on_begin = on_begin
        self._on_select = on_select
        self._on_finish = on_finish
        self._autoscroll = autoscroll

        # Logical (scroll-aware) corners of the active rectangle; None when idle.
        self._start: wx.Point | None = None
        self._end: wx.Point | None = None
        # Fixed screen-space origin for the outline overlay (screen-anchored so
        # the visible box doesn't shift when the content scrolls under it).
        self._start_screen: wx.Point | None = None
        self._overlay: MarqueeOverlay | None = None
        self._timer = wx.Timer(window)
        window.Bind(wx.EVT_TIMER, self._on_timer, self._timer)

    @property
    def active(self) -> bool:
        return self._start is not None

    # ----- lifecycle -----
    def begin(self, client_point: wx.Point, *, additive: bool) -> None:
        """Start a marquee at a client point on the target window."""
        if self.active:
            return
        logical = self._to_logical(client_point)
        self._start = logical
        self._end = logical
        self._start_screen = self._window.ClientToScreen(client_point)
        if not self._window.HasCapture():
            self._window.CaptureMouse()
        self._timer.Start(_RUBBER_POLL_MS)
        self._on_begin(additive)
        self._on_select(self._rect())
        self._update_overlay()

    def begin_at_screen(self, screen_point: wx.Point, *, additive: bool = False) -> None:
        """Start a marquee from anywhere on screen (e.g. the frame background).

        The pointer may be well outside the target window; capturing the mouse
        routes the rest of the drag to it regardless, and the polling timer
        tracks the cursor by its global position from there on.
        """
        self.begin(self._window.ScreenToClient(screen_point), additive=additive)

    def update(self, client_point: wx.Point) -> None:
        """Extend the rectangle to a new client point."""
        if not self.active:
            return
        self._end = self._to_logical(client_point)
        self._on_select(self._rect())
        self._update_overlay()

    def finish(self) -> None:
        """Commit and tear down the active marquee."""
        if not self.active:
            return
        self._teardown()
        self._on_finish()

    def cancel(self) -> None:
        """Tear down without committing (e.g. on mouse-capture loss)."""
        was_active = self.active
        self._teardown()
        if was_active:
            self._on_finish()

    def _teardown(self) -> None:
        self._timer.Stop()
        if self._overlay is not None:
            self._overlay.cancel()
        self._start = None
        self._end = None
        self._start_screen = None
        if self._window.HasCapture():
            self._window.ReleaseMouse()

    # ----- internals -----
    def _rect(self) -> wx.Rect:
        # _start/_end are only read while active, where both are set.
        x1, y1 = self._start  # type: ignore[misc]
        x2, y2 = self._end  # type: ignore[misc]
        return wx.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def _update_overlay(self) -> None:
        if self._start_screen is None:
            return
        if self._overlay is None:
            self._overlay = MarqueeOverlay(self._window.GetTopLevelParent())
        self._overlay.update(self._start_screen, wx.GetMousePosition())

    def _on_timer(self, _event: wx.TimerEvent) -> None:
        """Extend the rectangle toward the live cursor while the button is held.

        Reading the global cursor (rather than relying on motion events, which
        the OS stops sending once the pointer leaves the window) keeps the box
        growing past the canvas edges and lets a held-at-the-edge drag scroll the
        view so the whole canvas — not just the visible part — is reachable.
        """
        if not self.active:
            self._timer.Stop()
            return
        # If the button came up off-window we may have missed the up event; the
        # selection is already committed, so just stand down.
        if not wx.GetMouseState().LeftIsDown():
            self.finish()
            return
        client = self._window.ScreenToClient(wx.GetMousePosition())
        if self._autoscroll is not None:
            self._autoscroll(client)
        # Recompute in logical space *after* any scroll so the endpoint tracks
        # the content the cursor now sits over.
        self.update(client)
