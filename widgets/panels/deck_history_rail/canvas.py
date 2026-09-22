"""The rail's painted column of versions.

A compact cousin of :class:`~widgets.panels.deck_history_panel.graph_canvas.DeckGraphCanvas`,
sharing its placement and its lane colours but not its proportions. The tab's
canvas gives each version a 46px band holding a message and a timestamp; at rail
width there is room for a lane dot and a short sha, and everything else moves to
the tooltip.

Kept separate rather than added to the tab's canvas as a "compact" flag: the two
differ in what a click *means* (there, select; here, check out), which is not a
difference a drawing option should be carrying.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import wx

from utils.constants.theme import (
    ACCENT_PRIMARY,
    BORDER_SUBTLE,
    SELECTION_FILL_ON_PANEL,
    SURFACE_PANEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from widgets.panels.deck_history_panel.graph_canvas import LANE_COLORS, TIMESTAMP_FORMAT
from widgets.panels.deck_history_panel.layout import GraphLayout
from widgets.stylize import type_font

ROW_HEIGHT = 26
LANE_WIDTH = 13
GRAPH_LEFT_PAD = 11
TEXT_GAP = 9
NODE_RADIUS = 4
HEAD_RING_RADIUS = 7
EMPTY_TEXT_INSET = 10


class DeckRailCanvas(wx.ScrolledWindow):
    """Paints the deck's versions as a narrow column and checks one out on click."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        on_activate: Callable[[str], None] | None = None,
        empty_text: str = "",
    ) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(0, ROW_HEIGHT)

        self._layout = GraphLayout()
        self._head: str | None = None
        self._hover: str | None = None
        self._on_activate = on_activate
        self._empty_text = empty_text

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    # ------------------------------------------------------------------ state ------------------------------------------------------------------
    def set_layout(self, layout: GraphLayout) -> None:
        self._layout = layout
        self._head = next(
            (n.sha for n in layout.nodes if n.graph_commit.commit.is_head),
            None,
        )
        if self._hover is not None and layout.node_for(self._hover) is None:
            self._hover = None
        self.SetVirtualSize(
            (self.GetClientSize().GetWidth(), max(len(layout.nodes) * ROW_HEIGHT, 1))
        )
        self.Refresh()

    @property
    def head_sha(self) -> str | None:
        return self._head

    # ------------------------------------------------------------------ hit testing ------------------------------------------------------------------
    def _node_at(self, point: wx.Point):
        _x, y = self.CalcUnscrolledPosition(point)
        row = y // ROW_HEIGHT
        if row < 0 or row >= len(self._layout.nodes):
            return None
        return next((n for n in self._layout.nodes if n.row == row), None)

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        node = self._node_at(event.GetPosition())
        if node is None or self._on_activate is None:
            return
        # Already on it: a checkout would be a no-op that still rewrites the
        # user's file, so it is simply not one.
        if node.sha == self._head:
            return
        self._on_activate(node.sha)

    def _on_motion(self, event: wx.MouseEvent) -> None:
        node = self._node_at(event.GetPosition())
        sha = node.sha if node is not None else None
        if sha == self._hover:
            return
        self._hover = sha
        self.SetToolTip(self._tooltip_for(node) if node is not None else None)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if sha and sha != self._head else wx.CURSOR_ARROW))
        self.Refresh()

    def _on_leave(self, _event: wx.MouseEvent) -> None:
        if self._hover is None:
            return
        self._hover = None
        self.Refresh()

    @staticmethod
    def _tooltip_for(node) -> str:
        """Everything the tab's two text lines would have said, in one string."""
        commit = node.graph_commit.commit
        lines = [node.graph_commit.label, node.graph_commit.short_sha]
        if not commit.is_baseline:
            lines[-1] += "  ·  " + datetime.fromtimestamp(commit.timestamp).strftime(
                TIMESTAMP_FORMAT
            )
        if commit.branches:
            lines.append(", ".join(commit.branches))
        return "\n".join(lines)

    # ------------------------------------------------------------------ painting ------------------------------------------------------------------
    def _lane_x(self, lane: int) -> int:
        return GRAPH_LEFT_PAD + lane * LANE_WIDTH

    def _row_y(self, row: int) -> int:
        return row * ROW_HEIGHT + ROW_HEIGHT // 2

    @staticmethod
    def _lane_colour(lane: int) -> wx.Colour:
        return wx.Colour(*LANE_COLORS[lane % len(LANE_COLORS)])

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        self.DoPrepareDC(dc)
        dc.SetBackground(wx.Brush(wx.Colour(*SURFACE_PANEL)))
        dc.Clear()

        if not self._layout.nodes:
            dc.SetFont(type_font("caption"))
            dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
            dc.DrawText(self._empty_text, EMPTY_TEXT_INSET, EMPTY_TEXT_INSET)
            return

        gc = wx.GraphicsContext.Create(dc)
        # Same order as the tab's canvas, for the same reason: the hover fill is
        # a full-width rectangle and would erase the graph line crossing it.
        self._draw_hover(dc)
        if gc is not None:
            self._draw_edges(gc)
        self._draw_nodes(dc)

    def _draw_hover(self, dc: wx.DC) -> None:
        node = self._layout.node_for(self._hover) if self._hover else None
        if node is None:
            return
        dc.SetPen(wx.Pen(wx.Colour(*BORDER_SUBTLE), 1))
        dc.SetBrush(wx.Brush(wx.Colour(*SELECTION_FILL_ON_PANEL)))
        dc.DrawRectangle(0, node.row * ROW_HEIGHT, self.GetVirtualSize().GetWidth(), ROW_HEIGHT)

    def _draw_edges(self, gc: wx.GraphicsContext) -> None:
        for edge in self._layout.edges:
            gc.SetPen(wx.Pen(self._lane_colour(edge.child_lane), 2))
            child_x = self._lane_x(edge.child_lane)
            parent_x = self._lane_x(edge.parent_lane)
            child_y = self._row_y(edge.child_row)
            parent_y = self._row_y(edge.parent_row)
            path = gc.CreatePath()
            path.MoveToPoint(child_x, child_y)
            if edge.is_fork:
                # An elbow down the child's lane, then across into the parent's,
                # so a fork reads as one branch leaving another.
                path.AddLineToPoint(child_x, parent_y)
                path.AddLineToPoint(parent_x, parent_y)
            else:
                path.AddLineToPoint(parent_x, parent_y)
            gc.StrokePath(path)

    def _draw_nodes(self, dc: wx.DC) -> None:
        font = type_font("caption")
        dc.SetFont(font)
        text_x = self._lane_x(max(self._layout.lane_count - 1, 0)) + TEXT_GAP

        for node in self._layout.nodes:
            commit = node.graph_commit.commit
            x = self._lane_x(node.lane)
            y = self._row_y(node.row)
            colour = self._lane_colour(node.lane)

            if commit.is_head:
                dc.SetPen(wx.Pen(wx.Colour(*ACCENT_PRIMARY), 2))
                dc.SetBrush(wx.Brush(wx.Colour(*SURFACE_PANEL)))
                dc.DrawCircle(x, y, HEAD_RING_RADIUS)

            dc.SetPen(wx.Pen(colour, 1))
            dc.SetBrush(wx.Brush(colour))
            dc.DrawCircle(x, y, NODE_RADIUS)

            dc.SetTextForeground(wx.Colour(*(TEXT_PRIMARY if commit.is_head else TEXT_SECONDARY)))
            label = node.graph_commit.short_sha
            _w, h = dc.GetTextExtent(label)
            dc.DrawText(label, text_x, y - h // 2)
