"""#983: moving a card view's viewport smears the edge fade.

What breaks
-----------
The redesign's S5 fade (:mod:`widgets.panels.card_table_panel.edge_fade`) is the
only thing the card views paint against the **viewport** rather than against the
content: a 24px band hugging the pane edge. Everything else they draw is a blit
out of a content-sized canvas, so it stays correct wherever the window's pixels
end up.

wxMSW keeps whatever pixels it can when the viewport moves and invalidates only
the strip it cannot, and a ``wx.PaintDC`` is clipped to that update region by
``BeginPaint``. So the fade painted by the *previous* frame survives wherever
those preserved pixels ended up, and no paint handler is allowed to reach it.
Both gestures do it, for the same reason:

* **A wheel scroll.** wx moves the origin by blitting (``ScrollWindow``).
  Logged from the pile view's own paint handler, six notches at 64px::

      region=(0, 289, 912, 64)  client=(912, 353)  view_y=124
      region=(0, 289, 912, 64)  client=(912, 353)  view_y=188

  The band was at y 329..353; the blit carried it to y 265..289, just above the
  strip wx asked for. One stale band per notch, 64px apart, still there 750ms
  after the burst ended.
* **A sash drag.** No blit needed -- a pane that grows repaints only the strip
  it gained, once per mouse-move, so the swept band fills with overlapping
  copies of the fade.

What is pinned
--------------
1. That a **resize** of a card view asks for a repaint of the whole client,
   every time and in both directions, rather than trusting the region wx
   invalidated.
2. That a **scroll** of a window carrying :func:`edge_fade.
   require_whole_client_repaints` really does hand its paint handler the whole
   client, where an otherwise identical window gets a thin strip.
3. That both card views actually carry it.

(1) is asserted on the request rather than on pixels deliberately: what the view
*asks for* does not vary with anything about the machine.

(2) cannot be, because there is no request -- the whole point is that wx does
this from C++ without consulting us, so the only honest assertion is on the
update region the paint handler is handed. That measurement **does** vary with
the machine: an occluded window has no preserved pixels, so MSW invalidates all
of it and the bug hides. An earlier attempt at this test passed against unfixed
code for exactly that reason. The guard is a **control window** built beside the
subject and scrolled identically: if the control does not reproduce the partial
region, this machine cannot see the defect and the test skips instead of
passing. Reverting the fix makes the subject behave like its control, which is
a failure and not a skip, because the control still reproduces.

What no test here covers: that the resulting *pixels* have no stale band in them
mid-gesture. That was verified by capturing the running app's screen during both
gestures (see PR #983); it needs a real compositor and a real gesture, so it
stays a manual check.
"""

from __future__ import annotations

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.panels.card_table_panel import edge_fade

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

#: Pixels of sash travel per step. Smaller than the 24px fade band, which is what
#: makes the stale bands overlap into a solid smear rather than read as stripes.
_DRAG_STEP_PX = 15


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


def _sash_range(splitter: wx.SplitterWindow) -> tuple[int, int]:
    minimum = splitter.GetMinimumPaneSize()
    return minimum, splitter.GetClientSize().GetHeight() - minimum - splitter.GetSashSize()


@pytest.mark.parametrize("zone", ["main", "side"])
@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_a_sash_drag_repaints_the_whole_card_view(
    deck_selector_factory, wx_app, monkeypatch, zone, mode
) -> None:
    """Every step of a sash drag asks the resized view for a full repaint (#983).

    Anything less leaves the previous step's edge fade on screen at the edge the
    pane no longer has, which is the smear.
    """
    frame = _deck_tables_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, zone, mode)
        splitter = frame.deck_split
        low, high = _sash_range(splitter)
        assert high - low > 4 * _DRAG_STEP_PX, (
            f"the split has no room to drag in (sash range {low}..{high}); "
            "the frame is not laid out, so this test would prove nothing"
        )

        requested: list[tuple[bool, wx.Rect | None]] = []
        monkeypatch.setattr(
            view,
            "Refresh",
            lambda eraseBackground=True, rect=None: requested.append((eraseBackground, rect)),
        )

        splitter.SetSashPosition(high)
        pump_ui_events(wx_app)

        # Down and back up: one leg grows this pane and the other shrinks it,
        # and before the fix the two failed differently -- a partial strip, and
        # no repaint at all.
        position = high
        heights: list[int] = []
        for target in (low, high):
            while position != target:
                step = min(_DRAG_STEP_PX, abs(target - position))
                position += step if target > position else -step
                requested.clear()
                splitter.SetSashPosition(position)
                height = view.GetClientSize().GetHeight()
                assert heights[-1:] != [height], (
                    f"the {zone} {mode} view did not resize when the sash moved to "
                    f"{position} (still {height}px); this step proves nothing"
                )
                heights.append(height)
                assert requested, (
                    f"the {zone} {mode} view was not asked to repaint when the sash "
                    f"moved to {position}: wxMSW invalidates only the strip it just "
                    "exposed, so the edge fade stays painted at the old edge"
                )
                assert all(rect is None for _erase, rect in requested), (
                    f"the {zone} {mode} view asked to repaint only {requested}; the "
                    "fade sits at whichever edge the pane now has, so a partial "
                    "repaint is what smears it"
                )

        assert len(set(heights)) > 4, (
            f"the {zone} {mode} view barely resized during the drag "
            f"(heights seen: {sorted(set(heights))})"
        )
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------------
# The scroll half. See the module docstring for why this one reads pixel-level
# update regions and carries its own control.

