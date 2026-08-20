"""Row-boundary snapping for the deck card views (grid + pile).

The problem this solves
-----------------------
Both views scroll at ``CARD_VIEW_SCROLL_RATE = 1`` px per unit, so the view
origin can land on any pixel. The wheel moves 60px per notch against a 232px
grid row, so after a scroll the origin is ``scroll_y % 232`` into a row and the
**top** row of the viewport is sliced — measured at the 1200x680 floor, one
notch leaves 172px of a card cut off above the pane edge, and four notches leave
16px of card showing. A partial row at the *bottom* is a legitimate "there is
more below" signal; a partial row at the *top* is just a clipped render.

Why snapping and not quantising the pane
----------------------------------------
Rounding the viewport down to a whole number of rows was the review's
suggestion and was measured and rejected in phase 8: at the enforced 1200x680
floor the mainboard grid gets 285px against a 232px row, so quantising spends up
to 231px of the primary content region, and the 118px sideboard pane quantises
to *zero* rows — an empty pane. Snapping the **origin** costs nothing: the
bottom row stays partial (that is the affordance), the top row never is.

The rule
--------
* A view declares its quantum as ``scroll_snap_step() -> (step, phase)``. The
  grid's is one cell (card + gap) at phase 0. The pile's is one name strip at
  phase ``_PILE_TOP``, because every pile's card tops sit at ``_PILE_TOP + 32k``
  regardless of how many copies it holds -- shorter piles are bottom-aligned but
  their tops land on the same lattice.
* Snapping is **off when the viewport is shorter than one step**, which is what
  keeps the 118px sideboard grid pane scrolling freely: with no whole row able
  to fit, every origin slices both edges and there is no better one to snap to.
* The reachable origins are the lattice **plus 0 and plus the bottom clamp**.
  Content height is not a multiple of the step, so the last origin cannot be on
  the lattice; scrolled fully down the view shows the last row whole against the
  bottom edge and the top row is the one that gives, which is the one case where
  a sliced top row is unavoidable and correct.
* A wheel notch moves a whole number of steps, ``round(px / step)`` floored at
  one. This is the part that makes snapping feel right rather than sticky: with
  a 60px notch against a 232px grid row, "scroll 60px then snap" either moves a
  whole row anyway (snapping forward) or moves nothing at all (snapping to the
  nearest), and the second is the failure the brief warned about. Deriving the
  notch from the step instead means no correction is ever applied and the view
  never moves backwards against the gesture. Measured: the grid goes 60px/notch
  -> 232px/notch (one row, which is what the 285px viewport shows anyway), the
  pile 60 -> 64px/notch, i.e. unchanged in feel.

What is deliberately **not** snapped: the marquee autoscroll and the drag-
reorder autoscroll (they need pixel-smooth travel and are a gesture in
progress), and the horizontal axis (the pile's columns are a lattice too, but
168px per notch is a scroll-speed change nothing asked for).
"""

from __future__ import annotations

import wx


def snap_step(window: wx.ScrolledWindow) -> tuple[int, int] | None:
    """``(step, phase)`` for ``window``, or ``None`` when snapping is off.

    ``None`` covers both a view that declares no quantum and a viewport too
    short to hold one whole step.
    """
    declare = getattr(window, "scroll_snap_step", None)
    if declare is None:
        return None
    declared = declare()
    if not declared:
        return None
    step, phase = declared
    if step <= 0:
        return None
    if window.GetClientSize().GetHeight() < step:
        return None
    return step, phase


def snap_stops(window: wx.ScrolledWindow) -> list[int] | None:
    """Every vertical origin ``window`` may come to rest at, ascending.

    ``None`` when snapping is off for this window.
    """
    declared = snap_step(window)
    if declared is None:
        return None
    step, phase = declared
    client_h = window.GetClientSize().GetHeight()
    content_h = content_height(window)
    limit = max(0, content_h - client_h)
    if limit <= 0:
        return [0]
    stops = [0]
    y = phase if phase > 0 else step
    while y < limit:
        stops.append(y)
        y += step
    stops.append(limit)
    return stops


def content_height(window: wx.ScrolledWindow) -> int:
    """The view's true content height.

    A view may publish ``scroll_content_height()`` when its virtual size is not
    it -- wx inflates ``GetVirtualSize`` to the client size, which would make a
    short deck look scrollable.
    """
    publish = getattr(window, "scroll_content_height", None)
    if publish is not None:
        return int(publish())
    return window.GetVirtualSize().GetHeight()


def snapped_target(
    window: wx.ScrolledWindow, current: int, delta: int, unit: int | None = None
) -> int:
    """Where a vertical scroll of ``delta`` px from ``current`` should land.

    ``delta`` is positive downward. Falls back to plain pixel scrolling (clamped
    at the top; ``Scroll`` clamps the bottom) when snapping is off for this
    window, so a caller can use this unconditionally.

    ``unit`` is the pixel size of **one** of whatever the caller is counting --
    one wheel notch. It matters because a single wheel event can carry several
    notches (a flick on a free-spin wheel, or the accumulator releasing carried
    rotation), and rounding the *total* onto the lattice would collapse three
    notches of 60px into one 232px row. Rounding the unit and multiplying keeps
    a flick worth what its notches are worth. Defaults to ``delta``, i.e. one.
    """
    stops = snap_stops(window)
    if stops is None:
        return max(0, current + delta)
    if delta == 0 or len(stops) < 2:
        return current
    declared = snap_step(window)
    assert declared is not None  # snap_stops already returned a list
    step = declared[0]
    unit = abs(unit) if unit else abs(delta)
    count = max(1, round(abs(delta) / unit)) * max(1, round(unit / step))
    if delta > 0:
        # Index of the last stop at or below where we are: a notch from an
        # unaligned origin (a thumb drag, the bottom clamp) moves onto the
        # lattice first, then by whole steps.
        idx = max((i for i, y in enumerate(stops) if y <= current), default=0)
        return stops[min(len(stops) - 1, idx + count)]
    idx = min((i for i, y in enumerate(stops) if y >= current), default=len(stops) - 1)
    return stops[max(0, idx - count)]


