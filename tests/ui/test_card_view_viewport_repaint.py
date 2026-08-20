"""#983: moving a card view's viewport smeared the edge fade.

What broke
----------
The redesign's S5 fade (:mod:`widgets.panels.card_table_panel.edge_fade`) is the
only thing the card views paint against the **viewport** rather than against the
content: a 24px band hugging the pane edge. Everything else they draw is a blit
out of a content-sized canvas, so it stays correct wherever the window's pixels
end up. A band does not, and wxMSW preserves whatever pixels it can.

Captured off the screen mid-gesture, with the band temporarily rendered opaque
so a stranded one could be counted: a twelve-notch wheel burst left four bands
at exactly the 64px notch spacing, still there when the capture ended 500ms
after the gesture, and a live sash sweep stacked them 90px deep.

What is pinned here
-------------------
Three independent levers hold the fix up, and each is pinned by the test that
can actually see it:

1. :func:`edge_fade.begin_viewport_paint` widens a paint's clip to the whole
   client. Measured on the ``PaintDC``'s own HDC against a control window that
   does not call it -- the only assertion here that depends on the machine, and
   the control is what makes it honest (see below).
2. Every gesture that moves the origin goes through
   :func:`scroll_snap.scroll_viewport`, which keeps wx's scroll blit off the
   screen. Asserted on the calls, so it does not vary with anything.
3. Both card views carry ``wx.FULL_REPAINT_ON_RESIZE``, so MSW does not preserve
   bits across the resizes of a live sash drag.

**What no test here covers, and cannot:** that the pixels on screen hold no
stale band while a gesture is in flight. That needs a real compositor, a real
gesture and a frame grab of the screen surface; it was verified that way for
#983 (both gestures, before and after, frames read back and counted) and it
stays a manual check. Everything below is a proxy for it -- a good one, but the
distinction is exactly what let an earlier attempt at this test pass against
code the reporter could see was broken.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.panels.card_table_panel import edge_fade, scroll_snap
from widgets.panels.card_table_panel.scrolling import inject_wheel_notches

#: Enough distinct cards that both zones are several rows deep at the frame's
#: enforced floor, so both views really do have a clipped edge to fade.
_DECK = [
    "Blazing Rootwalla",
    "Marauding Mako",
    "Hardened Academic",
    "Vengevine",
    "Hollow One",
    "Street Wraith",
    "Burning Inquiry",
    "Faithless Looting",
    "Lightning Bolt",
    "Arid Mesa",
    "Bloodstained Mire",
    "Mountain",
    "Scalding Tarn",
    "Sacred Foundry",
    "Wooded Foothills",
    "Practiced Offense",
    "Prismatic Ending",
    "Vexing Bauble",
    "Damping Sphere",
]


def _deck_tables_frame(deck_selector_factory, wx_app):
    """A frame at its own enforced floor with the Deck Tables split in front."""
    frame = deck_selector_factory()
    frame.main_table.set_cards([{"name": name, "qty": 4} for name in _DECK])
    frame.side_table.set_cards([{"name": name, "qty": 2} for name in _DECK])
    pump_ui_events(wx_app)
    frame._apply_min_size()
    frame.SetSize(frame.GetMinSize())
    # The split has to be the visible page or its panes are never laid out.
    for index in range(frame.deck_tabs.GetPageCount()):
        if frame.deck_tabs.GetPage(index) is frame.deck_split:
            frame.deck_tabs.SetSelection(index)
            break
    frame.Layout()
    pump_ui_events(wx_app)
    return frame


def _view(frame, zone: str, mode: str):
    table = getattr(frame, f"{zone}_table")
    table.set_view_mode(mode, persist=False)
    return getattr(table, "pile_view" if mode == "pile" else "grid_view")


# ---------------------------------------------------------------------------
# 1. The clip a paint handler is given.

_PROBE_SIZE = (360, 260)
_PROBE_CONTENT_H = 4000
#: Scroll offsets to step through. Each leaves a retained strip taller than the
#: 24px fade band, so a clip short of the client would really strand one.
_PROBE_OFFSETS = (64, 128, 192, 256)


def _clip_box(dc: wx.DC) -> wx.Rect:
    """The clip ``BeginPaint`` actually put on ``dc``, read off its HDC.

    ``wx.DC.GetClippingBox`` reports the *application's* clipping region, which
    nothing here sets; the region that matters is the one Windows installed on
    the device context before the handler ran, and ``GetClipBox`` is the only
    way to see it.
    """
    rect = wintypes.RECT()
    ctypes.windll.gdi32.GetClipBox(wintypes.HDC(dc.GetHandle()), ctypes.byref(rect))
    return wx.Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


class _ClipProbe(wx.ScrolledWindow):
    """A scrolled window that records the clip of every paint it is given."""

    def __init__(self, parent: wx.Window, *, widen: bool) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.widen = widen
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(1, 1)
        self.SetVirtualSize((_PROBE_SIZE[0], _PROBE_CONTENT_H))
        self.clips: list[wx.Rect] = []
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        if self.widen:
            edge_fade.begin_viewport_paint(self)
        dc = wx.PaintDC(self)
        self.clips.append(_clip_box(dc))
        dc.SetBackground(wx.Brush(wx.Colour(20, 20, 20)))
        dc.Clear()


def _scrolled_clips(probe: _ClipProbe, frame: wx.Frame, wx_app: wx.App) -> list[wx.Rect]:
    """Step ``probe`` through the offsets, returning one clip per paint."""
    probe.Scroll(0, 0)
    frame.Update()
    pump_ui_events(wx_app)
    probe.clips.clear()
    for offset in _PROBE_OFFSETS:
        probe.Scroll(0, offset)
        frame.Update()
        pump_ui_events(wx_app)
    return list(probe.clips)


@pytest.mark.usefixtures("wx_app")
def test_a_scrolled_paint_is_clipped_to_the_whole_client(wx_app) -> None:
    """``begin_viewport_paint`` must widen the paint it is called from (#983).

    ``BeginPaint`` clips the ``wx.PaintDC`` to the update region before the
    handler runs, so a stale band outside it is unreachable however it is
    composited. Invalidating from inside ``WM_PAINT`` and before the ``PaintDC``
    exists is what makes the clip the whole client instead.

    The control beside the subject is what makes this mean anything: it is the
    same window without the call, and if *it* is handed the whole client too
    then this machine is not preserving pixels across a scroll and cannot tell
    the fix from its absence. An occluded or unredirected window does exactly
    that, and that is how an earlier version of this test passed against unfixed
    code -- so the control failing to reproduce is a **skip**, never a pass.
    """
    frame = wx.Frame(None, size=(2 * _PROBE_SIZE[0] + 60, _PROBE_SIZE[1] + 60))
    try:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        control = _ClipProbe(frame, widen=False)
        subject = _ClipProbe(frame, widen=True)
        sizer.Add(control, 1, wx.EXPAND)
        sizer.Add(subject, 1, wx.EXPAND)
        frame.SetSizer(sizer)
        frame.Show()
        frame.Raise()
        frame.Update()
        pump_ui_events(wx_app)

        control_clips = _scrolled_clips(control, frame, wx_app)
        subject_clips = _scrolled_clips(subject, frame, wx_app)

        control_h = control.GetClientSize().GetHeight()
        subject_h = subject.GetClientSize().GetHeight()
        assert control_h > 2 * min(_PROBE_OFFSETS) and subject_h > 2 * min(_PROBE_OFFSETS), (
            f"the probes are too short to retain anything across a scroll "
            f"(control {control_h}px, subject {subject_h}px); this proves nothing"
        )
        assert control_clips and subject_clips, (
            "neither probe painted at all when scrolled; the window is not being "
            "composited, so nothing here can be measured"
        )

        if all(clip.GetHeight() >= control_h for clip in control_clips):
            pytest.skip(
                "this machine hands a scrolled window its whole client even "
                f"without the fix (control clips {control_clips}); it cannot "
                "distinguish the fix from its absence -- an occluded or "
                "unredirected window does this"
            )

        narrow = [clip for clip in subject_clips if clip.GetHeight() < subject_h]
        assert not narrow, (
            f"a scrolled paint was clipped to {narrow} of a {subject_h}px client. "
            "Nothing the handler draws can reach outside that, so the previous "
            "frame's edge fade -- which the scroll blitted up into the retained "
            "pixels -- can never be erased, and the card rows come out smeared"
        )
    finally:
        frame.Destroy()
        pump_ui_events(wx_app)


@pytest.mark.usefixtures("wx_app")
def test_widening_is_limited_to_paints_that_follow_a_viewport_move() -> None:
    """A repeat paint at the same viewport must stay the targeted repaint.

    The async image pipeline patches one card into the canvas and calls
    ``RefreshRect``; widening *that* would undo an optimisation the fix has no
    reason to touch, because a fade cannot go stale where nothing moved.
    """
    frame = wx.Frame(None, size=(*_PROBE_SIZE,))
    try:
        window = wx.ScrolledWindow(frame)
        window.SetScrollRate(1, 1)
        window.SetVirtualSize((_PROBE_SIZE[0], _PROBE_CONTENT_H))
        frame.Show()

        assert edge_fade.begin_viewport_paint(window) is True, (
            "the first paint of a window has no previous viewport to compare "
            "against, so it must be treated as a move"
        )
        assert edge_fade.begin_viewport_paint(window) is False, (
            "a second paint at the same view start and client size cannot have "
            "stranded anything, so it must not be widened"
        )
        window.Scroll(0, 64)
        assert edge_fade.begin_viewport_paint(window) is True, (
            "a scroll moves the viewport out from under the fade, so the paint "
            "that follows it has to cover the whole client"
        )
        window.SetSize(_PROBE_SIZE[0], _PROBE_SIZE[1] // 2)
        assert edge_fade.begin_viewport_paint(window) is True, (
            "a resize moves the edge the fade is anchored to just as a scroll "
            "does, so the paint that follows it has to cover the whole client"
        )
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# 2. Keeping wx's scroll blit off the screen.


@pytest.mark.usefixtures("wx_app")
def test_scroll_viewport_keeps_the_blit_off_the_screen() -> None:
    """``Scroll`` has to happen between ``Freeze`` and ``Thaw`` (#983).

    ``wxScrollHelper::DoScroll`` blits the window's pixels to their new position
    and repaints only the strip the blit could not cover, so for as long as that
    result is on screen the previous frame's fade band is on screen with it.
    Under ``Freeze`` (``WM_SETREDRAW(FALSE)``) the blit paints nothing at all,
    and the ``Thaw`` + ``Update`` that follow put the next whole frame up in one
    step.
    """
    frame = wx.Frame(None, size=(*_PROBE_SIZE,))
    try:
        window = wx.ScrolledWindow(frame)
        window.SetScrollRate(1, 1)
        window.SetVirtualSize((_PROBE_SIZE[0], _PROBE_CONTENT_H))
        frame.Show()

        calls: list[str] = []
        for name in ("Freeze", "Thaw", "Update"):
            original = getattr(window, name)

            def record(*args, _name=name, _original=original, **kwargs):
                calls.append(_name)
                return _original(*args, **kwargs)

            setattr(window, name, record)
        original_scroll = window.Scroll

        def record_scroll(*args, **kwargs):
            calls.append("Scroll")
            return original_scroll(*args, **kwargs)

        window.Scroll = record_scroll

        scroll_snap.scroll_viewport(window, -1, 64)

        assert calls == ["Freeze", "Scroll", "Thaw", "Update"], (
            f"scroll_viewport did {calls}; the Scroll has to sit inside the "
            "Freeze/Thaw pair or wx's scroll blit reaches the screen carrying "
            "the previous frame's edge fade with it"
        )
    finally:
        frame.Destroy()


@pytest.mark.parametrize("zone", ["main", "side"])
@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_a_wheel_notch_goes_through_scroll_viewport(
    deck_selector_factory, wx_app, monkeypatch, zone, mode
) -> None:
    """The wheel is the gesture that reported #983; it must not call ``Scroll``."""
    frame = _deck_tables_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, zone, mode)
        view.Scroll(0, 0)
        pump_ui_events(wx_app)

        routed: list[tuple[int, int]] = []
        monkeypatch.setattr(
            scroll_snap,
            "scroll_viewport",
            lambda window, x, y: routed.append((x, y)),
        )
        monkeypatch.setattr(
            view,
            "Scroll",
            lambda *args, **kwargs: pytest.fail(
                f"the {zone} {mode} view's wheel called Scroll directly; wx's "
                "scroll blit then reaches the screen and strands the edge fade"
            ),
        )
        inject_wheel_notches(view, 1, up=False)

        assert routed, (
            f"a wheel notch on the {zone} {mode} view moved the origin without "
            "going through scroll_viewport"
        )
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# 3. Not preserving bits across a resize.


@pytest.mark.parametrize("zone", ["main", "side"])
@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_the_card_views_repaint_fully_on_resize(deck_selector_factory, wx_app, zone, mode) -> None:
    """Both views must be on wx's redraw-on-resize window class (#983).

    A live sash drag resizes a pane faster than it can repaint. Without this
    style MSW keeps the bits it can on every one of those resizes, and each
    skipped repaint leaves another fade band behind -- which is why the sash
    drag reads as a solid dark wash rather than as separate stripes.
    """
    frame = _deck_tables_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, zone, mode)
        assert view.GetWindowStyleFlag() & wx.FULL_REPAINT_ON_RESIZE, (
            f"the {zone} {mode} view does not carry wx.FULL_REPAINT_ON_RESIZE, "
            "so wxMSW preserves its pixels across a resize and a sash drag "
            "stacks stale edge fades over the card art"
        )
    finally:
        frame.Destroy()
