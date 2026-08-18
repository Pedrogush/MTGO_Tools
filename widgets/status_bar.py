"""An own-drawn replacement for ``wx.StatusBar``.

Why replace it at all (issue #962, §4.1 — the worst *measured* defect in the app):
``wx.StatusBar`` on wxMSW honours ``SetBackgroundColour`` and **silently ignores**
``SetForegroundColour``. The main frame set both, so the app's primary feedback
channel — "Loaded 976 decks…", "Deck ready…" — rendered as the system's near-black
text on ``#22272E``: a contrast ratio of **1.40:1**, effectively invisible.

Why own-drawn rather than a panel full of ``wx.StaticText``:
``_on_status_bar_click`` (issue #142) hit-tests the update slot with
``GetFieldRect(1).Contains(event.GetPosition())``. A child label sitting on top of
the strip would swallow the press and report a position in *its* coordinate space,
so the hit-test would silently stop matching. One window with an ``EVT_PAINT``
keeps every mouse position in the strip's own coordinates, which is exactly the
contract the existing handler was written against.

The API surface deliberately mirrors the part of ``wx.StatusBar`` the app uses —
``SetStatusText`` / ``GetStatusText`` / ``SetStatusWidths`` / ``GetFieldRect`` —
so ``properties.py``, ``handlers/app_frame.py`` and the automation server's
``get_status`` command all keep working untouched.
"""

from __future__ import annotations

import wx

from utils.constants.theme import (
    BORDER_SUBTLE,
    SPACE_SM,
    STATUS_BAR_BG,
    STATUS_BAR_FG,
)

#: Vertical padding above and below the text. With the 9pt base font this gives a
#: strip a little under wx's own 22px, and it tracks the font when phase 3 raises
#: the base size.
_VERTICAL_PADDING = 3


class ThemedStatusBar(wx.Panel):
    """A dark, own-drawn status strip with ``wx.StatusBar``'s field semantics."""

    def __init__(self, parent: wx.Window, field_count: int = 2) -> None:
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        if field_count < 1:
            raise ValueError(f"a status bar needs at least one field, got {field_count}")
        self._fields: list[str] = [""] * field_count
        # Same convention as wx.StatusBar.SetStatusWidths: a negative value is a
        # proportion of the leftover space, a positive one a fixed pixel width.
        self._widths: list[int] = [-1] * field_count
        self.SetBackgroundColour(wx.Colour(*STATUS_BAR_BG))
        self.SetForegroundColour(wx.Colour(*STATUS_BAR_FG))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.SetMinSize((-1, self._natural_height()))

    # ------------------------------------------------------------------ wx.StatusBar API
    def GetFieldsCount(self) -> int:  # noqa: N802 - mirrors wx
        return len(self._fields)

    def SetStatusText(self, text: str, number: int = 0) -> None:  # noqa: N802 - mirrors wx
        if not 0 <= number < len(self._fields):
            return
        if self._fields[number] == text:
            return
        self._fields[number] = text
        self.Refresh()

    def GetStatusText(self, number: int = 0) -> str:  # noqa: N802 - mirrors wx
        if not 0 <= number < len(self._fields):
            return ""
        return self._fields[number]

    def SetStatusWidths(self, widths: list[int]) -> None:  # noqa: N802 - mirrors wx
        if len(widths) != len(self._fields):
            raise ValueError(
                f"expected {len(self._fields)} widths for "
                f"{len(self._fields)} fields, got {len(widths)}"
            )
        self._widths = list(widths)
        self.Refresh()

    def GetFieldRect(self, number: int) -> wx.Rect:  # noqa: N802 - mirrors wx
        """The client rect of field ``number``, in this window's coordinates.

        Matching ``wx.StatusBar``'s coordinate space is the whole point: the
        update-note click handler tests ``GetFieldRect(1).Contains(...)`` against a
        position taken straight off the mouse event.
        """
        if not 0 <= number < len(self._fields):
            return wx.Rect()
        return self._field_rects()[number]

    # ------------------------------------------------------------------ internals
    def _natural_height(self) -> int:
        return self.GetCharHeight() + 2 * _VERTICAL_PADDING

    def _field_rects(self) -> list[wx.Rect]:
        """Resolve the wx width convention into pixel rects."""
        width, height = self.GetClientSize()
        fixed = sum(w for w in self._widths if w >= 0)
        proportions = [-w for w in self._widths if w < 0]
        total_proportion = sum(proportions) or 1
        leftover = max(0, width - fixed)

        rects: list[wx.Rect] = []
        x = 0
        for declared in self._widths:
            if declared >= 0:
                field_width = declared
            else:
                field_width = leftover * (-declared) // total_proportion
            rects.append(wx.Rect(x, 0, field_width, height))
            x += field_width
        # Hand any rounding remainder to the last field so the strip is fully covered.
        if rects:
            rects[-1].width = max(0, width - rects[-1].x)
        return rects

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        self._draw(wx.AutoBufferedPaintDC(self))

    def _draw(self, dc: wx.DC) -> None:
        """Render the strip onto ``dc``.

        Split out from the paint handler so the drawing can be exercised against a
        ``wx.MemoryDC`` in tests — ``AutoBufferedPaintDC`` is only valid inside a
        real ``WM_PAINT``, so a test that called the handler directly would be
        testing undefined behaviour rather than this code.
        """
        width, height = self.GetClientSize()
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()

        # A hairline along the top edge, the one piece of chrome wx's own status
        # bar drew for free: without it the strip merges into the panel above.
        dc.SetPen(wx.Pen(wx.Colour(*BORDER_SUBTLE)))
        dc.DrawLine(0, 0, width, 0)

        dc.SetFont(self.GetFont())
        dc.SetTextForeground(self.GetForegroundColour())
        text_y = max(0, (height - dc.GetCharHeight()) // 2)
        for rect, text in zip(self._field_rects(), self._fields, strict=True):
            if not text:
                continue
            dc.SetClippingRegion(rect)
            dc.DrawText(
                self._ellipsize(dc, text, rect.width - 2 * SPACE_SM),
                rect.x + SPACE_SM,
                text_y,
            )
            dc.DestroyClippingRegion()

    @staticmethod
    def _ellipsize(dc: wx.DC, text: str, available: int) -> str:
        """Clip ``text`` to ``available`` pixels with a trailing ellipsis.

        Hand-rolled rather than ``wx.Control.Ellipsize`` because the strip draws
        onto a DC and has no control to borrow the metrics from.
        """
        if available <= 0:
            return ""
        if dc.GetTextExtent(text)[0] <= available:
            return text
        ellipsis = "…"
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if dc.GetTextExtent(text[:mid] + ellipsis)[0] <= available:
                low = mid
            else:
                high = mid - 1
        return text[:low] + ellipsis if low else ""


__all__ = ["ThemedStatusBar"]
