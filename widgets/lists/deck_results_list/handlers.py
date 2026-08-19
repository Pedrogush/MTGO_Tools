"""Public state setters, drawing overrides, and drawing helpers for the deck results list."""

from __future__ import annotations

import wx

from utils.constants.theme import SPACE_SM
from widgets.stylize import type_font


class DeckResultsListHandlersMixin:
    """Public setters, drawing overrides, and sizing helpers for :class:`DeckResultsList`."""

    _ITEM_MARGIN: int
    _CARD_RADIUS: int
    _CARD_PADDING: int
    _ROW_GAP: int
    _row_height: int | None

    _items: list[tuple[bool, tuple]]
    _line_one_color: wx.Colour
    _line_two_color: wx.Colour
    _card_bg: wx.Colour
    _selection_bg: wx.Colour
    _selection_border: wx.Colour
    _selection_border_width: int

    # ------------------------------------------------------------------
    # Selection painting
    # ------------------------------------------------------------------

    def _paint_card(self, dc: wx.DC, card_rect: wx.Rect, is_selected: bool) -> None:
        """Fill and outline one row's card, selected or not.

        The whole of C9/G1 for this widget lives here: an unselected row is a
        plain panel-coloured card with no outline, a selected one is the app's
        selection token (16% accent tint + a 2px accent edge). Text colours do
        not change with selection any more — the old code inverted them to
        near-black because the selected row was a solid accent fill.
        """
        dc.SetBrush(wx.Brush(self._selection_bg if is_selected else self._card_bg))
        if is_selected:
            dc.SetPen(wx.Pen(self._selection_border, self._selection_border_width))
        else:
            dc.SetPen(wx.Pen(self._card_bg))
        dc.DrawRoundedRectangle(card_rect, self._CARD_RADIUS)

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

    def set_decks(self, rows: list[tuple[str, str, str, str, str, str]]) -> None:
        """Bulk-populate structured deck rows with a single layout pass.

        Each row is ``(emoji, player, archetype, event, result, date)``. Appending
        every row before a single :meth:`SetItemCount`/:meth:`Refresh` avoids the
        per-row scrollbar/layout recomputation that defeats VListBox virtualization.
        """
        self.Freeze()
        try:
            for emoji, player, archetype, event, result, date in rows:
                self._items.append((True, (emoji, player, archetype, event, result, date)))
            self.SetItemCount(len(self._items))
            self.Refresh()
        finally:
            self.Thaw()

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
        card_fg = self._line_one_color
        sub_fg = self._line_two_color

        card_rect = wx.Rect(rect)
        card_rect.Deflate(self._ITEM_MARGIN, self._ITEM_MARGIN)
        max_text_width = max(card_rect.width - (self._CARD_PADDING * 2), 0)

        self._paint_card(dc, card_rect, self.IsSelected(n))

        font = type_font("body", base=self.GetFont(), bold=True)
        dc.SetFont(font)

        emoji_w = 0
        if emoji_prefix:
            emoji_w, _ = dc.GetTextExtent(emoji_prefix)

        dc.SetTextForeground(card_fg)
        line_one_width, line_one_height = dc.GetTextExtent(line_one)
        total_line_one_width = emoji_w + line_one_width

        # H3. This used to shrink the font one point at a time until the string
        # fitted, which made type size a function of string length rather than
        # importance -- the strongest possible violation of "size encodes
        # hierarchy", and one that got *worse* at a 10pt base because the loop
        # had further to run. Fixed caption size, ellipsis when it overflows.
        line_two_font = type_font("caption", base=self.GetFont())
        if line_two:
            dc.SetFont(line_two_font)
            line_two = self._truncate_to_width(dc, line_two, max_text_width)
            line_two_width, line_two_height = dc.GetTextExtent(line_two)
        else:
            line_two_width = 0
            line_two_height = 0

        content_height = line_one_height + (line_two_height + 2 if line_two else 0)
        center_x = card_rect.x + (card_rect.width // 2)
        start_y = card_rect.y + (card_rect.height - content_height) // 2
        line_one_start_x = center_x - (total_line_one_width // 2)

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

        H2 -- the hierarchy is inverted from what shipped before. Each row used
        to read player+archetype (bold body), event (caption), **date (bold
        body)**, record (caption): the loudest string in the right column was
        the date, and the ``5-0`` / ``7-1`` that people actually scan a results
        list for was the smallest and dimmest thing on the row. The record is
        now the heading-level element and the date the caption beside the event,
        so the two columns read identity / result rather than identity / when.
        """
        emoji, player, archetype, event, result, date = data
        primary_fg = self._line_one_color
        secondary_fg = self._line_two_color

        card_rect = wx.Rect(rect)
        card_rect.Deflate(self._ITEM_MARGIN, self._ITEM_MARGIN)

        self._paint_card(dc, card_rect, self.IsSelected(n))

        inner_left = card_rect.x + self._CARD_PADDING
        inner_right = card_rect.x + card_rect.width - self._CARD_PADDING
        inner_top = card_rect.y + self._CARD_PADDING
        inner_w = card_rect.width - (self._CARD_PADDING * 2)

        title_font = type_font("body", base=self.GetFont(), bold=True)
        record_font = type_font("heading", base=self.GetFont())
        caption_font = type_font("caption", base=self.GetFont())

        dc.SetFont(record_font)
        record_w, record_h = dc.GetTextExtent(result or "0-0")
        dc.SetFont(title_font)
        _, title_h = dc.GetTextExtent("Ay")
        dc.SetFont(caption_font)
        _, caption_h = dc.GetTextExtent("Ay")
        date_w, _ = dc.GetTextExtent(date) if date else (0, 0)

        top_h = max(title_h, record_h)
        # The right column is sized to its own content rather than to a fixed
        # 30% of the row: a record is at most five glyphs and a date ten, so a
        # ratio split spent width the left column needed for the archetype name.
        right_col_w = max(record_w, date_w)
        left_col_w = max(0, inner_w - right_col_w - SPACE_SM)

        top_y = inner_top
        bottom_y = inner_top + top_h + self._ROW_GAP

        # --- left column: who, then which event -----------------------------
        dc.SetFont(title_font)
        dc.SetTextForeground(primary_fg)
        player_arch = f"{player}, {archetype}" if archetype else player
        player_text = f"{emoji} {player_arch}".strip() if emoji else player_arch
        dc.DrawText(
            self._truncate_to_width(dc, player_text, left_col_w),
            inner_left,
            top_y + max(0, (top_h - title_h) // 2),
        )

        dc.SetFont(caption_font)
        dc.SetTextForeground(secondary_fg)
        dc.DrawText(self._truncate_to_width(dc, event, left_col_w), inner_left, bottom_y)

        # --- right column: the result, then when ----------------------------
        if result:
            dc.SetFont(record_font)
            dc.SetTextForeground(primary_fg)
            width, _ = dc.GetTextExtent(result)
            dc.DrawText(result, inner_right - width, top_y + max(0, (top_h - record_h) // 2))

        if date:
            dc.SetFont(caption_font)
            dc.SetTextForeground(secondary_fg)
            dc.DrawText(date, inner_right - date_w, bottom_y)

    def _measure_row_height(self) -> int:
        """Row height in pixels, derived from the type scale.

        The tallest thing on a structured row is the heading-level record and
        the shortest the caption-level event/date, so all three fonts are
        measured: that is what keeps the row honest when the base font moves.
        Plain rows are body over caption and are never taller.
        """
        dc = wx.ClientDC(self)
        heights = []
        for level, bold in (("heading", None), ("body", True), ("caption", None)):
            dc.SetFont(type_font(level, base=self.GetFont(), bold=bold))
            heights.append(dc.GetTextExtent("Ay")[1])
        heading_h, body_h, caption_h = heights
        content_height = max(heading_h, body_h) + self._ROW_GAP + caption_h
        return content_height + (self._ITEM_MARGIN * 2) + (self._CARD_PADDING * 2)

    def OnMeasureItem(self, n: int) -> int:
        # Cached: wx.VListBox calls this once per item and the list runs to
        # thousands of rows, so measuring three fonts on a fresh ClientDC every
        # time would be a per-row DC allocation during scrolling.
        if self._row_height is None:
            self._row_height = self._measure_row_height()
        return self._row_height
