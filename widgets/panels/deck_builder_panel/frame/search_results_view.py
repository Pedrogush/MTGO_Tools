"""Virtual ``wx.ListCtrl`` subclass that renders deck builder card search results."""

from __future__ import annotations

from typing import Any

import wx

from utils.constants import (
    BUILDER_MANA_CANVAS_WIDTH,
    BUILDER_MANA_ICON_GAP,
    BUILDER_MANA_ROW_HEIGHT,
    BUILDER_NAME_COL_MIN_WIDTH,
    DARK_ALT,
)
from utils.mana_icon_factory import ManaIconFactory


class _SearchResultsView(wx.ListCtrl):
    """Virtual ListCtrl for efficiently displaying large card search results."""

    def __init__(self, parent: wx.Window, style: int, mana_icons: ManaIconFactory | None = None):
        super().__init__(parent, style=style | wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self._data: list[dict[str, Any]] = []
        self._mana_icons = mana_icons
        self._mana_img_index: dict[str, int] = {}
        self._mana_img_list: wx.ImageList | None = None
        if mana_icons:
            self._mana_img_list = wx.ImageList(BUILDER_MANA_CANVAS_WIDTH, BUILDER_MANA_ROW_HEIGHT)
            self.AssignImageList(self._mana_img_list, wx.IMAGE_LIST_SMALL)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        self._fit_name_column()

    def _fit_name_column(self) -> None:
        name_w = max(
            BUILDER_NAME_COL_MIN_WIDTH, self.GetClientSize().width - BUILDER_MANA_CANVAS_WIDTH
        )
        self.SetColumnWidth(1, name_w)

    def SetData(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        if self._mana_icons and self._mana_img_list is not None:
            self._update_mana_cache()
        if self.GetItemCount() > 0:
            self.EnsureVisible(0)
        self.SetItemCount(len(data))
        self.Refresh()

    def _update_mana_cache(self) -> None:
        """Add bitmaps for mana costs not yet in the persistent image list.

        The image list is created once and only grows — existing indices are
        stable so OnGetItemColumnImage lookups remain valid across searches.
        Only costs absent from the cache require bitmap rendering, making
        repeated searches (including empty-filter / browse-all) O(new_costs).
        """
        from utils.mana_icon_factory import tokenize_mana_symbols

        assert self._mana_icons is not None
        assert self._mana_img_list is not None
        unique_costs = {card.get("mana_cost", "") for card in self._data if card.get("mana_cost")}
        new_costs = unique_costs - set(self._mana_img_index)
        if not new_costs:
            return

        for cost in new_costs:
            tokens = tokenize_mana_symbols(cost)
            if not tokens:
                continue

            # Collect render-scale bitmaps (before the factory's own downscale).
            # Using hires gives a single downscale from ~78px to the final size
            # instead of two chained downscales (78→26, then 26→final).
            raws: list[wx.Bitmap] = []
            for token in tokens:
                raw = self._mana_icons.bitmap_for_symbol_hires(token)
                if raw and raw.IsOk():
                    raws.append(raw)
            if not raws:
                continue

            # Compute each symbol's width if scaled to full row height.
            widths_at_full_h = [
                (
                    max(1, int(b.GetWidth() * BUILDER_MANA_ROW_HEIGHT / b.GetHeight()))
                    if b.GetHeight() > 0
                    else 1
                )
                for b in raws
            ]
            total_at_full_h = sum(widths_at_full_h) + max(0, len(raws) - 1) * BUILDER_MANA_ICON_GAP

            # Single squeeze factor: 1.0 when icons fit, <1.0 when they overflow.
            squeeze = (
                min(1.0, BUILDER_MANA_CANVAS_WIDTH / total_at_full_h)
                if total_at_full_h > 0
                else 1.0
            )
            final_h = max(1, int(BUILDER_MANA_ROW_HEIGHT * squeeze))

            # Single-pass scale: raw → final size.
            scaled_icons: list[wx.Bitmap] = []
            for bmp, w_full in zip(raws, widths_at_full_h):
                final_w = max(1, int(w_full * squeeze))
                scaled_icons.append(
                    wx.Bitmap(bmp.ConvertToImage().Scale(final_w, final_h, wx.IMAGE_QUALITY_HIGH))
                )

            total_w = (
                sum(b.GetWidth() for b in scaled_icons)
                + max(0, len(scaled_icons) - 1) * BUILDER_MANA_ICON_GAP
            )

            # DARK_ALT canvas — gaps between icons match the list background.
            canvas = wx.Bitmap(BUILDER_MANA_CANVAS_WIDTH, BUILDER_MANA_ROW_HEIGHT)
            dc = wx.MemoryDC(canvas)
            dc.SetBackground(wx.Brush(DARK_ALT))
            dc.Clear()

            # Right-justify: start at (canvas_width - total_icon_width).
            x = BUILDER_MANA_CANVAS_WIDTH - total_w
            for idx, icon_bmp in enumerate(scaled_icons):
                y = (BUILDER_MANA_ROW_HEIGHT - icon_bmp.GetHeight()) // 2
                dc.DrawBitmap(icon_bmp, x, max(0, y), False)
                x += icon_bmp.GetWidth()
                if idx < len(scaled_icons) - 1:
                    x += BUILDER_MANA_ICON_GAP

            dc.SelectObject(wx.NullBitmap)
            self._mana_img_index[cost] = self._mana_img_list.Add(canvas)

    def OnGetItemText(self, item: int, column: int) -> str:
        """Return text for the given item and column.

        Column layout:
          0 - hidden dummy (absorbs the IMAGE_LIST_SMALL indent, zero width)
          1 - card Name
          2 - Mana Cost text (suppressed when an icon image is shown)
        """
        if item < 0 or item >= len(self._data):
            return ""

        card = self._data[item]
        if column == 1:
            return card.get("name", "Unknown")
        elif column == 2:
            # Mana cost column: suppress text when an icon image is shown.
            cost = card.get("mana_cost", "")
            if self._mana_icons and cost in self._mana_img_index:
                return ""
            return cost if cost else "—"
        return ""

    def OnGetItemImage(self, item: int) -> int:
        return -1

    def OnGetItemColumnImage(self, item: int, col: int) -> int:
        if col != 2 or not self._mana_icons or item < 0 or item >= len(self._data):
            return -1
        cost = self._data[item].get("mana_cost", "")
        return self._mana_img_index.get(cost, -1)

    def GetItemText(self, row: int, col: int = 0) -> str:
        """Legacy method for test compatibility.

        Callers use logical columns (0=Name, 1=Mana Cost); shift by 1 internally
        to account for the hidden dummy column 0.
        """
        return self.OnGetItemText(row, col + 1)
