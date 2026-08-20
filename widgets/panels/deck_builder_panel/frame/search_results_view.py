"""Virtual ``wx.ListCtrl`` subclass that renders deck builder card search results."""

from __future__ import annotations

from typing import Any

import wx

from utils.constants import (
    BUILDER_MANA_CANVAS_WIDTH,
    BUILDER_MANA_ICON_GAP,
    BUILDER_MANA_ROW_HEIGHT,
    BUILDER_NAME_COL_MIN_WIDTH,
    BUILDER_NAME_COL_SLACK,
    DARK_ALT,
)
from widgets.mana_icon_factory import ManaIconFactory
from widgets.native_dark import has_horizontal_scrollbar

# Column 0 is the hidden 0-width dummy that absorbs the IMAGE_LIST_SMALL indent,
# column 2 the fixed-width Mana Cost column; column 1 is the one that flexes.
_NAME_COL = 1


class _SearchResultsView(wx.ListCtrl):
    """Virtual ListCtrl for efficiently displaying large card search results."""

    def __init__(self, parent: wx.Window, style: int, mana_icons: ManaIconFactory | None = None):
        super().__init__(parent, style=style | wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self._data: list[dict[str, Any]] = []
        self._mana_icons = mana_icons
        self._mana_img_index: dict[str, int] = {}
        self._mana_img_list: wx.ImageList | None = None
        self._hscrollbar_check_pending = False
        if mana_icons:
            self._mana_img_list = wx.ImageList(BUILDER_MANA_CANVAS_WIDTH, BUILDER_MANA_ROW_HEIGHT)
            self.AssignImageList(self._mana_img_list, wx.IMAGE_LIST_SMALL)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        self._fit_name_column()
        self._schedule_hscrollbar_check()

    def _fit_name_column(self, reserve_scrollbar: bool = False) -> None:
        """Give the Name column whatever the fixed columns leave, minus the slack.

        Three things this cannot do, all three measured on the running builder:

        * It cannot fit the columns to *exactly* the client width. wxMSW's native
          ``SysListView32`` raises its horizontal scrollbar the moment they sum to
          more than the client, so an exact fit is one client-width change away
          from a bar with nothing to scroll. The columns have to sum to strictly
          less; see ``BUILDER_NAME_COL_SLACK``.
        * It cannot assume the fixed columns are ``BUILDER_MANA_CANVAS_WIDTH``
          wide. Reading them back is what keeps this the arithmetic the scrollbar
          is actually decided by.
        * It cannot leave the correction until after the client width has already
          changed. comctl32 re-evaluates the bar when a column width changes, but
          a change made *from inside* its own scrollbar update -- which is where
          the ``EVT_SIZE`` for a bar appearing arrives -- does not get that
          re-evaluation, and the bar stays up. Hence ``reserve_scrollbar``: the
          caller shrinks first, so the overflow never happens at all.

        ``reserve_scrollbar`` takes the vertical scrollbar's width off the top,
        for the moment before a row count change that may add one. It is always
        safe -- the only cost is a transient underfit that the caller's follow-up
        fit corrects before anything repaints.
        """
        fixed = sum(
            self.GetColumnWidth(col) for col in range(self.GetColumnCount()) if col != _NAME_COL
        )
        available = self.GetClientSize().width - fixed - BUILDER_NAME_COL_SLACK
        if reserve_scrollbar:
            available -= wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X, self)
        self.SetColumnWidth(_NAME_COL, max(BUILDER_NAME_COL_MIN_WIDTH, available))

    def _schedule_hscrollbar_check(self) -> None:
        """Queue one deferred check that no spurious horizontal scrollbar is up."""
        if self._hscrollbar_check_pending:
            return
        self._hscrollbar_check_pending = True
        wx.CallAfter(self._drop_spurious_hscrollbar)

    def _drop_spurious_hscrollbar(self) -> None:
        """Take down a horizontal scrollbar wxMSW left up over columns that fit.

        comctl32 raises the bar from inside its own resize -- before ``EVT_SIZE``
        reaches ``_on_size`` and narrows the columns -- and a column width written
        from *inside* that update does not get re-evaluated, so the bar stays up
        with nothing to scroll. Measured on the running builder: the identical
        ``SetColumnWidth`` one message cycle later does take it down. Which is
        also why this writes a **different** width first: comctl32 re-evaluates on
        a width *change*, and re-writing the width it already has is not one.

        A bar over a Name column pinned at its minimum is not spurious -- the list
        is genuinely too narrow for its columns -- and is left alone.
        """
        self._hscrollbar_check_pending = False
        if not self:  # destroyed between the schedule and the call
            return
        if not has_horizontal_scrollbar(self):
            return
        width = self.GetColumnWidth(_NAME_COL)
        if width <= BUILDER_NAME_COL_MIN_WIDTH:
            return
        self.SetColumnWidth(_NAME_COL, width - 1)
        self._fit_name_column()

    def SetData(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        if self._mana_icons and self._mana_img_list is not None:
            self._update_mana_cache()
        if self.GetItemCount() > 0:
            self.EnsureVisible(0)
        # Shrink, then set the count, then fit. A row count that crosses the
        # point where the list needs a vertical scrollbar takes that bar's width
        # off the *client width*, with no EVT_SIZE to announce it -- the bar is
        # non-client area, so the window itself never resized. Columns fitted to
        # the old client width then overflow by exactly that much and wxMSW puts
        # up a horizontal scrollbar over content that fits. Shrinking first means
        # they are already narrow enough whichever way the count goes; the fit
        # afterwards gives back whatever the reservation turned out not to need.
        self._fit_name_column(reserve_scrollbar=True)
        self.SetItemCount(len(data))
        self._fit_name_column()
        self._schedule_hscrollbar_check()
        self.Refresh()

    def _update_mana_cache(self) -> None:
        """Add bitmaps for mana costs not yet in the persistent image list.

        The image list is created once and only grows — existing indices are
        stable so OnGetItemColumnImage lookups remain valid across searches.
        Only costs absent from the cache require bitmap rendering, making
        repeated searches (including empty-filter / browse-all) O(new_costs).
        """
        from widgets.mana_icon_factory import tokenize_mana_symbols

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
