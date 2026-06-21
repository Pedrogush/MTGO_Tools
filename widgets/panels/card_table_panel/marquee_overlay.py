"""App-level marquee outline for the pile view's rubber-band selection.

The selection box must render across the whole application window rather than
clip at the pile view's own bounds, but a child widget can only paint inside
itself. So the outline is drawn by four thin, borderless, always-on-top popup
strips (the rectangle's edges) positioned in screen coordinates. Popups don't
take focus and aren't erased when the views underneath repaint mid-drag, and
four solid strips avoid needing a shaped/transparent window for the hollow
interior.
"""

from __future__ import annotations

import wx

from utils.constants import DARK_ACCENT

# Thickness, in px, of the rendered outline.
_BORDER = 2


def marquee_bounds(p1: wx.Point, p2: wx.Point) -> wx.Rect:
    """Normalised rectangle (positive size) framed by two corner points."""
    left, right = sorted((p1.x, p2.x))
    top, bottom = sorted((p1.y, p2.y))
    return wx.Rect(left, top, right - left, bottom - top)


def edge_strips(
    bounds: tuple[int, int, int, int], border: int = _BORDER
) -> list[tuple[int, int, int, int]] | None:
    """Pure ``(x, y, w, h)`` geometry for ``update``: the four framing strips.

    ``bounds`` is the normalised ``(x, y, w, h)`` rectangle. A degenerate box
    (sub-1px in either dimension) yields ``None`` — the caller should cancel
    rather than draw. Otherwise the four edge strips (top, bottom, left, right)
    are returned with each dimension clamped to ``>= 1`` so a thin/short box
    still produces visible strips. wx-free so the decision is unit-testable.
    """
    x, y, w, h = bounds
    if w < 1 or h < 1:
        return None
    return [
        (x, y, max(1, w), max(1, border)),  # top
        (x, y + h - border, max(1, w), max(1, border)),  # bottom
        (x, y, max(1, border), max(1, h)),  # left
        (x + w - border, y, max(1, border), max(1, h)),  # right
    ]


def edge_rects(outer: wx.Rect, border: int = _BORDER) -> list[wx.Rect]:
    """The four edge strips (top, bottom, left, right) framing ``outer``."""
    strips = edge_strips((outer.x, outer.y, outer.width, outer.height), border)
    return [wx.Rect(*strip) for strip in (strips or [])]


class MarqueeOverlay:
    """Four solid popup strips that frame a rectangle in screen coordinates."""

    def __init__(self, parent: wx.Window) -> None:
        self._strips = [self._make_strip(parent) for _ in range(4)]

    @staticmethod
    def _make_strip(parent: wx.Window) -> wx.PopupWindow:
        strip = wx.PopupWindow(parent, flags=wx.BORDER_NONE)
        strip.SetBackgroundColour(wx.Colour(*DARK_ACCENT))
        return strip

    def update(self, p1: wx.Point, p2: wx.Point) -> None:
        """Frame the rectangle with the (screen-space) corners ``p1`` and ``p2``."""
        rect = marquee_bounds(p1, p2)
        edges = edge_strips((rect.x, rect.y, rect.width, rect.height))
        if edges is None:
            self.cancel()
            return
        for strip, (ex, ey, ew, eh) in zip(self._strips, edges):
            strip.SetSize(ex, ey, ew, eh)
            if not strip.IsShown():
                strip.Show()

    def cancel(self) -> None:
        for strip in self._strips:
            if strip.IsShown():
                strip.Hide()
