"""The mainboard/sideboard sash is never wxMSW's near-white one, on any path.

What broke
----------
:class:`widgets.splitter.DarkSplitter` own-draws the sash gutter because wxMSW's
native one is a near-white ``#F0F0F0``/``#FFFFFF`` band and no colour call
reaches it (``docs/WXMSW_BEHAVIOUR.md``). It did that from ``EVT_PAINT``, and
``EVT_PAINT`` is not the only place wx paints the sash:
``wxSplitterWindow::SizeWindows()`` ends by drawing it **straight onto a
``wxClientDC``**, an immediate un-invalidated write that never becomes a
``WM_PAINT``.

The first fix chased that draw with a repaint after it, on the two call sites
known at the time. It missed the rest, and the miss was invisible because the
measurement sampled **one column** of a ~1585px band. Re-measured across the
whole band, ``wxSplitterWindow::OnSize`` and ``UpdateSize()`` were still leaving
the native sash across **100% of the gutter** (9,408 of 9,408 pixels) -- so every
window resize and every side-panel collapse flashed a full-width white bar.
Caught off the screen, that was **25 of 90 frames** of a panel-toggle capture,
the band persisting for hundreds of milliseconds at a time.

What is pinned here
-------------------
The surface itself, which is the only thing that can see this, and **the whole
band** rather than a column. Every assertion reads pixels back with a
``ClientDC`` blit, deliberately not a ``PrintWindow`` capture: ``PrintWindow``
re-renders the widget tree, so it reports the pixels the paint handler *intends*
and hides this defect completely.

Every path that reaches ``SizeWindows()`` is driven, and each is checked
**before** the event loop is allowed to reach idle -- that gap is precisely
where a screen frame catches the white band:

* a live drag through ``wxSplitterWindow``'s own ``OnMouseEvent``,
* a programmatic ``SetSashPosition``,
* a resize (``wxSplitterWindow::OnSize``),
* an explicit ``UpdateSize()``,
* hide/show, as a notebook tab switch does.

:func:`test_the_gutter_is_border_subtle_not_merely_not_white` is the positive
control: "no native pixels" would also pass if the gutter were black, empty or
unpainted, so the divider is asserted to actually be there.

:func:`test_a_real_click_on_the_sash_starts_a_drag` is the other one. Every
colour assertion above keeps passing on a sash that cannot be moved at all --
which is exactly what shipped once the overlay went in, because it forwarded a
mouse position in *its* coordinates as if they were the splitter's. See
:func:`_send` for why building these events by hand is what hid it.

**What this cannot cover:** that no frame the compositor actually presents holds
the light band. That needs a real gesture and a screen grab; it was verified that
way (0 of 140 frames across drags and panel toggles after the fix, 25 of 90
panel-toggle frames before) and stays a manual check with
``automation.cli start-video --method screen``.
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from utils.constants.theme import BORDER_SUBTLE  # noqa: E402
from widgets.splitter import DarkSplitter  # noqa: E402

#: What ``wxRendererNative`` paints a 3-D sash with, sampled off a probe frame:
#: a ``#F0F0F0`` band around a ``#FFFFFF`` centre line, closed by ``#A0A0A0``
#: and ``#696969`` shadow rows.
NATIVE_SASH_COLOURS = {
    (0xF0, 0xF0, 0xF0),
    (0xFF, 0xFF, 0xFF),
    (0xA0, 0xA0, 0xA0),
    (0x69, 0x69, 0x69),
}
SUBTLE = tuple(BORDER_SUBTLE)


def _gutter_pixels(splitter: wx.SplitterWindow) -> list[tuple[int, int, int]]:
    """**Every** pixel of the sash band, read off the window's own surface.

    A ``ClientDC`` blit, not ``wx.WindowDC``/``PrintWindow``: the defect is an
    un-invalidated write to this exact surface and a re-render cannot see it.

    The whole band, not one column: the previous version of this helper sampled
    ``x = 40`` alone and reported zero while ``OnSize`` was painting the band end
    to end. ``GetData()`` rather than per-pixel ``GetRed`` so scanning thousands
    of pixels per assertion stays cheap.
    """
    if not splitter.IsSplit():
        return []
    size = splitter.GetClientSize()
    position = splitter.GetSashPosition()
    sash = splitter.GetSashSize()
    if sash <= 0 or size.width <= 0 or size.height <= 0:
        return []
    if splitter.GetSplitMode() == wx.SPLIT_VERTICAL:
        rect = wx.Rect(position, 0, sash, size.height)
    else:
        rect = wx.Rect(0, position, size.width, sash)
    rect = rect.Intersect(wx.Rect(0, 0, size.width, size.height))
    if rect.width <= 0 or rect.height <= 0:
        return []

    bitmap = wx.Bitmap(rect.width, rect.height)
    memory = wx.MemoryDC(bitmap)
    memory.Blit(0, 0, rect.width, rect.height, wx.ClientDC(splitter), rect.x, rect.y)
    memory.SelectObject(wx.NullBitmap)
    raw = bitmap.ConvertToImage().GetData()
    return [tuple(raw[i : i + 3]) for i in range(0, len(raw), 3)]


def _native_pixels(splitter: wx.SplitterWindow) -> int:
    return sum(1 for pixel in _gutter_pixels(splitter) if pixel in NATIVE_SASH_COLOURS)


def _send(
    splitter: wx.SplitterWindow,
    window: wx.Window,
    event_type: int,
    where: wx.Point,
    dragging: bool = False,
) -> None:
    """Post a mouse event the way wxMSW delivers one, **not** the way it reads.

    ``where`` is in the splitter's client coordinates, because that is what a
    reader of these tests is thinking in. It is then converted into ``window``'s
    own coordinates before being sent, because that is what wxMSW puts in a real
    ``WM_MOUSEMOVE``: a mouse event's position is relative to the window it is
    delivered to.

    That conversion is the entire reason this helper exists. The sash band
    belongs to :class:`widgets.splitter._SashOverlay`, a child sized to the band
    and therefore *not* at the splitter's origin, so a real click on the middle
    of a 7px sash reaches the overlay as ``3``, not as ``sash_position + 3``. An
    earlier version of this module built its events by hand and handed the
    overlay splitter coordinates, which made a broken forward look correct and
    let an undraggable sash ship.
    """
    event = wx.MouseEvent(event_type)
    event.SetEventObject(window)
    event.SetPosition(window.ScreenToClient(splitter.ClientToScreen(where)))
    if dragging:
        event.SetLeftDown(True)
    window.GetEventHandler().ProcessEvent(event)


@pytest.fixture(name="split_frame")
def fixture_split_frame(wx_app: wx.App):
    """A shown frame holding one horizontally split :class:`DarkSplitter`.

    Wide on purpose: a partial-width native draw needs room to show, and the
    real deck workspace's sash is ~1585px. Shown and raised deliberately -- an
    unmapped window has no surface to read back, so the measurement would be
    vacuous.
    """
    frame = wx.Frame(None, size=(1100, 700))
    splitter = DarkSplitter(frame)
    top = wx.Panel(splitter)
    top.SetBackgroundColour(wx.Colour(0x22, 0x27, 0x2E))
    bottom = wx.Panel(splitter)
    bottom.SetBackgroundColour(wx.Colour(0x22, 0x27, 0x2E))
    splitter.SetMinimumPaneSize(60)
    splitter.SplitHorizontally(top, bottom, 300)
    frame.Show()
    frame.Raise()
    for _ in range(25):
        wx_app.Yield()
    yield splitter
    frame.Destroy()
    for _ in range(20):
        wx_app.Yield()


def test_the_gutter_is_border_subtle_not_merely_not_white(
    split_frame: DarkSplitter, wx_app: wx.App
) -> None:
    """The positive control for every other assertion in this module.

    "No native pixels" would also pass on a gutter that was black, empty or
    never painted, so the divider is asserted to actually *be* ``BORDER_SUBTLE``.
    """
    wx_app.Yield()
    pixels = _gutter_pixels(split_frame)
    assert pixels, "no gutter pixels were read back; the frame has no surface"
    subtle = sum(1 for pixel in pixels if pixel == SUBTLE)
    assert subtle >= len(pixels) * 0.99, (
        f"the sash gutter is not BORDER_SUBTLE {SUBTLE}: "
        f"{subtle}/{len(pixels)} px matched; sample={pixels[:6]}"
    )


def test_a_real_click_on_the_sash_starts_a_drag(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """The sash is still draggable, which the colour tests cannot tell you.

    The regression this pins: the overlay covers the band, so a real pointer
    lands on the *overlay*, and its position arrives in the overlay's own
    coordinates -- ``3``, for a click on the middle of a 7px sash. Forwarded to
    ``wxSplitterWindow::OnMouseEvent`` untranslated, that reads as 3px from the
    splitter's edge, ``SashHitTest`` refuses, and the sash cannot be moved at
    all. Verified against a physical Win32 ``SendInput`` drag, which moved the
    sash 0px with the untranslated forward and 120px with it.

    Every other test here would keep passing through that, because the band goes
    on being painted the right colour while nothing can move it.

    The press goes to the overlay because that is the window under the pointer;
    the rest of the gesture goes to the splitter because ``OnMouseEvent``
    captures the mouse on the press, and wxMSW routes to the capturing window
    from then on.
    """
    splitter = split_frame
    overlay = splitter.GetChildren()[0]
    splitter.SetSashPosition(200)
    wx_app.Yield()

    grab = wx.Point(40, splitter.GetSashPosition() + splitter.GetSashSize() // 2)
    drop = wx.Point(40, grab.y + 120)
    _send(splitter, overlay, wx.wxEVT_LEFT_DOWN, grab)
    wx_app.Yield()
    _send(splitter, splitter, wx.wxEVT_MOTION, drop, dragging=True)
    wx_app.Yield()
    _send(splitter, splitter, wx.wxEVT_LEFT_UP, drop)
    wx_app.Yield()

    assert splitter.GetSashPosition() == 320, (
        "a press on the sash band did not start a drag: the sash is at "
        f"{splitter.GetSashPosition()}, not 320. The overlay must translate a "
        "forwarded mouse position into the splitter's coordinates."
    )
    assert (
        overlay.GetRect().y == 320
    ), f"the sash moved but the overlay did not follow it: {overlay.GetRect()}"


def test_no_native_sash_through_a_live_mouse_drag(
    split_frame: DarkSplitter, wx_app: wx.App
) -> None:
    """The drag path: ``SizeWindows()`` deferred to ``OnInternalIdle``.

    The events go into ``wxSplitterWindow``'s own ``OnMouseEvent`` through the
    binding table a physical mouse's arrive on: the press to the **overlay**,
    which is the window a real pointer lands on, and the moves to the splitter,
    which has captured the mouse by then. :func:`_send` converts each position
    into the receiving window's coordinates, as wxMSW does.
    """
    splitter = split_frame
    overlay = splitter.GetChildren()[0]
    splitter.SetSashPosition(200)
    wx_app.Yield()

    # +3 lands inside the 7px band, which is what wxSplitterWindow's hit test
    # requires before it will start a drag.
    _send(splitter, overlay, wx.wxEVT_LEFT_DOWN, wx.Point(40, 203))

    offenders: list[tuple[str, int, int]] = []
    for target in range(210, 500, 20):
        _send(splitter, splitter, wx.wxEVT_MOTION, wx.Point(40, target + 3), dragging=True)
        native = _native_pixels(splitter)
        if native:
            offenders.append(("no-yield", target, native))
        wx_app.Yield()
        native = _native_pixels(splitter)
        if native:
            offenders.append(("after-yield", target, native))
    _send(splitter, splitter, wx.wxEVT_LEFT_UP, wx.Point(40, 503))
    wx_app.Yield()

    assert splitter.GetSashPosition() > 200, (
        "the drag never moved the sash, so nothing was measured -- the overlay "
        "must forward mouse events to wxSplitterWindow::OnMouseEvent"
    )
    assert offenders == [], f"native sash pixels during a live drag: {offenders}"


def test_no_native_sash_through_a_programmatic_move(
    split_frame: DarkSplitter, wx_app: wx.App
) -> None:
    """``SetSashPosition`` runs ``SizeWindows()`` inline.

    Checked with no ``Yield`` between the move and the read: that gap, before
    the loop reaches idle, is where a screen capture caught the band.
    """
    splitter = split_frame
    offenders: list[tuple[int, int]] = []
    for position in range(200, 460, 20):
        splitter.SetSashPosition(position)
        native = _native_pixels(splitter)
        if native:
            offenders.append((position, native))

    assert offenders == [], f"native sash pixels after SetSashPosition: {offenders}"


def test_no_native_sash_through_a_resize(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """``wxSplitterWindow::OnSize`` runs ``SizeWindows()`` inline too.

    This is the one the first fix missed entirely, and the one a user actually
    hits: every window resize and every side-panel collapse goes through it.
    Both directions are driven -- **growing** is its own case, because it exposes
    a strip an overlay sized to the client area would not cover yet.
    """
    splitter = split_frame
    frame = splitter.GetParent()
    offenders: list[tuple[str, int]] = []
    for width, height in ((1060, 680), (1020, 660), (1120, 720), (1160, 740), (1080, 690)):
        frame.SetSize((width, height))
        native = _native_pixels(splitter)
        if native:
            offenders.append((f"no-yield@{width}x{height}", native))
        wx_app.Yield()
        native = _native_pixels(splitter)
        if native:
            offenders.append((f"after-yield@{width}x{height}", native))

    assert offenders == [], f"native sash pixels after a resize: {offenders}"


def test_no_native_sash_through_update_size(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """``UpdateSize()`` is the public ``SizeWindows()``."""
    splitter = split_frame
    offenders: list[int] = []
    for _ in range(4):
        splitter.UpdateSize()
        native = _native_pixels(splitter)
        if native:
            offenders.append(native)
        wx_app.Yield()

    assert offenders == [], f"native sash pixels after UpdateSize(): {offenders}"


def test_no_native_sash_through_hide_and_show(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """A notebook tab switch, which is what the deck workspace's split lives in."""
    splitter = split_frame
    offenders: list[str] = []
    for index in range(3):
        splitter.Hide()
        wx_app.Yield()
        splitter.Show()
        if _native_pixels(splitter):
            offenders.append(f"no-yield#{index}")
        wx_app.Yield()
        if _native_pixels(splitter):
            offenders.append(f"after-yield#{index}")

    assert offenders == [], f"native sash pixels after hide/show: {offenders}"


