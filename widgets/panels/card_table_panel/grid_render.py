"""Canvas cache + card-drawing primitives for :class:`DeckGridView`.

A thin view-collaborator mixin holding the cohesive cached canvas (the
full-content bitmap a scroll blits a sub-rect out of) and the per-card drawing
routines that paint art, quantity badges, selection accents and the drawn
+/−/× controls.

``_on_paint`` itself stays on the concrete view (it orchestrates these), but the
canvas build/patch and every ``_draw_*`` primitive live here. The
``_patch_card_on_canvas`` path is the one the async image pipeline calls when a
single card's art arrives, so it must keep redrawing only that card's cell.
"""

from __future__ import annotations

from typing import Any

import wx

from utils.constants import (
    DARK_ACCENT,
    DARK_ALT,
    DARK_PANEL,
    DECK_CARD_ACTION_BUTTON_FG,
    DECK_CARD_ACTIVE_BORDER_WIDTH,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_BASE_FONT_SIZE,
    DECK_CARD_CORNER_RADIUS,
)
from widgets.panels.card_table_panel.grid_layout import (
    _ACTION_BUTTON_RADIUS,
    _ACTION_GLYPHS,
    _CELL_HEIGHT,
    _MAX_CANVAS_PX,
)


class GridRenderMixin:
    """Cohesive cached canvas + per-card drawing for the grid view."""

    def _visible_card_indices(self) -> range:
        """Indices of the cards overlapping the current repaint region.

        Used only by the oversized-deck fallback. Falls back to every card when
        the update region is empty (e.g. a full ``Refresh``).
        """
        n = len(self._cards)
        if n == 0:
            return range(0)
        cols = max(1, self._cols)
        box = self.GetUpdateRegion().GetBox()
        if box.IsEmpty():
            top, bottom = 0, self.GetClientSize().GetHeight()
        else:
            top, bottom = box.GetTop(), box.GetBottom()
        # Region is in device coords; shift by the scroll origin to get logical y.
        view_y = self.GetViewStart()[1]
        first_row = max(0, (top + view_y) // _CELL_HEIGHT)
        last_row = (bottom + view_y) // _CELL_HEIGHT
        return range(first_row * cols, min(n, (last_row + 1) * cols))

    # ----- cohesive cached canvas -----
    def _invalidate_canvas(self) -> None:
        """Drop the cached full-content bitmap so the next paint rebuilds it."""
        self._canvas = None

    def _ensure_canvas(self) -> wx.Bitmap | None:
        """Return the full-content bitmap, building it if stale.

        Returns ``None`` when there is nothing to draw or the virtual size is
        too large to cache, signalling the caller to draw directly.
        """
        vsize = self.GetVirtualSize()
        vw, vh = vsize.GetWidth(), vsize.GetHeight()
        if not self._cards or vw <= 0 or vh <= 0:
            return None
        if vw > _MAX_CANVAS_PX or vh > _MAX_CANVAS_PX:
            return None
        if self._canvas is not None and self._canvas.GetSize() == vsize:
            return self._canvas
        canvas = wx.Bitmap(vw, vh)
        mem = wx.MemoryDC(canvas)
        mem.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        mem.Clear()
        for idx, card in enumerate(self._cards):
            self._draw_card_static(mem, self._card_rect(idx), card)
        mem.SelectObject(wx.NullBitmap)
        self._canvas = canvas
        return canvas

    def _patch_card_on_canvas(self, name: str) -> None:
        """Redraw just ``name``'s cell(s) into the canvas and invalidate them.

        Called when a card's art finishes loading so a single image swap repaints
        only that card rather than rebuilding or re-blitting the whole view.
        """
        if self._canvas is None:
            self.Refresh()
            return
        mem = wx.MemoryDC(self._canvas)
        mem.SetBackground(wx.Brush(wx.Colour(*DARK_PANEL)))
        view_x, view_y = self.GetViewStart()
        for idx, card in enumerate(self._cards):
            if card["name"].lower() != name.lower():
                continue
            rect = self._card_rect(idx)
            mem.SetBrush(wx.Brush(wx.Colour(*DARK_PANEL)))
            mem.SetPen(wx.TRANSPARENT_PEN)
            mem.DrawRectangle(rect)
            self._draw_card_static(mem, rect, card)
            self.RefreshRect(wx.Rect(rect.x - view_x, rect.y - view_y, rect.width, rect.height))
        mem.SelectObject(wx.NullBitmap)

    def _draw_overlays(self, dc: wx.DC) -> None:
        """Draw selection border, accent badge and +/−/× over the blitted cards."""
        sel = self._selected_names
        hov = self._hover_name
        if not sel and not hov:
            return
        for idx, card in enumerate(self._cards):
            name = card["name"]
            is_selected = name in sel
            is_hover = hov is not None and name.lower() == hov.lower()
            if not (is_selected or is_hover):
                continue
            rect = self._card_rect(idx)
            if is_selected:
                self._draw_qty(dc, rect, card, True)
                dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), DECK_CARD_ACTIVE_BORDER_WIDTH))
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)
            if self._shows_actions(name):
                self._draw_actions(dc, rect, name)

    def _draw_card_static(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any]) -> None:
        """Draw a card's scroll-invariant content (art + base quantity badge).

        This is what gets baked into the cached canvas. Selection accent, active
        border and the +/−/× controls are deliberately left out — they change
        without the card itself changing, so they are painted live as overlays.
        """
        name = card["name"]
        bitmap = self._image_cache.get(name)
        if bitmap is not None:
            x = rect.x + (rect.width - bitmap.GetWidth()) // 2
            y = rect.y + (rect.height - bitmap.GetHeight()) // 2
            # Opaque bitmaps (flattened onto DARK_PANEL) → fast BitBlt, no mask.
            dc.DrawBitmap(bitmap, x, y, False)
        else:
            dc.DrawBitmap(self._template_for(name), rect.x, rect.y, False)
        self._draw_qty(dc, rect, card, False)

    def _draw_card(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any]) -> None:
        """Draw a card in full (static content + live overlays).

        Used by the oversized-deck fallback path that bypasses the canvas.
        """
        name = card["name"]
        is_selected = name in self._selected_names
        self._draw_card_static(dc, rect, card)
        if is_selected:
            self._draw_qty(dc, rect, card, True)
            dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), DECK_CARD_ACTIVE_BORDER_WIDTH))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)

        if self._shows_actions(name):
            self._draw_actions(dc, rect, name)

    def _draw_qty(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any], is_selected: bool) -> None:
        qty_value = card["qty"]
        qty_for_check = int(qty_value) if isinstance(qty_value, float) else qty_value
        _, owned_rgb = self._owned_status(card["name"], qty_for_check)
        text = str(qty_value)
        dc.SetFont(
            wx.Font(
                DECK_CARD_BASE_FONT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        tw, th = dc.GetTextExtent(text)
        pad = DECK_CARD_BADGE_PADDING
        badge_bg = DARK_ACCENT if is_selected else DARK_ALT
        dc.SetBrush(wx.Brush(wx.Colour(*badge_bg)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect.x + pad, rect.y + pad, tw + pad * 2, th + pad)
        dc.SetTextForeground(wx.Colour(*owned_rgb))
        dc.DrawText(text, rect.x + pad * 2, rect.y + pad + (th + pad) // 2 - th // 2)

    def _draw_actions(self, dc: wx.DC, rect: wx.Rect, name: str) -> None:
        dc.SetFont(
            wx.Font(
                DECK_CARD_BASE_FONT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_BOLD,
            )
        )
        for idx, (button_rect, glyph) in enumerate(
            zip(self._action_button_rects(rect), _ACTION_GLYPHS)
        ):
            pressed = self._pressed == (name, idx)
            bg = tuple(max(0, c - 40) for c in DARK_ACCENT) if pressed else DARK_ACCENT
            dc.SetBrush(wx.Brush(wx.Colour(*bg)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRoundedRectangle(button_rect, _ACTION_BUTTON_RADIUS)
            dc.SetTextForeground(wx.Colour(*DECK_CARD_ACTION_BUTTON_FG))
            gw, gh = dc.GetTextExtent(glyph)
            dc.DrawText(
                glyph,
                button_rect.x + (button_rect.width - gw) // 2,
                button_rect.y + (button_rect.height - gh) // 2,
            )
