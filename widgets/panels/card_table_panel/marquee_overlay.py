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


def edge_rects(outer: wx.Rect, border: int = _BORDER) -> list[wx.Rect]:
    """The four edge strips (top, bottom, left, right) framing ``outer``."""
    x, y, w, h = outer.x, outer.y, outer.width, outer.height
    return [
        wx.Rect(x, y, w, border),  # top
        wx.Rect(x, y + h - border, w, border),  # bottom
        wx.Rect(x, y, border, h),  # left
        wx.Rect(x + w - border, y, border, h),  # right
    ]


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
        if rect.width < 1 or rect.height < 1:
            self.cancel()
            return
        for strip, edge in zip(self._strips, edge_rects(rect)):
            strip.SetSize(edge.x, edge.y, max(1, edge.width), max(1, edge.height))
            if not strip.IsShown():
                strip.Show()

    def cancel(self) -> None:
        for strip in self._strips:
            if strip.IsShown():
                strip.Hide()