def test_the_overlay_never_covers_a_pane(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """The overlay is the sash band and nothing more.

    A full-client-area overlay was tried first and is the reason this test
    exists: ``Lower()`` does not stop a child painting over its siblings and
    neither does ``wx.CLIP_SIBLINGS``, so it filled both panes with
    ``BORDER_SUBTLE`` and wiped the card views out -- while every gutter-only
    measurement still reported a clean pass. Sizing it to the band makes that
    impossible, and this pins it.
    """
    splitter = split_frame
    children = list(splitter.GetChildren())
    assert len(children) == 3, f"expected overlay + two panes, got {children}"
    overlay = children[0]
    assert not isinstance(
        overlay, wx.Panel
    ), f"the first child should be the sash overlay, not a pane: {children}"
    rect = overlay.GetRect()
    assert rect.height == splitter.GetSashSize(), (
        f"overlay {rect} is not the height of the {splitter.GetSashSize()}px sash "
        "band; anything taller covers a pane"
    )
    assert (
        rect.y == splitter.GetSashPosition()
    ), f"overlay {rect} is not at the sash position {splitter.GetSashPosition()}"


def test_the_gravity_prediction_matches_wx(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """``_predicted_position`` must agree with where wx actually puts the sash.

    The overlay is placed from that prediction *before* ``wxSplitterWindow::
    OnSize`` runs its inline ``SizeWindows()``, because placing it at the
    current position leaves it stale and lets the native band show. So the
    prediction is a hand-written mirror of wx's gravity arithmetic, and an
    unpinned mirror silently drifts the moment wx changes it.

    Pinned against wx's own answer rather than against a recomputation of the
    same formula -- comparing an implementation to itself would pass while both
    were wrong. The spy captures each prediction as it is made, since both
    inputs (`GetSashPosition`, `_last_client`) have already moved on by the time
    the resize settles.

    A wrong prediction costs a frame of white rather than correctness --
    ``OnInternalIdle`` still corrects the overlay afterwards -- which is exactly
    why it needs a test: nothing else would ever report it.
    """
    splitter = split_frame
    splitter.SetSashGravity(0.6)
    for _ in range(10):
        wx_app.Yield()

    predictions: list[int] = []
    original = splitter._predicted_position

    def spy(new_client: wx.Size) -> int:
        predicted = original(new_client)
        predictions.append(predicted)
        return predicted

    splitter._predicted_position = spy  # type: ignore[method-assign]
    try:
        mismatches: list[tuple[int, int]] = []
        for height in (640, 580, 700, 660):
            predictions.clear()
            splitter.GetParent().SetSize((1100, height))
            for _ in range(15):
                wx_app.Yield()
            if not predictions:
                continue
            actual = splitter.GetSashPosition()
            if predictions[-1] != actual:
                mismatches.append((predictions[-1], actual))
    finally:
        del splitter._predicted_position

    assert predictions or mismatches, (
        "_predicted_position was never called, so nothing was pinned -- "
        "check that DarkSplitter still places the overlay from the size event"
    )
    assert mismatches == [], (
        "_predicted_position disagrees with wxSplitterWindow::OnSize "
        f"(predicted, actual): {mismatches}"
    )
