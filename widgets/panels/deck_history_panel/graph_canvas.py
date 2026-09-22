"""The painted commit graph.

wxPython ships no commit-graph control, and the DAG-layout libraries that a web
frontend would reach for have no wx equivalent, so this draws the graph itself
on a :class:`wx.ScrolledWindow`. The placement it paints comes from
:mod:`widgets.panels.deck_history_panel.layout`, which imports no wx -- so the
question "did the fork land in the right lane?" is answered by a unit test, and
this module only has to be right about pixels.

Clicking a node here selects it and nothing more: this canvas sits beside a
preview pane, so a click means "show me that version", and checking out is the
node's context menu. The rail's canvas
(:mod:`widgets.panels.deck_history_rail.canvas`) makes the opposite choice for
the opposite reason -- it has nothing to preview *into*, so a click there is the
move itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import wx

from utils.constants.theme import (
    ACCENT_PRIMARY,
    ACCENT_TEXT,
    BORDER_SUBTLE,
    SELECTION_FILL_ON_PANEL,
    SURFACE_PANEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from widgets.panels.deck_history_panel.layout import GraphLayout
from widgets.stylize import type_font

ROW_HEIGHT = 46
LANE_WIDTH = 22
GRAPH_LEFT_PAD = 16
TEXT_GAP = 14
NODE_RADIUS = 5
HEAD_RING_RADIUS = 9

#: Where each row's two text lines sit inside its band.
LABEL_TOP = 6
META_TOP = 25
EMPTY_TEXT_INSET = 16

CHIP_PAD_X = 5
CHIP_GAP = 6
CHIP_RADIUS = 3

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

#: Lane colours cycle; a deck with more branches than this reuses them, which is
#: fine because lane position, not colour, is what identifies a chain.
LANE_COLORS = (
    ACCENT_PRIMARY,
    (0xE0, 0x8C, 0x3A),
    (0x5B, 0xC0, 0x8C),
    (0xC8, 0x77, 0xD4),
    (0xD9, 0x6B, 0x6B),
)


class DeckGraphCanvas(wx.ScrolledWindow):
    """Paints a deck's version DAG and reports clicks on its nodes."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        on_select: Callable[[str], None] | None = None,
        on_context: Callable[[str, wx.Point], None] | None = None,
        empty_text: str = "",
    ) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetScrollRate(0, ROW_HEIGHT // 2)

        self._layout = GraphLayout()
        self._selected: str | None = None
        self._on_select = on_select
        self._on_context = on_context
        self._empty_text = empty_text

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_right_down)

    # ------------------------------------------------------------------ state ------------------------------------------------------------------
    def set_layout(self, layout: GraphLayout) -> None:
        self._layout = layout
        if self._selected is not None and layout.node_for(self._selected) is None:
            self._selected = None
        height = max(len(layout.nodes) * ROW_HEIGHT + 8, 1)
        self.SetVirtualSize((self.GetClientSize().GetWidth(), height))
        self.Refresh()

    @property
    def selected_sha(self) -> str | None:
        return self._selected

    def select(self, sha: str | None) -> None:
        self._selected = sha
        self.Refresh()

    # ------------------------------------------------------------------ hit testing ------------------------------------------------------------------
    def _sha_at(self, point: wx.Point) -> str | None:
        x, y = self.CalcUnscrolledPosition(point)
        row = y // ROW_HEIGHT
        if row < 0 or row >= len(self._layout.nodes):
            return None
        # The whole row is the target, not just the dot: a 10px circle is not a
        # click target anyone can hit reliably.
        node = next((n for n in self._layout.nodes if n.row == row), None)
        return node.sha if node is not None else None

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        sha = self._sha_at(event.GetPosition())
        if sha is None:
            return
        self._selected = sha
        self.Refresh()
        if self._on_select is not None:
            self._on_select(sha)

    def _on_right_down(self, event: wx.MouseEvent) -> None:
        sha = self._sha_at(event.GetPosition())
        if sha is None:
            return
        self._selected = sha
        self.Refresh()
        if self._on_select is not None:
            self._on_select(sha)
        if self._on_context is not None:
            self._on_context(sha, event.GetPosition())

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
        gc = wx.GraphicsContext.Create(dc)
        dc.SetBackground(wx.Brush(wx.Colour(*SURFACE_PANEL)))
        dc.Clear()

        if not self._layout.nodes:
            dc.SetFont(type_font("body"))
            dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
            dc.DrawText(self._empty_text, EMPTY_TEXT_INSET, EMPTY_TEXT_INSET)
            return

        # Three passes, in this order, because each would otherwise paint over
        # the one before: the selection fill is a full-width rectangle, so
        # drawing it after the edges erased the run of graph line crossing the
        # selected row -- the fork's own elbow, most of the time.
        self._draw_selection(dc)
        if gc is not None:
            self._draw_edges(gc)
        self._draw_nodes(dc)

    def _draw_selection(self, dc: wx.DC) -> None:
        node = next((n for n in self._layout.nodes if n.sha == self._selected), None)
        if node is None:
            return
        dc.SetPen(wx.Pen(wx.Colour(*ACCENT_PRIMARY), 1))
        dc.SetBrush(wx.Brush(wx.Colour(*SELECTION_FILL_ON_PANEL)))
        dc.DrawRectangle(0, node.row * ROW_HEIGHT, self.GetVirtualSize().GetWidth(), ROW_HEIGHT)

    def _draw_edges(self, gc: wx.GraphicsContext) -> None:
        for edge in self._layout.edges:
            colour = self._lane_colour(edge.child_lane)
            gc.SetPen(wx.Pen(colour, 2))
            x1, y1 = self._lane_x(edge.child_lane), self._row_y(edge.child_row)
            x2, y2 = self._lane_x(edge.parent_lane), self._row_y(edge.parent_row)
            path = gc.CreatePath()
            path.MoveToPoint(x1, y1)
            if edge.is_fork:
                # A fork bends once, close to the parent, so the straight part of
                # each chain stays vertical and reads as one line.
                bend_y = y2 - ROW_HEIGHT // 2
                path.AddLineToPoint(x1, bend_y)
                path.AddCurveToPoint(x1, y2, x2, bend_y, x2, y2)
            else:
                path.AddLineToPoint(x2, y2)
            gc.StrokePath(path)

    def _draw_nodes(self, dc: wx.DC) -> None:
        text_x = self._lane_x(max(self._layout.lane_count, 1)) + TEXT_GAP
        # Own-drawn text: wx font inheritance cannot reach a dc.SetFont() call,
        # so the sizes come from the type ladder explicitly (widgets.stylize).
        body_font = type_font("body")
        caption_font = type_font("caption")
        # Bold buys legibility in a chip a few characters wide, the way the mana
        # glyph runs do -- it is not marking a heading.
        chip_font = type_font("caption", bold=True)

        for node in self._layout.nodes:
            y = self._row_y(node.row)
            commit = node.graph_commit
            colour = self._lane_colour(node.lane)

            if commit.commit.is_head:
                # HEAD gets a ring rather than a different fill, so it stays
                # readable on top of the selection highlight.
                dc.SetPen(wx.Pen(wx.Colour(*ACCENT_TEXT), 2))
                dc.SetBrush(wx.Brush(wx.Colour(*SURFACE_PANEL), wx.BRUSHSTYLE_TRANSPARENT))
                dc.DrawCircle(self._lane_x(node.lane), y, HEAD_RING_RADIUS)

            dc.SetPen(wx.Pen(colour, 2))
            dc.SetBrush(wx.Brush(colour))
            dc.DrawCircle(self._lane_x(node.lane), y, NODE_RADIUS)

            label_x = text_x
            for branch in commit.commit.branches:
                label_x = self._draw_branch_chip(dc, chip_font, branch, label_x, node.row, colour)

            dc.SetFont(body_font)
            dc.SetTextForeground(wx.Colour(*TEXT_PRIMARY))
            dc.DrawText(commit.label, label_x, node.row * ROW_HEIGHT + LABEL_TOP)

            dc.SetFont(caption_font)
            dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
            # A baseline root's timestamp is a fixed constant, not a moment the
            # user's deck passed through, so showing it only ever reads as a
            # wrong date (it renders as 2019-12-31 in this timezone).
            if commit.commit.is_baseline:
                meta = commit.short_sha
            else:
                stamp = datetime.fromtimestamp(commit.commit.timestamp).strftime(TIMESTAMP_FORMAT)
                meta = f"{commit.short_sha}  ·  {stamp}"
            dc.DrawText(meta, text_x, node.row * ROW_HEIGHT + META_TOP)

    def _draw_branch_chip(
        self, dc: wx.DC, font: wx.Font, branch: str, x: int, row: int, colour: wx.Colour
    ) -> int:
        dc.SetFont(font)
        width, height = dc.GetTextExtent(branch)
        top = row * ROW_HEIGHT + LABEL_TOP
        dc.SetPen(wx.Pen(colour, 1))
        dc.SetBrush(wx.Brush(wx.Colour(*BORDER_SUBTLE)))
        dc.DrawRoundedRectangle(x, top, width + CHIP_PAD_X * 2, height + 2, CHIP_RADIUS)
        dc.SetTextForeground(colour)
        dc.DrawText(branch, x + CHIP_PAD_X, top + 1)
        return int(x + width + CHIP_PAD_X * 2 + CHIP_GAP)
