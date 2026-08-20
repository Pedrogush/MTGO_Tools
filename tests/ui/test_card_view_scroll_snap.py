"""Phase 8, S5: the top row of a card view is never sliced.

What this pins, and why it is a runtime test
--------------------------------------------
The review filed S5 as "the last row of the card grid and the whole sideboard
strip are sliced in half by the pane edge" and prescribed row-height
quantisation. Re-measured at the enforced 1200x680 floor, quantisation is the
wrong fix -- the mainboard grid's viewport is 285px against a 232px row, so
rounding it down spends up to 231px of the primary content region, and the
118px sideboard pane rounds to *zero* rows. What the review missed is that the
**top** row is sliced too, and worse: the wheel moves 60px against a 232px row,
so after any scroll the origin is ``scroll_y % 232`` into a row -- measured at
188px, i.e. a top row showing 44px of a card. A partial row at the bottom is a
scroll affordance; a partial row at the top is a clipped render.

So the fix is a snapped *origin*, and the property worth pinning is exactly
that: **wherever the view comes to rest, its origin is a row boundary**. That
cannot be read off the source -- it is a product of the wheel step, the row
height, the live client size and the bottom clamp -- and it only exists at the
window's own floor, which is the size no screenshot pass had ever used.

Every assertion below is pinned against the failure mode
``test_live_layout_overflow`` had in draft: passing while visiting nothing. The
frame is never ``Show()``n in a test, so a view can report a degenerate client
size and every "is this a stop" check would then hold vacuously. Each test
therefore asserts what it actually travelled before asserting where it landed.
"""

from __future__ import annotations

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.panels.card_table_panel import edge_fade, scroll_snap
from widgets.panels.card_table_panel.scrolling import _apply_wheel, inject_wheel_notches

#: Distinct cards, enough that the mainboard grid is several rows deep at the
#: floor's 3 columns. Names come from the deck the app ships in its own saved
#: session, so the metadata lookups behave as they do in the running app.
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


def _floor_frame(deck_selector_factory, wx_app):
    """A frame laid out at its own enforced minimum, with a real deck in it."""
    frame = deck_selector_factory()
    frame.main_table.set_cards([{"name": name, "qty": 4} for name in _DECK])
    frame.side_table.set_cards([{"name": name, "qty": 2} for name in _DECK[:7]])
    pump_ui_events(wx_app)
    frame._apply_min_size()
    frame.SetSize(frame.GetMinSize())
    frame.Layout()
    pump_ui_events(wx_app)
    return frame


def _view(frame, zone: str, mode: str):
    table = getattr(frame, f"{zone}_table")
    table.set_view_mode(mode, persist=False)
    return getattr(table, "pile_view" if mode == "pile" else "grid_view")


def _wheel_to_the_bottom(view, wx_app) -> list[int]:
    """Wheel down until the view stops moving; return every origin it rested at."""
    origins = [view.GetViewStart()[1]]
    for _ in range(60):
        inject_wheel_notches(view, 1, up=False)
        pump_ui_events(wx_app)
        origin = view.GetViewStart()[1]
        if origin == origins[-1]:
            break
        origins.append(origin)
    return origins


@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_the_wheel_only_ever_rests_on_a_row_boundary(deck_selector_factory, wx_app, mode) -> None:
    """Wheel the mainboard from the top to the bottom: every origin is a stop."""
    frame = _floor_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, "main", mode)
        pump_ui_events(wx_app)
        view.Scroll(0, 0)

        stops = scroll_snap.snap_stops(view)
        assert stops is not None, (
            f"snapping is off for the mainboard {mode} view at the window's floor, "
            f"so this test would pass while asserting nothing "
            f"(client {view.GetClientSize().Get()}, step {view.scroll_snap_step()})"
        )
        origins = _wheel_to_the_bottom(view, wx_app)
        # Pinned so the sweep cannot pass by never moving -- the failure mode a
        # first draft of test_live_layout_overflow actually had.
        assert len(origins) > 3, f"the {mode} view only reached {origins}"
        assert origins[-1] == stops[-1], (
            f"the {mode} view did not wheel all the way to the bottom: "
            f"ended at {origins[-1]}, bottom is {stops[-1]}"
        )
        off_lattice = [y for y in origins if y not in stops]
        assert off_lattice == [], (
            f"the mainboard {mode} view rested at {off_lattice}, which are not row "
            f"boundaries -- the top row is sliced there. Stops: {stops[:8]}..."
        )
    finally:
        frame.Destroy()