_PROBE_SIZE = (360, 240)
_PROBE_CONTENT_H = 4000
#: Scroll offsets to step through. Each is far enough from the last to leave a
#: retained strip taller than the fade band, so a partial region would really
#: strand one.
_PROBE_OFFSETS = (64, 128, 192, 256)


class _RegionProbe(wx.ScrolledWindow):
    """A scrolled window that records the update region of every paint."""

    def __init__(self, parent: wx.Window, *, whole_client: bool) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(1, 1)
        self.SetVirtualSize((_PROBE_SIZE[0], _PROBE_CONTENT_H))
        if whole_client:
            edge_fade.require_whole_client_repaints(self)
        self.regions: list[wx.Rect] = []
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        self.PrepareDC(dc)
        dc.SetBackground(wx.Brush(wx.Colour(20, 20, 20)))
        dc.Clear()
        self.regions.append(self.GetUpdateRegion().GetBox())


def _scrolled_regions(probe: _RegionProbe, frame: wx.Frame, wx_app: wx.App) -> list[wx.Rect]:
    """Step ``probe`` through the offsets, returning one region per paint."""
    probe.Scroll(0, 0)
    frame.Update()
    pump_ui_events(wx_app)
    probe.regions.clear()
    for offset in _PROBE_OFFSETS:
        probe.Scroll(0, offset)
        frame.Update()
        pump_ui_events(wx_app)
    return list(probe.regions)


@pytest.mark.usefixtures("wx_app")
def test_a_scroll_invalidates_the_whole_client(wx_app) -> None:
    """A scroll must repaint every strip, not only the one it exposed (#983).

    The control beside the subject is what makes this test mean anything: it is
    the same window without :func:`edge_fade.require_whole_client_repaints`, and
    if *it* is handed the whole client too then this machine is not preserving
    pixels across a scroll and cannot see the defect at all.
    """
    frame = wx.Frame(None, size=(2 * _PROBE_SIZE[0] + 60, _PROBE_SIZE[1] + 60))
    try:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        control = _RegionProbe(frame, whole_client=False)
        subject = _RegionProbe(frame, whole_client=True)
        sizer.Add(control, 1, wx.EXPAND)
        sizer.Add(subject, 1, wx.EXPAND)
        frame.SetSizer(sizer)
        frame.Show()
        frame.Update()
        pump_ui_events(wx_app)

        control_regions = _scrolled_regions(control, frame, wx_app)
        subject_regions = _scrolled_regions(subject, frame, wx_app)

        control_h = control.GetClientSize().GetHeight()
        subject_h = subject.GetClientSize().GetHeight()
        assert control_h > 2 * min(_PROBE_OFFSETS) and subject_h > 2 * min(_PROBE_OFFSETS), (
            f"the probes are too short to retain anything across a scroll "
            f"(control {control_h}px, subject {subject_h}px); this proves nothing"
        )
        assert control_regions and subject_regions, (
            "neither probe painted at all when scrolled; the window is not being "
            "composited, so nothing here can be measured"
        )

        if all(region.GetHeight() >= control_h for region in control_regions):
            pytest.skip(
                "this machine invalidates the whole client on a scroll even "
                f"without the fix (control regions {control_regions}); it cannot "
                "distinguish the fix from its absence -- an occluded or "
                "unredirected window does this"
            )

        stale = [region for region in subject_regions if region.GetHeight() < subject_h]
        assert not stale, (
            f"a scroll handed the view only {stale} of its {subject_h}px client. A "
            "wx.PaintDC is clipped to that, so the previous frame's edge fade -- "
            "which the scroll blitted up into the retained pixels -- can never be "
            "erased, and the card rows come out smeared with dark bands"
        )
    finally:
        frame.Destroy()
        pump_ui_events(wx_app)


@pytest.mark.parametrize("zone", ["main", "side"])
@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_the_card_views_ask_for_whole_client_repaints(
    deck_selector_factory, wx_app, zone, mode
) -> None:
    """The property the test above measures has to be on the real views."""
    frame = _deck_tables_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, zone, mode)
        assert view.IsDoubleBuffered(), (
            f"the {zone} {mode} view is not asking wxMSW to repaint its whole "
            "client on a scroll (edge_fade.require_whole_client_repaints), so "
            "every wheel notch strands another copy of the edge fade"
        )
    finally:
        frame.Destroy()
