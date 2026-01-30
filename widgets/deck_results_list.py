from __future__ import annotations

import html

import wx
import wx.html

from utils.constants import DARK_ACCENT, DARK_ALT, LIGHT_TEXT, SUBDUED_TEXT


class DeckResultsList(wx.html.HtmlListBox):
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self._items: list[tuple[str, str]] = []
        self._line_one_color = self._rgb_hex(LIGHT_TEXT)
        self._line_two_color = self._rgb_hex(SUBDUED_TEXT)
        self._card_bg = self._rgb_hex(DARK_ALT)
        self._card_border = self._rgb_hex(DARK_ACCENT)
        self.SetBackgroundColour(DARK_ALT)
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

    def _rgb_hex(self, value: tuple[int, int, int]) -> str:
        return f"#{value[0]:02x}{value[1]:02x}{value[2]:02x}"

    def OnGetItem(self, n: int) -> str:
        if n < 0 or n >= len(self._items):
            return ""
        line_one, line_two = self._items[n]
        line_one = html.escape(line_one)
        line_two = html.escape(line_two)
        is_selected = self.IsSelected(n)
        card_bg = self._card_border if is_selected else self._card_bg
        text_one = "#0f1116" if is_selected else self._line_one_color
        text_two = "#0f1116" if is_selected else self._line_two_color
        return (
            "<table width='100%' cellspacing='6' cellpadding='6'>"
            "<tr>"
            f"<td align='center' bgcolor='{self._card_bg}'>"
            f"<table width='100%' cellpadding='6' cellspacing='0' bgcolor='{card_bg}'"
            f" border='1' bordercolor='{self._card_border}' style='border-radius:8px;'>"
            "<tr><td align='center'>"
            f"<font color='{text_one}'><b>{line_one}</b></font>"
            f"<br><font color='{text_two}'>{line_two}</font>"
            "</td></tr></table>"
            "</td>"
            "</tr>"
            "</table>"
        )
