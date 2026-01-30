from __future__ import annotations

import wx

from utils.constants import DARK_ACCENT, DARK_ALT, LIGHT_TEXT, SUBDUED_TEXT


class DeckResultsList(wx.VListBox):
    _ITEM_MARGIN = 6
    _CARD_RADIUS = 8
    _CARD_PADDING = 8

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self._items: list[tuple[str, str]] = []
        self._line_one_color = wx.Colour(*LIGHT_TEXT)
        self._line_two_color = wx.Colour(*SUBDUED_TEXT)
        self._card_bg = wx.Colour(*DARK_ALT)
        self._card_border = wx.Colour(*DARK_ACCENT)
        self._selection_fg = wx.Colour(15, 17, 22)
        self.SetBackgroundColour(DARK_ALT)
        self.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
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

    def GetCount(self) -> int:
        return len(self._items)

    def _split_lines(self, text: str) -> tuple[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "", ""
        if len(lines) == 1:
            return lines[0], ""
        return lines[0], " ".join(lines[1:])

    def OnDrawBackground(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        dc.SetBrush(wx.Brush(self.GetBackgroundColour()))
        dc.SetPen(wx.Pen(self.GetBackgroundColour()))
        dc.DrawRectangle(rect)

    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        if n < 0 or n >= len(self._items):
            return
        line_one, line_two = self._items[n]
        is_selected = self.IsSelected(n)
        card_bg = self._card_border if is_selected else self._card_bg
        card_fg = self._selection_fg if is_selected else self._line_one_color
        sub_fg = self._selection_fg if is_selected else self._line_two_color

        card_rect = wx.Rect(rect)
        card_rect.Deflate(self._ITEM_MARGIN, self._ITEM_MARGIN)
        dc.SetBrush(wx.Brush(card_bg))
        dc.SetPen(wx.Pen(self._card_border))
        dc.DrawRoundedRectangle(card_rect, self._CARD_RADIUS)

        font = self.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        dc.SetTextForeground(card_fg)
        line_one_width, line_one_height = dc.GetTextExtent(line_one)

        font.SetWeight(wx.FONTWEIGHT_NORMAL)
        dc.SetFont(font)
        dc.SetTextForeground(sub_fg)
        line_two_width, line_two_height = dc.GetTextExtent(line_two)

        content_height = line_one_height
        if line_two:
            content_height += line_two_height + 2

        center_x = card_rect.x + (card_rect.width // 2)
        start_y = card_rect.y + (card_rect.height - content_height) // 2

        dc.SetTextForeground(card_fg)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        dc.DrawText(line_one, center_x - (line_one_width // 2), start_y)

        if line_two:
            font.SetWeight(wx.FONTWEIGHT_NORMAL)
            dc.SetFont(font)
            dc.SetTextForeground(sub_fg)
            dc.DrawText(
                line_two,
                center_x - (line_two_width // 2),
                start_y + line_one_height + 2,
            )

    def OnMeasureItem(self, n: int) -> int:
        line_height = self.GetCharHeight()
        content_height = line_height
        if 0 <= n < len(self._items) and self._items[n][1]:
            content_height = line_height * 2 + 2
        return content_height + (self._ITEM_MARGIN * 2) + (self._CARD_PADDING * 2)
