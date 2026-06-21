"""Geometry tests for the app-level marquee outline overlay."""

from __future__ import annotations

import wx

from widgets.panels.card_table_panel.marquee_overlay import (
    edge_rects,
    edge_strips,
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


# ----- edge_strips: the pure decision/clamp behind MarqueeOverlay.update -----


def test_edge_strips_returns_none_for_degenerate_box():
    # Sub-1px in either dimension => caller should cancel (draw nothing).
    assert edge_strips((10, 10, 0, 40)) is None
    assert edge_strips((10, 10, 40, 0)) is None


def test_edge_strips_frames_a_valid_box_top_bottom_left_right():
    top, bottom, left, right = edge_strips((100, 200, 60, 40), border=2)
    assert top == (100, 200, 60, 2)
    assert bottom == (100, 238, 60, 2)
    assert left == (100, 200, 2, 40)
    assert right == (158, 200, 2, 40)


def test_edge_strips_clamps_thin_box_to_at_least_one_px_strips():
    # A 1x1 box still yields strips with every dimension >= 1px.
    strips = edge_strips((5, 5, 1, 1), border=2)
    assert strips is not None
    for _x, _y, w, h in strips:
        assert w >= 1
        assert h >= 1
