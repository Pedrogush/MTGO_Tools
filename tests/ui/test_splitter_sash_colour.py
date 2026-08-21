"""The mainboard/sideboard sash stayed dark for the whole of a live drag.

What broke
----------
:class:`widgets.splitter.DarkSplitter` own-draws the sash gutter because wxMSW's
native one is a near-white ``#F0F0F0``/``#FFFFFF`` band and no colour call
reaches it (``docs/WXMSW_BEHAVIOUR.md``). It did that from ``EVT_PAINT`` alone,
and ``EVT_PAINT`` is not the only place wx paints the sash:
``wxSplitterWindow::SizeWindows()`` ends by drawing it **straight onto a
``wxClientDC``**, an immediate un-invalidated write that never becomes a
``WM_PAINT``.

Traced off the window surface, one step of a live drag ran in this order:

1. ``OnMouseEvent(MOTION)`` moved the panes,
2. ``EVT_PAINT`` filled the gutter with ``BORDER_SUBTLE``,
3. ``OnInternalIdle`` ran ``SizeWindows()``, which painted the native band on
   top of it.

The own-drawn colour lost every step because it was painted *first*. Measured on
the deck workspace, **14 of 15** drag steps left the light sash on screen, and a
screen-grabbed video of a real sweep caught it in 9 of 43 frames -- so the
divider strobed between ``#39424E`` and near-white at mouse-move cadence, the
brightest thing in a dark-themed window and a large flickering area.

What is pinned here
-------------------
The surface itself, which is the only thing that can see this. Every assertion
below reads pixels back with a ``ClientDC`` blit, deliberately **not** a
``PrintWindow`` capture: ``PrintWindow`` re-renders the widget tree, so it
reports the pixels the paint handler *intends* and hides this defect completely.
That is why the redesign's own screenshots walked past it for six phases.

Both paths to ``SizeWindows()`` are driven, because they are separate holes and
the fix plugs them in two different places:

* a live drag, through ``wxSplitterWindow``'s own ``OnMouseEvent`` -- deferred
  to ``OnInternalIdle``,
* a programmatic ``SetSashPosition`` -- run inline.

**What this cannot cover:** that no frame the compositor actually presents holds
the light band. That needs a real gesture and a screen grab; it was verified
that way (0 of 38 frames after the fix, 9 of 43 before) and stays a manual
check with ``automation.cli start-video --method screen``.
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


def _read_gutter(splitter: wx.SplitterWindow) -> list[tuple[int, int, int]]:
    """The sash band's pixels, read back off the window's own surface.

    A ``ClientDC`` blit, not ``wx.WindowDC``/``PrintWindow``: the defect is an
    un-invalidated write to this exact surface, and a re-render cannot see it.
    """
    size = splitter.GetClientSize()
    bitmap = wx.Bitmap(size)
    memory = wx.MemoryDC(bitmap)
    memory.Blit(0, 0, size.width, size.height, wx.ClientDC(splitter), 0, 0)
    memory.SelectObject(wx.NullBitmap)
    image = bitmap.ConvertToImage()

    position = splitter.GetSashPosition()
    sash = splitter.GetSashSize()
    x = min(40, size.width - 1)
    return [
        (image.GetRed(x, y), image.GetGreen(x, y), image.GetBlue(x, y))
        for y in range(position, min(size.height, position + sash))
    ]


def _native_rows(gutter: list[tuple[int, int, int]]) -> int:
    return sum(1 for pixel in gutter if pixel in NATIVE_SASH_COLOURS)


@pytest.fixture(name="split_frame")
def fixture_split_frame(wx_app: wx.App):
    """A shown frame holding one horizontally split :class:`DarkSplitter`.

    Shown and raised deliberately: an unmapped window has no surface to read
    back, so the whole measurement would be vacuous.
    """
    frame = wx.Frame(None, size=(500, 500))
    splitter = DarkSplitter(frame)
    top = wx.Panel(splitter)
    bottom = wx.Panel(splitter)
    splitter.SetMinimumPaneSize(40)
    splitter.SplitHorizontally(top, bottom, 200)
    frame.Show()
    frame.Raise()
    for _ in range(20):
        wx_app.Yield()
    yield splitter
    frame.Destroy()
    for _ in range(20):
        wx_app.Yield()


def test_sash_is_border_subtle_at_rest(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """The baseline the redesign already had: a still sash is ``BORDER_SUBTLE``."""
    wx_app.Yield()
    gutter = _read_gutter(split_frame)
    assert gutter, "no gutter pixels were read back; the frame has no surface"
    assert _native_rows(gutter) == 0, f"native sash colours at rest: {gutter}"
    assert gutter.count(SUBTLE) >= len(gutter) - 1, (
        f"the sash gutter is not BORDER_SUBTLE {SUBTLE}: {gutter}"
    )


def test_sash_stays_dark_through_a_live_mouse_drag(
    split_frame: DarkSplitter, wx_app: wx.App
) -> None:
    """The regression: ``SizeWindows()`` repainting the native sash mid-drag.

    The events go into ``wxSplitterWindow``'s own ``OnMouseEvent`` through the
    binding table a physical mouse's arrive on, which is what puts the deferred
    ``SizeWindows()`` -- the actual defect -- under test. ``SetSashPosition``
    would exercise the *other* path and leave this one unmeasured.
    """
    splitter = split_frame
    splitter.SetSashPosition(150)
    wx_app.Yield()

    def send(event_type: int, y: int, dragging: bool = False) -> None:
        event = wx.MouseEvent(event_type)
        event.SetEventObject(splitter)
        event.SetPosition(wx.Point(40, y))
        if dragging:
            event.SetLeftDown(True)
        splitter.GetEventHandler().ProcessEvent(event)

    # Grab the sash itself: +3 lands inside the 7px band, which is what
    # wxSplitterWindow's hit test requires before it will start a drag.
    send(wx.wxEVT_LEFT_DOWN, 153)

    offenders: list[tuple[int, list[tuple[int, int, int]]]] = []
    for target in range(160, 320, 10):
        send(wx.wxEVT_MOTION, target + 3, dragging=True)
        wx_app.Yield()
        gutter = _read_gutter(splitter)
        if _native_rows(gutter) >= 3:
            offenders.append((splitter.GetSashPosition(), gutter))
    send(wx.wxEVT_LEFT_UP, 323)
    wx_app.Yield()

    assert splitter.GetSashPosition() > 150, (
        "the drag never moved the sash, so nothing was measured -- "
        "check the hit test still accepts a press inside GetSashSize()"
    )
    assert offenders == [], (
        "wxSplitterWindow::SizeWindows() repainted the native near-white sash "
        f"during a live drag at sash positions {[pos for pos, _ in offenders]}; "
        "DarkSplitter.OnInternalIdle must run after it"
    )


def test_sash_stays_dark_through_a_programmatic_move(
    split_frame: DarkSplitter, wx_app: wx.App
) -> None:
    """The other hole: ``SetSashPosition`` runs ``SizeWindows()`` inline.

    No ``Yield`` between the move and the read. That is the point -- it is the
    gap before the event loop reaches idle that a screen grab caught the light
    band in, so the fix has to close it at the call rather than at the next
    idle round.
    """
    splitter = split_frame
    offenders: list[int] = []
    for position in range(150, 300, 10):
        splitter.SetSashPosition(position)
        if _native_rows(_read_gutter(splitter)) >= 3:
            offenders.append(position)

    assert offenders == [], (
        "SetSashPosition left the native near-white sash on the surface at "
        f"{offenders}; the repaint has to happen at the call, not at the next idle"
    )


def test_sash_survives_a_resize(split_frame: DarkSplitter, wx_app: wx.App) -> None:
    """``wxSplitterWindow::OnSize`` calls ``SizeWindows()`` too."""
    splitter = split_frame
    offenders: list[int] = []
    for width in (480, 460, 440, 420):
        splitter.GetParent().SetSize((width, 500))
        wx_app.Yield()
        if _native_rows(_read_gutter(splitter)) >= 3:
            offenders.append(width)

    assert offenders == [], (
        f"a resize left the native near-white sash on the surface at widths {offenders}"
    )