@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_one_event_carrying_several_notches_moves_several_rows(
    deck_selector_factory, wx_app, mode
) -> None:
    """A flick is worth what its notches are worth, not what one notch is.

    ``_apply_wheel`` accumulates sub-notch rotation and can release several
    whole notches in a single event. Rounding the *total* pixel distance onto
    the lattice would collapse three 60px notches into one 232px row -- the
    scroll would silently be a third of what the user asked for, and only on
    free-spin wheels and touchpads.
    """
    frame = _floor_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, "main", mode)
        pump_ui_events(wx_app)
        stops = scroll_snap.snap_stops(view)
        assert stops is not None and len(stops) > 4

        view.Scroll(0, 0)
        inject_wheel_notches(view, 1, up=False)
        pump_ui_events(wx_app)
        one_notch = view.GetViewStart()[1]

        view.Scroll(0, 0)
        inject_wheel_notches(view, 3, up=False)
        pump_ui_events(wx_app)
        three_events = view.GetViewStart()[1]

        view.Scroll(0, 0)
        _apply_wheel(view, rotation=-360, delta=120, lines=3, horizontal=False)
        pump_ui_events(wx_app)
        one_event = view.GetViewStart()[1]

        assert one_notch in stops and three_events in stops
        assert three_events > one_notch, (
            "three notches did not travel further than one, so this test cannot "
            "tell a collapsed flick from a correct one"
        )
        assert one_event == three_events, (
            f"one event carrying three notches moved to {one_event}, but the same "
            f"three notches delivered separately reach {three_events}"
        )
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_a_pane_too_short_for_one_row_keeps_scrolling_freely(deck_selector_factory, wx_app) -> None:
    """The sideboard grid pane is shorter than a row, so it must not snap.

    Snapping a pane that cannot show one whole row anyway would leave it able to
    rest only at the top and the bottom -- the pane-quantisation outcome S5's
    original prescription would have produced, arrived at by another route.
    """
    frame = _floor_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, "side", "grid")
        pump_ui_events(wx_app)
        step, _phase = view.scroll_snap_step()
        client_h = view.GetClientSize().GetHeight()
        assert 0 < client_h < step, (
            "the sideboard grid pane is no longer shorter than one row at the "
            f"window's floor (client {client_h}, row {step}) -- this test is not "
            "exercising the short-pane branch any more"
        )
        assert scroll_snap.snap_stops(view) is None

        view.Scroll(0, 0)
        origins = _wheel_to_the_bottom(view, wx_app)
        assert len(origins) > 3, f"the short pane stopped scrolling: {origins}"
        # Free scrolling means the wheel's own pixel step, not a row.
        assert origins[1] - origins[0] < step
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_scrollbar_settles_on_a_boundary_and_its_arrows_move_a_whole_row(
    deck_selector_factory, wx_app
) -> None:
    """A gesture that ends off the lattice settles onto it; arrows move a row.

    At ``CARD_VIEW_SCROLL_RATE = 1`` wx moves an arrow-button click one *pixel*,
    which the settle would immediately undo -- a dead button. The arrows are
    handled instead of settled for exactly that reason.
    """
    frame = _floor_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, "main", "grid")
        pump_ui_events(wx_app)
        step, _phase = view.scroll_snap_step()
        stops = scroll_snap.snap_stops(view)
        assert stops is not None and len(stops) > 2

        # Where a thumb drag leaves it: a pixel origin off the lattice.
        view.Scroll(0, stops[1] + 7)
        assert view.GetViewStart()[1] == stops[1] + 7, "the view did not accept a raw origin"
        scroll_snap.settle(view)
        assert view.GetViewStart()[1] == stops[1]

        view.Scroll(0, 0)
        for event_type, expected in (
            (wx.wxEVT_SCROLLWIN_LINEDOWN, stops[1]),
            (wx.wxEVT_SCROLLWIN_LINEDOWN, stops[2]),
            (wx.wxEVT_SCROLLWIN_LINEUP, stops[1]),
        ):
            scroll_snap.handle_scrollwin(view, wx.ScrollWinEvent(event_type, 0, wx.VERTICAL))
            assert view.GetViewStart()[1] == expected
        assert stops[1] == step, "the first stop below the top should be one row down"
    finally:
        frame.Destroy()


@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_the_fade_marks_only_an_edge_with_content_past_it(
    deck_selector_factory, wx_app, mode
) -> None:
    """The fade is the scroll affordance, so it must be absent where it would lie."""
    frame = _floor_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, "main", mode)
        pump_ui_events(wx_app)
        client_h = view.GetClientSize().GetHeight()
        content_h = scroll_snap.content_height(view)
        assert content_h > client_h * 2, (
            f"the {mode} view is not deep enough to have a clipped edge at all "
            f"(content {content_h}, client {client_h})"
        )

        bitmap = wx.Bitmap(max(1, view.GetClientSize().GetWidth()), max(1, client_h))
        dc = wx.MemoryDC(bitmap)
        try:
            view.Scroll(0, 0)
            view.PrepareDC(dc)
            assert edge_fade.draw_edge_fades(view, dc, (0, 0, 0)) == (False, True)

            view.Scroll(0, content_h)  # clamps to the bottom
            dc.SetDeviceOrigin(0, 0)
            view.PrepareDC(dc)
            assert edge_fade.draw_edge_fades(view, dc, (0, 0, 0)) == (True, False)
        finally:
            dc.SelectObject(wx.NullBitmap)
    finally:
        frame.Destroy()


def test_the_fade_bitmap_is_opaque_at_the_edge_and_clear_inside() -> None:
    """The ramp's direction is the whole content of the affordance."""
    for top in (True, False):
        image = edge_fade._fade_bitmap(4, 16, top, (10, 20, 30)).ConvertToImage()
        alpha = [image.GetAlpha(0, y) for y in range(16)]
        edge, inside = (alpha[0], alpha[-1]) if top else (alpha[-1], alpha[0])
        assert edge == 255 and inside == 0
        assert alpha == sorted(alpha, reverse=top)


@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_the_card_views_keep_the_background_style_the_fade_needs(
    deck_selector_factory, wx_app, mode
) -> None:
    """``BG_STYLE_PAINT`` is what makes anything drawn into the buffer survive.

    Phase 5: with ``wx.*BufferedPaintDC`` and the default background style,
    wxMSW's own erase-background pass owns the client area and the buffer is
    discarded -- silently. The fade is the first thing that would vanish, and it
    would vanish only on screen, which is the twelfth instance of this
    codebase's signature failure waiting to happen. So it is a test.
    """
    frame = _floor_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, "main", mode)
        assert view.GetBackgroundStyle() == wx.BG_STYLE_PAINT
    finally:
        frame.Destroy()
