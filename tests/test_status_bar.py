"""Behaviour of the own-drawn status strip that replaced ``wx.StatusBar``.

The strip is the app's primary feedback channel and three unrelated call paths
depend on its API — ``AppFramePropertiesMixin._set_status``, the update-available
handler for issue #142, and the automation server's ``get_status`` command. These
tests pin exactly the surface those three use, because a silent API drift there
shows up as "the app stopped reporting anything" rather than as an exception.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from utils.constants import theme as T

wx = pytest.importorskip("wx")

from widgets.status_bar import ThemedStatusBar  # noqa: E402


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def bar(app: object) -> Iterator[ThemedStatusBar]:
    frame = wx.Frame(None, size=(600, 400))
    strip = ThemedStatusBar(frame, 2)
    strip.SetSize((600, 22))
    yield strip
    frame.Destroy()


def _rgb(colour: object) -> tuple[int, int, int]:
    return (colour.Red(), colour.Green(), colour.Blue())


def test_uses_the_status_bar_tokens(bar: ThemedStatusBar) -> None:
    """The whole point of the replacement: wxMSW ignored the foreground."""
    assert _rgb(bar.GetBackgroundColour()) == T.STATUS_BAR_BG
    assert _rgb(bar.GetForegroundColour()) == T.STATUS_BAR_FG


def test_fields_round_trip(bar: ThemedStatusBar) -> None:
    bar.SetStatusText("Loaded 976 decks")
    bar.SetStatusText("Update available", 1)
    assert bar.GetStatusText() == "Loaded 976 decks"
    assert bar.GetStatusText(0) == "Loaded 976 decks"
    assert bar.GetStatusText(1) == "Update available"


def test_out_of_range_fields_are_inert() -> None:
    """wx.StatusBar asserts here; the app must not crash on a stray index."""
    frame = wx.Frame(None)
    try:
        strip = ThemedStatusBar(frame, 2)
        strip.SetStatusText("nope", 9)
        assert strip.GetStatusText(9) == ""
        assert strip.GetFieldRect(9) == wx.Rect()
    finally:
        frame.Destroy()


def test_field_rects_follow_the_wx_width_convention(bar: ThemedStatusBar) -> None:
    """Negative widths are proportions of the leftover space, positive are pixels."""
    bar.SetStatusWidths([-1, 160])
    bar.SetSize((600, 22))
    left, right = bar.GetFieldRect(0), bar.GetFieldRect(1)
    width = bar.GetClientSize().width
    assert right.width == pytest.approx(160, abs=1)
    assert left.x == 0
    assert right.x == pytest.approx(width - 160, abs=1)
    assert left.width + right.width == width


def test_update_field_hit_test_matches_the_click_handler(bar: ThemedStatusBar) -> None:
    """``_on_status_bar_click`` tests GetFieldRect(1).Contains(event.GetPosition()).

    The rects must therefore be in the strip's own client coordinates — which is
    the reason the strip draws its text instead of hosting child labels.
    """
    bar.SetStatusWidths([-1, 160])
    bar.SetSize((600, 22))
    rect = bar.GetFieldRect(1)
    assert rect.Contains(wx.Point(rect.x + 5, rect.y + 5))
    assert not rect.Contains(wx.Point(10, rect.y + 5))


def test_wrong_number_of_widths_is_rejected(bar: ThemedStatusBar) -> None:
    with pytest.raises(ValueError, match="expected 2 widths"):
        bar.SetStatusWidths([-1])


def test_a_status_bar_needs_a_field() -> None:
    frame = wx.Frame(None)
    try:
        with pytest.raises(ValueError, match="at least one field"):
            ThemedStatusBar(frame, 0)
    finally:
        frame.Destroy()


def test_ellipsize_shortens_only_when_it_has_to(bar: ThemedStatusBar) -> None:
    dc = wx.ClientDC(bar)
    dc.SetFont(bar.GetFont())
    text = "Loaded 976 decks for Modern. Click a deck to load it."
    full_width = dc.GetTextExtent(text)[0]
    assert bar._ellipsize(dc, text, full_width + 20) == text
    clipped = bar._ellipsize(dc, text, full_width // 2)
    assert clipped != text
    assert clipped.endswith("…")
    assert dc.GetTextExtent(clipped)[0] <= full_width // 2
    assert bar._ellipsize(dc, text, 0) == ""


def test_drawing_does_not_raise(bar: ThemedStatusBar) -> None:
    """The strip owns its own EVT_PAINT; a throw there would blank the window."""
    bar.SetStatusWidths([-1, 160])
    bar.SetStatusText("Deck ready", 0)
    bar.SetStatusText("v1.2.0 available", 1)
    bitmap = wx.Bitmap(*bar.GetClientSize())
    dc = wx.MemoryDC(bitmap)
    bar._draw(dc)
    dc.SelectObject(wx.NullBitmap)


def test_drawing_survives_a_zero_width_strip(bar: ThemedStatusBar) -> None:
    """A collapsed pane must not make the ellipsis search or the rect maths blow up."""
    bar.SetSize((1, 22))
    bar.SetStatusText("Deck ready", 0)
    bitmap = wx.Bitmap(1, 22)
    dc = wx.MemoryDC(bitmap)
    bar._draw(dc)
    dc.SelectObject(wx.NullBitmap)
