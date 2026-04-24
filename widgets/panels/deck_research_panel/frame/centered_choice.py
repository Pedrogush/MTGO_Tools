"""Owner-drawn combo box that center-aligns text and fits its width to its widest item."""

from __future__ import annotations

import wx
import wx.adv


class _CenteredChoice(wx.adv.OwnerDrawnComboBox):
    """Read-only combo box that center-aligns text and fits its width to its widest item."""

    _BUTTON_AND_PADDING_PX = 36

    def __init__(self, parent: wx.Window, choices: list[str]) -> None:
        super().__init__(parent, choices=choices, style=wx.CB_READONLY)
        self._fit_to_widest_choice(choices)

    def _fit_to_widest_choice(self, choices: list[str]) -> None:
        if not choices:
            return
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        max_text_w = max(dc.GetTextExtent(c)[0] for c in choices)
        width = max_text_w + self._BUTTON_AND_PADDING_PX
        self.SetMinSize(wx.Size(width, -1))
        self.SetInitialSize(wx.Size(width, -1))

    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, item: int, flags: int) -> None:  # noqa: N802
        if item == wx.NOT_FOUND:
            return
        text = self.GetString(item)
        tw, th = dc.GetTextExtent(text)
        x = rect.x + (rect.width - tw) // 2
        y = rect.y + (rect.height - th) // 2
        dc.DrawText(text, x, y)
