from __future__ import annotations

import wx

from utils.constants import DARK_ACCENT, DARK_ALT, LIGHT_TEXT, SUBDUED_TEXT


class DeckResultsList(wx.VListBox):
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self._items: list[tuple[str, str]] = []
        self._line_two_color = wx.Colour(*SUBDUED_TEXT)
        self._selection_bg = wx.Colour(*DARK_ACCENT)
        self._selection_fg = wx.Colour(15, 17, 22)
        self.SetBackgroundColour(DARK_ALT)
        self.SetForegroundColour(LIGHT_TEXT)
        self.SetItemCount(0)

    def Append(self, text: str) -> None:
        line_one, line_two = self._split_lines(text)
        self._items.append((line_one, line_two))
        self.SetItemCount(len(self._items))
        self.Refresh()

    def Clear(self) -> None:
        self._items = []
        self.SetItemCount(0)
        self.Refresh()

    def _split_lines(self, text: str) -> tuple[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "", ""
        if len(lines) == 1:
            return lines[0], ""
        return lines[0], " ".join(lines[1:])

    def OnDrawBackground(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        if self.IsSelected(n):
            dc.SetBrush(wx.Brush(self._selection_bg))
            dc.SetPen(wx.Pen(self._selection_bg))
        else:
            dc.SetBrush(wx.Brush(self.GetBackgroundColour()))
            dc.SetPen(wx.Pen(self.GetBackgroundColour()))
        dc.DrawRectangle(rect)

    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        if n < 0 or n >= len(self._items):
            return
        line_one, line_two = self._items[n]
        padding = 6
        line_height = self.GetCharHeight()
        text_x = rect.x + padding
        text_y = rect.y + padding
        if self.IsSelected(n):
            dc.SetTextForeground(self._selection_fg)
        else:
            dc.SetTextForeground(self.GetForegroundColour())
        dc.DrawText(line_one, text_x, text_y)
        if line_two:
            if self.IsSelected(n):
                dc.SetTextForeground(self._selection_fg)
            else:
                dc.SetTextForeground(self._line_two_color)
            dc.DrawText(line_two, text_x, text_y + line_height + 2)

    def OnMeasureItem(self, n: int) -> int:
        line_height = self.GetCharHeight()
        padding = 6
        if 0 <= n < len(self._items) and self._items[n][1]:
            return line_height * 2 + padding * 2 + 2
        return line_height + padding * 2
