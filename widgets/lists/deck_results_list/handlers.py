"""Public state setters, drawing overrides, and drawing helpers for the deck results list."""

from __future__ import annotations

import wx


class DeckResultsListHandlersMixin:
    """Public setters, drawing overrides, and sizing helpers for :class:`DeckResultsList`."""

    _ITEM_MARGIN: int
    _CARD_RADIUS: int
    _CARD_PADDING: int
    _MIN_FONT_SIZE: int
    _RIGHT_COL_RATIO: float

    _items: list[tuple[bool, tuple]]
    _line_one_color: wx.Colour
    _line_two_color: wx.Colour
    _card_bg: wx.Colour
    _card_border: wx.Colour
    _selection_fg: wx.Colour

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def Append(self, text: str) -> None:
        line_one, line_two = self._split_lines(text)
        emoji_prefix, line_one_text = self._split_emoji_prefix(line_one)
        self._items.append((False, (emoji_prefix, line_one_text, line_two)))
        self.SetItemCount(len(self._items))
        self.Refresh()

    def AppendDeck(
        self,
        player: str,
        event: str,
        result: str,
        date: str,
        emoji: str = "",
        archetype: str = "",
    ) -> None:
        self._items.append((True, (emoji, player, archetype, event, result, date)))
        self.SetItemCount(len(self._items))
        self.Refresh()

    def Clear(self) -> None:
        self._items = []
        self.SetItemCount(0)
        self.Refresh()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _truncate_to_width(self, dc: wx.DC, text: str, max_width: int) -> str:
        if not text:
            return text
        while text:
            w, _ = dc.GetTextExtent(text)
            if w <= max_width:
                return text
            words = text.rsplit(" ", 1)
            if len(words) == 1:
                # truncate char by char
                if text.endswith("..."):
                    text = text[:-4] + "..." if len(text) > 4 else "..."
                else:
                    text = text[:-1] + "..."
                return text
            text = f"{words[0].rstrip()}..."
        return text

    def _fit_font_to_width(self, dc: wx.DC, text: str, font: wx.Font, max_width: int) -> wx.Font:
        sized = wx.Font(font)
        for pt in range(font.GetPointSize(), self._MIN_FONT_SIZE - 1, -1):
            sized.SetPointSize(pt)
            dc.SetFont(sized)
            w, _ = dc.GetTextExtent(text)
            if w <= max_width:
                return sized
        return sized

    # ------------------------------------------------------------------
    # VListBox drawing overrides
    # ------------------------------------------------------------------

    def OnDrawBackground(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        dc.SetBrush(wx.Brush(self.GetBackgroundColour()))
        dc.SetPen(wx.Pen(self.GetBackgroundColour()))
        dc.DrawRectangle(rect)

    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, n: int) -> None:
        if n < 0 or n >= len(self._items):
            return
        is_structured, data = self._items[n]
        if is_structured:
            self._draw_deck_item(dc, rect, n, data)
        else:
            self._draw_plain_item(dc, rect, n, data)

    def _draw_plain_item(self, dc: wx.DC, rect: wx.Rect, n: int, data: tuple) -> None:
        emoji_prefix, line_one, line_two = data
        is_selected = self.IsSelected(n)
        card_bg = self._card_border if is_selected else self._card_bg
        card_fg = self._selection_fg if is_selected else self._line_one_color
        sub_fg = self._selection_fg if is_selected else self._line_two_color

        card_rect = wx.Rect(rect)
        card_rect.Deflate(self._ITEM_MARGIN, self._ITEM_MARGIN)
        max_text_width = max(card_rect.width - (self._CARD_PADDING * 2), 0)

        dc.SetBrush(wx.Brush(card_bg))
        dc.SetPen(wx.Pen(self._card_border))
        dc.DrawRoundedRectangle(card_rect, self._CARD_RADIUS)

        font = self.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)

        emoji_w = 0
        if emoji_prefix:
            emoji_w, _ = dc.GetTextExtent(emoji_prefix)

        dc.SetTextForeground(card_fg)
        line_one_width, line_one_height = dc.GetTextExtent(line_one)
        total_line_one_width = emoji_w + line_one_width

        base_font = self.GetFont()
        base_font.SetWeight(wx.FONTWEIGHT_NORMAL)
        if line_two:
            line_two_font = self._fit_font_to_width(dc, line_two, base_font, max_text_width)
            dc.SetFont(line_two_font)
            line_two_width, line_two_height = dc.GetTextExtent(line_two)
        else:
            line_two_width = 0
            line_two_height = 0

        content_height = line_one_height + (line_two_height + 2 if line_two else 0)
        center_x = card_rect.x + (card_rect.width // 2)
        start_y = card_rect.y + (card_rect.height - content_height) // 2
        line_one_start_x = center_x - (total_line_one_width // 2)

        font.SetWeight(wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)

        if emoji_prefix:
            dc.SetTextForeground(self._line_one_color)
            dc.DrawText(emoji_prefix, line_one_start_x, start_y)

        dc.SetTextForeground(card_fg)
        dc.DrawText(line_one, line_one_start_x + emoji_w, start_y)

        if line_two:
            dc.SetFont(line_two_font)
            dc.SetTextForeground(sub_fg)
            dc.DrawText(line_two, center_x - (line_two_width // 2), start_y + line_one_height + 2)

    def _draw_deck_item(self, dc: wx.DC, rect: wx.Rect, n: int, data: tuple) -> None:
        """Left/right split card layout for structured deck entries.

        Left column:  emoji + player name (bold), event (small/subdued below)
        Right column: date (bold, right-aligned), result (small/subdued, right-aligned)
        """
        emoji, player, archetype, event, result, date = data
        is_selected = self.IsSelected(n)
        card_bg = self._card_border if is_selected else self._card_bg
        primary_fg = self._selection_fg if is_selected else self._line_one_color
        secondary_fg = self._selection_fg if is_selected else self._line_two_color

        card_rect = wx.Rect(rect)
        card_rect.Deflate(self._ITEM_MARGIN, self._ITEM_MARGIN)

        dc.SetBrush(wx.Brush(card_bg))
        dc.SetPen(wx.Pen(self._card_border))
        dc.DrawRoundedRectangle(card_rect, self._CARD_RADIUS)

        # Column boundaries — split the inner content area 70/30
        inner_w = card_rect.width - (self._CARD_PADDING * 2)
        right_col_w = int(inner_w * self._RIGHT_COL_RATIO)
        left_col_w = inner_w - right_col_w - 4

        inner_left = card_rect.x + self._CARD_PADDING
        inner_right = card_rect.x + card_rect.width - self._CARD_PADDING
        inner_top = card_rect.y + self._CARD_PADDING
        inner_h = card_rect.height - (self._CARD_PADDING * 2)
        row_h = inner_h // 2

        # --- Bold font for primary rows ---
        bold_font = self.GetFont()
        bold_font.SetWeight(wx.FONTWEIGHT_BOLD)
        dc.SetFont(bold_font)
        _, line_h = dc.GetTextExtent("Ay")

        top_y = inner_top + max(0, (row_h - line_h) // 2)

        # --- Small font for secondary rows ---
        small_font = self.GetFont()
        small_font.SetWeight(wx.FONTWEIGHT_NORMAL)
        for pt in range(small_font.GetPointSize() - 1, self._MIN_FONT_SIZE - 1, -1):
            small_font.SetPointSize(pt)
            dc.SetFont(small_font)
            _, sh = dc.GetTextExtent("Ay")
            if sh <= row_h:
                break
        dc.SetFont(small_font)
        _, small_h = dc.GetTextExtent("Ay")
        bottom_y = inner_top + row_h + max(0, (row_h - small_h) // 2)

        # --- Draw left column ---
        # Top: emoji + player name
        dc.SetFont(bold_font)
        dc.SetTextForeground(primary_fg)
        player_arch = f"{player}, {archetype}" if archetype else player
        player_text = f"{emoji} {player_arch}".strip() if emoji else player_arch
        player_truncated = self._truncate_to_width(dc, player_text, left_col_w)
        dc.DrawText(player_truncated, inner_left, top_y)

        # Bottom: event name
        dc.SetFont(small_font)
        dc.SetTextForeground(secondary_fg)
        event_truncated = self._truncate_to_width(dc, event, left_col_w)
        dc.DrawText(event_truncated, inner_left, bottom_y)

        # --- Draw right column ---
        # Top: date (right-aligned)
        dc.SetFont(bold_font)
        dc.SetTextForeground(primary_fg)
        if date:
            date_w, _ = dc.GetTextExtent(date)
            dc.DrawText(date, inner_right - date_w, top_y)

        # Bottom: result (right-aligned)
        dc.SetFont(small_font)
        dc.SetTextForeground(secondary_fg)
        if result:
            result_w, _ = dc.GetTextExtent(result)
            dc.DrawText(result, inner_right - result_w, bottom_y)

    def OnMeasureItem(self, n: int) -> int:
        line_height = self.GetCharHeight()
        # Both plain two-line items and structured deck items use two rows
        content_height = line_height * 2 + 2
        return content_height + (self._ITEM_MARGIN * 2) + (self._CARD_PADDING * 2)
