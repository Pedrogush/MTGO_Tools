"""Own-drawn chart surfaces, for everywhere a WebView is not available.

Why not wxHTML
--------------
The first attempt at a fallback emitted the same charts in the HTML subset
``wx.html.HtmlWindow`` renders. Screenshotted, it drew the labels and the values
and **no bars at all**: wxHTML ignores ``bgcolor`` on a ``<table>``, collapses a
table cell with no text in it, and ignores ``height`` on ``<td>``. So the one
thing the chart exists to show was the one thing that did not render — a silent
no-op of exactly the kind this codebase keeps getting caught by, and the reason
the fallback had to be verified on screen rather than reasoned about.

A ``wx.DC`` has none of those limits, so the fallback is painted directly. It is
fed the same :class:`~widgets.charts.bars.ChartBar` tuples as the WebView
rendering, so there is still one data path and one palette.
"""

from __future__ import annotations

import wx

from utils.constants.theme import (
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.constants.ui_layout import (
    CHART_BAR_MIN_WIDTH_PCT,
    CHART_BAR_TRACK_HEIGHT,
    CHART_LABEL_COLUMN_PCT,
    CHART_ROW_HEIGHT,
    CHART_VALUE_COLUMN_PCT,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from widgets.charts.bars import ChartBar
from widgets.stylize import type_font

#: ``(section title or "", bars)``. An empty title draws no heading, which is
#: what the single-chart metagame case wants.
ChartSection = tuple[str, list[ChartBar]]


class BarChartPanel(wx.ScrolledWindow):
    """Sorted horizontal bar charts, painted with a DC.

    Scrolls vertically, because the fallback has no way to compress four
    sections into a fixed height the way the CSS layout does.
    """

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(*SURFACE_BASE))
        self.SetScrollRate(0, SPACE_SM)
        self._title = ""
        self._subtitle = ""
        self._sections: list[ChartSection] = []
        self._empty_text = ""
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, lambda evt: (self.Refresh(), evt.Skip()))
        # Required by the buffered paint DCs below: without it wxMSW leaves
        # the window's backing store untouched, and a panel that draws
        # nothing (an empty sparkline) shows whatever was last blitted
        # there -- observed as a deck-list row appearing inside the
        # archetype summary.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda _evt: None)

    def set_sections(
        self,
        title: str,
        subtitle: str,
        sections: list[ChartSection],
        empty_text: str = "",
    ) -> None:
        self._title, self._subtitle = title, subtitle
        self._sections = sections
        self._empty_text = empty_text
        self._resize_virtual()
        self.Refresh()

    def content_height(self) -> int:
        """How tall the drawing is, so the scroll extent can match it."""
        height = SPACE_MD
        if self._title:
            height += CHART_ROW_HEIGHT
        if self._subtitle:
            height += CHART_ROW_HEIGHT
        drawn = False
        for section_title, bars in self._sections:
            if section_title:
                height += CHART_ROW_HEIGHT
            height += CHART_ROW_HEIGHT * len(bars) + SPACE_MD
            drawn = drawn or bool(bars)
        if not drawn and self._empty_text:
            height += CHART_ROW_HEIGHT
        return height + SPACE_MD

    def _resize_virtual(self) -> None:
        self.SetVirtualSize((-1, self.content_height()))

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        self.DoPrepareDC(dc)
        width = self.GetClientSize().width
        dc.SetBackground(wx.Brush(wx.Colour(*SURFACE_BASE)))
        dc.Clear()

        y = SPACE_MD
        if self._title:
            dc.SetFont(type_font("heading"))
            dc.SetTextForeground(wx.Colour(*TEXT_PRIMARY))
            dc.DrawText(self._title, SPACE_MD, y)
            y += CHART_ROW_HEIGHT
        if self._subtitle:
            dc.SetFont(type_font("caption"))
            dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
            dc.DrawText(self._subtitle, SPACE_MD, y)
            y += CHART_ROW_HEIGHT

        if not any(bars for _title, bars in self._sections):
            if self._empty_text:
                dc.SetFont(type_font("body"))
                dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
                dc.DrawText(self._empty_text, SPACE_MD, y)
            return

        for section_title, bars in self._sections:
            if section_title:
                dc.SetFont(type_font("caption"))
                dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
                dc.DrawText(section_title.upper(), SPACE_MD, y)
                y += CHART_ROW_HEIGHT
            y = self._draw_bars(dc, bars, y, width)
            y += SPACE_MD

    def _draw_bars(self, dc: wx.DC, bars: list[ChartBar], y: int, width: int) -> int:
        usable = max(0, width - SPACE_MD * 2)
        label_width = usable * CHART_LABEL_COLUMN_PCT // 100
        value_width = usable * CHART_VALUE_COLUMN_PCT // 100
        track_x = SPACE_MD + label_width + SPACE_SM
        track_width = max(0, usable - label_width - value_width - SPACE_SM * 2)

        dc.SetFont(type_font("body"))
        for bar in bars:
            centre = y + CHART_ROW_HEIGHT // 2
            dc.SetTextForeground(wx.Colour(*TEXT_PRIMARY))
            _draw_right(dc, bar.label, SPACE_MD, label_width, centre)

            track_y = centre - CHART_BAR_TRACK_HEIGHT // 2
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.SetBrush(wx.Brush(wx.Colour(*SURFACE_ALT)))
            dc.DrawRectangle(track_x, track_y, track_width, CHART_BAR_TRACK_HEIGHT)
            fill = max(CHART_BAR_MIN_WIDTH_PCT / 100.0, min(1.0, bar.fraction))
            dc.SetBrush(wx.Brush(wx.Colour(bar.colour)))
            dc.DrawRectangle(track_x, track_y, int(track_width * fill), CHART_BAR_TRACK_HEIGHT)

            _draw_right(dc, bar.value_text, track_x + track_width + SPACE_SM, value_width, centre)
            y += CHART_ROW_HEIGHT
        return y


