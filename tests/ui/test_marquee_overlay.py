"""Geometry tests for the app-level marquee outline overlay."""

from __future__ import annotations

import wx

from widgets.panels.card_table_panel.marquee_overlay import (
    edge_rects,
    marquee_bounds,
)


def test_marquee_bounds_normalises_any_corner_order():
    # Corners given bottom-right -> top-left still yield a positive-size rect.
    rect = marquee_bounds(wx.Point(10, 50), wx.Point(4, 20))
    assert (rect.x, rect.y, rect.width, rect.height) == (4, 20, 6, 30)


def test_marquee_bounds_zero_size_for_coincident_points():
    rect = marquee_bounds(wx.Point(7, 7), wx.Point(7, 7))
    assert (rect.width, rect.height) == (0, 0)


def test_edge_rects_frame_the_rectangle_in_screen_space():
    top, bottom, left, right = edge_rects(wx.Rect(100, 200, 60, 40), border=2)
    # Top/bottom span the full width; left/right span the full height.
    assert (top.x, top.y, top.width, top.height) == (100, 200, 60, 2)
    assert (bottom.x, bottom.y, bottom.width, bottom.height) == (100, 238, 60, 2)
    assert (left.x, left.y, left.width, left.height) == (100, 200, 2, 40)
    assert (right.x, right.y, right.width, right.height) == (158, 200, 2, 40)
