"""Shared mouse-wheel scrolling for the deck card views (grid + pile).

Both views use a 1px scroll *rate* (``CARD_VIEW_SCROLL_RATE``) so the scrollbar
thumb positions cards with single-pixel precision. At that rate wx's built-in
wheel handling would crawl (it scrolls in units of the rate), so this helper
reproduces the built-in behaviour explicitly and identically for both views:

* Accumulate wheel rotation and only act on whole notches — exactly what
  ``wxScrollHelperBase`` does. This is what keeps high-resolution / free-spin
  wheels and touchpads responsive: without it, every micro-rotation event would
  trigger its own ``Scroll`` + repaint and the paint queue backlogs, which is
  felt as a lag before a direction change takes effect.
* Scroll ``lines_per_action * CARD_VIEW_WHEEL_LINE_PX`` pixels per notch, where
  ``lines_per_action`` follows the OS "lines to scroll per notch" setting. At
  the default of 3 lines this is 60px/notch — the same distance the views moved
  under the old 20px scroll rate.
"""

from __future__ import annotations

import wx

from utils.constants import CARD_VIEW_WHEEL_LINE_PX, CARD_VIEW_WHEEL_LINES_PER_NOTCH

# wx reports 120 per physical notch; guard against a 0 from odd drivers.
_DEFAULT_WHEEL_DELTA = 120


def scroll_by_wheel(window: wx.ScrolledWindow, event: wx.MouseEvent) -> None:
    """Scroll ``window`` in response to a mouse-wheel ``event``.

    The window must use a 1px scroll rate so view-start units equal pixels.
    A horizontal wheel — or Shift+wheel, the usual convention — scrolls the
    horizontal axis; otherwise the vertical axis moves.
    """
    rotation = event.GetWheelRotation()
    delta = event.GetWheelDelta() or _DEFAULT_WHEEL_DELTA

    # Carry sub-notch rotation across events so nothing is lost or over-fired.
    accumulated = getattr(window, "_wheel_accum", 0) + rotation
    notches = int(accumulated / delta)
    window._wheel_accum = accumulated - notches * delta  # type: ignore[attr-defined]
    if notches == 0:
        return

    lines = event.GetLinesPerAction()
    if lines <= 0:
        lines = CARD_VIEW_WHEEL_LINES_PER_NOTCH
    # Positive rotation scrolls toward the start (up / left), so subtract.
    offset = notches * lines * CARD_VIEW_WHEEL_LINE_PX

    view_x, view_y = window.GetViewStart()
    horizontal = event.GetWheelAxis() == wx.MOUSE_WHEEL_HORIZONTAL or event.ShiftDown()
    if horizontal:
        window.Scroll(max(0, view_x - offset), view_y)
    else:
        window.Scroll(view_x, max(0, view_y - offset))
