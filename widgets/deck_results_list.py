from __future__ import annotations

import wx

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT


class DeckResultsList(wx.VListBox):
    _ITEM_MARGIN = 6
    _CARD_RADIUS = 8
    _CARD_PADDING = 8
    _MIN_FONT_SIZE = 8

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self._items: list[tuple[str, str]] = []
        self._line_one_color = wx.Colour(*LIGHT_TEXT)
        self._line_two_color = wx.Colour(*SUBDUED_TEXT)
        self._card_bg = wx.Colour(*DARK_PANEL)
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

    def _fit_font_to_width(self, dc: wx.DC, text: str, font: wx.Font, max_width: int) -> wx.Font:
        sized_font = wx.Font(font)
        for point_size in range(font.GetPointSize(), self._MIN_FONT_SIZE - 1, -1):
            sized_font.SetPointSize(point_size)
            dc.SetFont(sized_font)
            text_width, _ = dc.GetTextExtent(text)
            if text_width <= max_width:
                return sized_font
        return sized_font

    def _truncate_line_two(self, text: str) -> str:
        if "-" not in text:
            return text
        prefix = text.split("-", 1)[0].rstrip()
        return f"{prefix}..." if prefix else "..."

    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        if n < 0 or n >= len(self._items):
            return
        line_one, line_two = self._items[n]
        if line_two:
            line_two = self._truncate_line_two(line_two)
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

        base_font = self.GetFont()
        base_font.SetWeight(wx.FONTWEIGHT_NORMAL)
        max_text_width = max(card_rect.width - (self._CARD_PADDING * 2), 0)
        if line_two:
            line_two_font = self._fit_font_to_width(dc, line_two, base_font, max_text_width)
            dc.SetFont(line_two_font)
            dc.SetTextForeground(sub_fg)
            line_two_width, line_two_height = dc.GetTextExtent(line_two)
        else:
            line_two_font = base_font
            line_two_width = 0
            line_two_height = 0

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
            dc.SetFont(line_two_font)
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