def nearest_stop(window: wx.ScrolledWindow, current: int) -> int | None:
    """The stop ``current`` should settle on, or ``None`` when snapping is off.

    Used after a gesture that moves the origin without going through the wheel
    -- a scrollbar thumb drag, an arrow-button click, a keyboard page. Those do
    scroll smoothly and only *settle* on a boundary, which is the right feel for
    a drag: snapping mid-gesture would fight the thumb.
    """
    stops = snap_stops(window)
    if stops is None:
        return None
    return min(stops, key=lambda y: (abs(y - current), y))


def scroll_viewport(window: wx.ScrolledWindow, x: int, y: int) -> None:
    """Move ``window``'s origin without letting wx's scroll blit reach the screen.

    ``wxScrollHelper::DoScroll`` -- what ``Scroll()`` goes through -- moves the
    origin with ``wxWindow::ScrollWindow``, which on MSW is
    ``::ScrollWindow(hwnd, dx, dy, ...)``: a screen-to-screen copy, followed by a
    repaint of only the strip the copy could not cover. Everything these views
    draw scrolls with the content and survives that intact except one thing --
    the edge fade is painted against the *viewport*, so the copy carries the
    previous frame's band to a position the repaint has no reason to touch
    (#983; ``edge_fade`` has the full account).

    ``Freeze()`` is ``WM_SETREDRAW(FALSE)``, under which the copy puts nothing
    on the window's surface at all; ``Thaw()`` restores drawing and invalidates
    the whole window, so the next paint renders a whole correct frame. Measured
    by reading the window's own surface immediately after the move and before
    any repaint (``tests/ui/test_card_view_viewport_repaint.py`` pins this): a
    plain ``Scroll`` leaves the band stranded partway down the client, wrapped
    like this it stays where the viewport puts it.

    There is deliberately **no** ``Update()`` here. Forcing the repaint
    synchronously was the previous attempt at #983, and it is what made the
    reporter call the scrolling sluggish: it serialises a paint into every
    notch and defeats the coalescing that lets a fast flick draw once for
    several notches. Leaving the paint asynchronous measured 96 paints per 72
    notches down to 72, and cut wheel-latency p95 from 19.5ms to 6.0ms with the
    worst case going from 181ms to 8ms.

    ``EnableScrolling(False, False)`` is the documented way to ask for exactly
    this and does not deliver it -- see :func:`edge_fade.begin_viewport_paint`,
    which is also the backstop for the scroll paths wx runs from C++ and this
    function never sees.
    """
    window.Freeze()
    try:
        # wx.ScrolledWindow.Scroll, not window.Scroll: both views override
        # Scroll to route here, so calling it back would recurse.
        wx.ScrolledWindow.Scroll(window, x, y)
    finally:
        window.Thaw()


def handle_scrollwin(window: wx.ScrolledWindow, event: wx.ScrollWinEvent) -> None:
    """Keep a view's scrollbar on the same lattice its wheel uses.

    Shared by the grid and the pile so both behave identically, exactly as
    :func:`widgets.panels.card_table_panel.scrolling.scroll_by_wheel` is. The
    three gestures behave differently on purpose:

    * **arrow buttons** move one whole row. At ``CARD_VIEW_SCROLL_RATE = 1`` wx
      moves them one *pixel*, which was already close to useless and would
      additionally be undone by the settle below -- i.e. a dead button.
    * **paging** is left to wx (a page is a viewport) and settles onto the
      nearest boundary afterwards, so a page moves a whole number of rows.
    * **a thumb drag** tracks the cursor pixel for pixel and settles only when
      the thumb is released. Snapping mid-drag would fight the thumb; smooth
      travel that comes to rest on a boundary is the better feel, and is what
      the brief asked for over snapping mid-gesture.

    With snapping off (a pane too short to hold one whole row) every event is
    handed straight back to wx, so the short sideboard pane keeps scrolling
    freely.
    """
    etype = event.GetEventType()
    if event.GetOrientation() != wx.VERTICAL or snap_stops(window) is None:
        event.Skip()
        return
    if etype in (wx.wxEVT_SCROLLWIN_LINEUP, wx.wxEVT_SCROLLWIN_LINEDOWN):
        down = etype == wx.wxEVT_SCROLLWIN_LINEDOWN
        _view_x, view_y = window.GetViewStart()
        scroll_viewport(window, -1, snapped_target(window, view_y, 1 if down else -1))
        return
    event.Skip()
    if etype == wx.wxEVT_SCROLLWIN_THUMBTRACK:
        return
    # After wx has applied the event, not instead of it.
    wx.CallAfter(settle, window)


def settle(window: wx.ScrolledWindow) -> None:
    """Move ``window`` to the nearest stop. No-op when snapping is off."""
    if not window:
        return
    _view_x, view_y = window.GetViewStart()
    target = nearest_stop(window, view_y)
    if target is not None and target != view_y:
        scroll_viewport(window, -1, target)
