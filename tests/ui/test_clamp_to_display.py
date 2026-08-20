"""Phase 8 — a companion window may not open larger than the screen.

``AppFrame`` has clamped its own restored size to ``wx.Display.GetClientArea()``
since before this redesign, and maximizes instead when its preferred size does
not fit. None of the other seventeen top-level windows did: their sizes are
constructor literals, and ``TOP_CARDS_FRAME_SIZE`` is **1400 x 740** against the
1366x768 laptop ``ui_layout.py`` names as the target -- 34px wider than the whole
screen and taller than what the taskbar leaves, with the right-hand columns and
the status row off the display and no way to reach them but dragging the window.
"""

from __future__ import annotations

import pytest
import wx

from widgets.stylize import clamp_to_display, init_top_level_window


@pytest.mark.usefixtures("wx_app")
def test_a_window_larger_than_the_display_is_shrunk_to_it() -> None:
    area = wx.Display(0).GetClientArea()
    frame = wx.Frame(None, size=(area.width * 2, area.height * 2))
    try:
        clamp_to_display(frame)
        size = frame.GetSize()
        assert size.GetWidth() <= area.width
        assert size.GetHeight() <= area.height
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_a_window_that_already_fits_is_left_exactly_alone() -> None:
    """It only ever shrinks. A window smaller than the screen is not centred,
    grown, or moved -- the sizes in ``utils/constants`` are deliberate."""
    frame = wx.Frame(None, size=(400, 300))
    try:
        before = frame.GetSize().Get()
        clamp_to_display(frame)
        assert frame.GetSize().Get() == before
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_minimum_comes_down_with_the_window() -> None:
    """A floor wider than the display is the state this exists to escape.

    wx will not honour a SetSize below the window's own minimum, so clamping
    without lowering the minimum first is a call that runs and does nothing --
    this codebase's signature failure, eleven documented instances.
    """
    area = wx.Display(0).GetClientArea()
    frame = wx.Frame(None, size=(area.width * 2, area.height * 2))
    try:
        frame.SetMinSize(wx.Size(area.width * 2, area.height * 2))
        clamp_to_display(frame)
        assert frame.GetSize().GetWidth() <= area.width
        assert frame.GetMinSize().GetWidth() <= area.width
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_a_maximized_window_is_skipped() -> None:
    """A maximized window's size legitimately exceeds the client area by the
    maximized frame border; resizing it here would silently un-maximize it."""
    frame = wx.Frame(None, size=(400, 300))
    try:
        frame.Show()
        frame.Maximize(True)
        clamp_to_display(frame)
        assert frame.IsMaximized()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_init_top_level_window_applies_the_clamp() -> None:
    """The wiring, not just the function.

    ``init_top_level_window`` is the one call every top-level window in the app
    already makes as its first statement (for the base font and the dark
    caption), which is why the clamp lives there rather than at eighteen
    construction sites -- but a helper nobody calls is the same as no helper.
    """
    area = wx.Display(0).GetClientArea()
    frame = wx.Frame(None, size=(area.width + 400, area.height + 400))
    try:
        init_top_level_window(frame)
        assert frame.GetSize().GetWidth() <= area.width
        assert frame.GetSize().GetHeight() <= area.height
    finally:
        frame.Destroy()