def _draw_right(dc: wx.DC, text: str, x: int, width: int, centre_y: int) -> None:
    """Draw ``text`` right-aligned in ``[x, x + width)``, vertically centred."""
    if not text:
        return
    text_width, text_height = dc.GetTextExtent(text)
    dc.DrawText(text, x + max(0, width - text_width), centre_y - text_height // 2)


class SparkBarPanel(wx.Panel):
    """A total, a per-day bar strip, and a caption.

    Replaces ``9/6/0/7/10/4/0`` — seven slash-separated integers rendered at the
    second-highest visual weight on the panel, with no axis, units or legend, so
    the only thing a reader could take from them was "some numbers". The strip
    encodes the same seven values as length, which is readable at a glance, and
    the number that was actually worth reading big — the total — is the big one.
    """

    def __init__(self, parent: wx.Window, *, surface: tuple[int, int, int] = SURFACE_PANEL) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self._surface = surface
        self.SetBackgroundColour(wx.Colour(*surface))
        self._values: list[int] = []
        self._labels: list[str] = []
        self._total_text = ""
        self._caption = ""
        self._colour = wx.Colour(*TEXT_SECONDARY)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        # Required by the buffered paint DCs below: without it wxMSW leaves
        # the window's backing store untouched, and a panel that draws
        # nothing (an empty sparkline) shows whatever was last blitted
        # there -- observed as a deck-list row appearing inside the
        # archetype summary.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda _evt: None)

    def set_series(
        self,
        values: list[int],
        labels: list[str],
        total_text: str,
        caption: str,
        colour: tuple[int, int, int],
    ) -> None:
        self._values = list(values)
        self._labels = list(labels)
        self._total_text = total_text
        self._caption = caption
        self._colour = wx.Colour(*colour)
        self.Refresh()

    def clear(self) -> None:
        self.set_series([], [], "", "", TEXT_SECONDARY)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(*self._surface)))
        dc.Clear()
        if not self._values:
            return

        width, height = self.GetClientSize()
        dc.SetFont(type_font("title"))
        dc.SetTextForeground(wx.Colour(*TEXT_PRIMARY))
        total_w, total_h = dc.GetTextExtent(self._total_text)
        dc.DrawText(self._total_text, width - total_w - SPACE_SM, SPACE_XS)

        dc.SetFont(type_font("caption"))
        dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
        caption_w, caption_h = dc.GetTextExtent(self._caption)
        dc.DrawText(
            self._caption,
            width - total_w - caption_w - SPACE_SM * 2,
            SPACE_XS + total_h - caption_h,
        )

        label_h = caption_h if self._labels else 0
        strip_top = SPACE_XS + total_h + SPACE_XS
        strip_bottom = height - SPACE_XS - label_h
        strip_height = max(1, strip_bottom - strip_top)

        count = len(self._values)
        slot = max(1, (width - SPACE_SM * 2) // count)
        bar_width = max(1, slot - SPACE_XS)
        peak = max(self._values) or 1
        left = width - SPACE_SM - slot * count

        dc.SetPen(wx.TRANSPARENT_PEN)
        for index, value in enumerate(self._values):
            x = left + slot * index
            bar_height = max(1, round(strip_height * value / peak)) if value else 1
            dc.SetBrush(wx.Brush(self._colour if value else wx.Colour(*SURFACE_ALT)))
            dc.DrawRectangle(x, strip_bottom - bar_height, bar_width, bar_height)

        if self._labels:
            dc.SetTextForeground(wx.Colour(*TEXT_SECONDARY))
            for index, label in enumerate(self._labels[:count]):
                text_w, _h = dc.GetTextExtent(label)
                x = left + slot * index + (bar_width - text_w) // 2
                dc.DrawText(label, x, strip_bottom)
