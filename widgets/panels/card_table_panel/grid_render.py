"""Canvas cache + card-drawing primitives for :class:`DeckGridView`.

A thin view-collaborator mixin holding the cohesive cached canvas (the
full-content bitmap a scroll blits a sub-rect out of) and the per-card drawing
routines that paint art, the copy-count strip, selection accents and the drawn
+/−/× controls.

``_on_paint`` itself stays on the concrete view (it orchestrates these), but the
canvas build/patch and every ``_draw_*`` primitive live here. The
``_patch_card_on_canvas`` path is the one the async image pipeline calls when a
single card's art arrives, so it must keep redrawing only that card's cell.
"""

from __future__ import annotations

from typing import Any

import wx
from PIL import Image as PilImage
from PIL import ImageDraw

from utils.constants import (
    DARK_ALT,
    DARK_PANEL,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_BADGE_RADIUS,
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_COUNT_STRIP_PADDING,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
    SELECTION_BORDER,
    SELECTION_BORDER_WIDTH,
    SURFACE_RAISED,
    TEXT_PRIMARY,
)
from widgets.panels.card_table_panel.grid_layout import (
    _ACTION_BUTTON_RADIUS,
    _ACTION_GLYPHS,
    _CELL_HEIGHT,
    _MAX_CANVAS_PX,
    badge_rect,
    count_dot_layout,
    count_fits_in_dots,
)
from widgets.stylize import type_font

#: Cached dot columns, keyed by ``(count, backing_rgb, dot_rgb)``. The column is
#: identical on every card that shares those three, so a 60-card deck rasterises
#: at most a handful of distinct bitmaps -- see :func:`_count_dots_bitmap`.
_DOTS_CACHE: dict[tuple[int, tuple[int, int, int], tuple[int, int, int]], wx.Bitmap] = {}
#: Bounded like the edge fade's cache: the key space is small (counts x two
#: backings x the four owned-status hues), so this only trips if something
#: unexpected starts varying the colours.
_DOTS_CACHE_MAX = 64
#: Supersample factor the dots are rasterised at before the area-average
#: downscale that anti-aliases them.
_DOTS_SUPERSAMPLE = 4


def _count_dots_bitmap(
    count: int, backing_rgb: tuple[int, int, int], dot_rgb: tuple[int, int, int]
) -> wx.Bitmap:
    """Build (and cache) the **opaque** dot column for a ``count``-copy strip.

    Opaque, and only the column rather than the whole strip, for the reason the
    card art next to it is flattened onto ``DARK_PANEL``: an alpha blit into the
    canvas bitmap does not take wxMSW's ``BitBlt`` path. Measured on a 60-card
    zone, one small alpha ``DrawBitmap`` per card costs ~5ms *each* (~330ms), and
    a ``wx.GraphicsContext`` per card costs ~1.2ms each just to create the
    context; the opaque blit used here is ~0.04ms. The strip's rounded outline is
    drawn by the DC around it, exactly as the numeral chip's was.

    The column is inset by :data:`DECK_CARD_COUNT_STRIP_PADDING` on all sides,
    which keeps its square corners inside the pill's round caps, so painting one
    over the other leaves the outline intact.

    PIL rasterises the dots at :data:`_DOTS_SUPERSAMPLE` scale and the box
    downscale averages that down to coverage-accurate anti-aliasing --
    ``wx.DC.DrawCircle`` has none on wxMSW, and an 8px aliased circle reads as a
    lumpy square.
    """
    key = (count, backing_rgb, dot_rgb)
    cached = _DOTS_CACHE.get(key)
    if cached is not None:
        return cached
    strip, dots = count_dot_layout(wx.Rect(0, 0, DECK_CARD_WIDTH, DECK_CARD_HEIGHT), count)
    pad = DECK_CARD_COUNT_STRIP_PADDING
    width, height = strip.width - pad * 2, strip.height - pad * 2
    scale = _DOTS_SUPERSAMPLE
    column = PilImage.new("RGB", (width * scale, height * scale), backing_rgb)
    draw = ImageDraw.Draw(column)
    for dot in dots:
        x0 = (dot.x - strip.x - pad) * scale
        y0 = (dot.y - strip.y - pad) * scale
        draw.ellipse(
            [x0, y0, x0 + dot.width * scale - 1, y0 + dot.height * scale - 1], fill=dot_rgb
        )
    image = wx.Image(width, height)
    image.SetData(column.resize((width, height), PilImage.BOX).tobytes())
    bitmap = image.ConvertToBitmap()
    if len(_DOTS_CACHE) >= _DOTS_CACHE_MAX:
        _DOTS_CACHE.clear()
    _DOTS_CACHE[key] = bitmap
    return bitmap


class GridRenderMixin:
    """Cohesive cached canvas + per-card drawing for the grid view."""

    def _visible_card_indices(self, whole_client: bool = False) -> range:
        """Indices of the cards overlapping the current repaint region.

        Used only by the oversized-deck fallback. Falls back to every card when
        the update region is empty (e.g. a full ``Refresh``), or when
        ``whole_client`` says :func:`edge_fade.begin_viewport_paint` widened
        this paint's clip past what ``GetUpdateRegion`` still remembers (#983).
        """
        n = len(self._cards)
        if n == 0:
            return range(0)
        cols = max(1, self._cols)
        box = self.GetUpdateRegion().GetBox()
        if whole_client or box.IsEmpty():
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
                dc.SetPen(wx.Pen(wx.Colour(*SELECTION_BORDER), SELECTION_BORDER_WIDTH))
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
            dc.SetPen(wx.Pen(wx.Colour(*SELECTION_BORDER), SELECTION_BORDER_WIDTH))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)

        if self._shows_actions(name):
            self._draw_actions(dc, rect, name)

    def _draw_qty(self, dc: wx.DC, rect: wx.Rect, card: dict[str, Any], is_selected: bool) -> None:
        """Draw the card's copy count on its left edge (issue #987).

        One filled dot per copy, stacked in a thin strip down that edge; past
        :data:`DECK_CARD_COUNT_MAX_DOTS` copies the strip degrades to the numeral
        chip, which is the only thing that stays readable for a 20-of.
        """
        qty_value = card["qty"]
        qty_for_check = int(qty_value) if isinstance(qty_value, float) else qty_value
        _, owned_rgb = self._owned_status(card["name"], qty_for_check)
        # The selected backing used to be a solid accent block on top of the art.
        # Selection is already carried by the 2px accent edge around the whole
        # card, so it only has to lift off the unselected one.
        badge_bg = SURFACE_RAISED if is_selected else DARK_ALT
        if count_fits_in_dots(qty_for_check):
            self._draw_qty_dots(dc, rect, int(qty_for_check), badge_bg, owned_rgb)
            return
        text = str(qty_value)
        dc.SetFont(type_font("body"))
        tw, th = dc.GetTextExtent(text)
        pad = DECK_CARD_BADGE_PADDING
        dc.SetBrush(wx.Brush(wx.Colour(*badge_bg)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        bx, by, bw, bh = badge_rect(rect, tw, th)
        dc.DrawRoundedRectangle(bx, by, bw, bh, DECK_CARD_BADGE_RADIUS)
        dc.SetTextForeground(wx.Colour(*owned_rgb))
        dc.DrawText(text, bx + pad, by + (bh - th) // 2)

    @staticmethod
    def _draw_qty_dots(
        dc: wx.DC,
        rect: wx.Rect,
        count: int,
        backing_rgb: tuple[int, int, int],
        dot_rgb: tuple[int, int, int],
    ) -> None:
        """Blit ``count`` filled dots into the card's left-edge strip.

                The strip keeps the numeral chip's opaque backing: the dots sit over card
                *art*, which is any colour at all, and the owned-status hue has to stay
                readable against it -- a bare dot on a light art box would not.

        The rounded backing is a DC rounded-rectangle (as the numeral chip's was)
                with the anti-aliased dot column blitted inside it -- see
                :func:`_count_dots_bitmap` for why the split.

                ``dc`` is in content coordinates (the canvas ``wx.MemoryDC``, or the
                scroll-shifted ``AutoBufferedPaintDC`` the selected overlay paints on),
                which is what :func:`count_dot_layout` returns, so the strip's rect goes
                straight in.
        """
        strip, _dots = count_dot_layout(rect, count)
        pad = DECK_CARD_COUNT_STRIP_PADDING
        dc.SetBrush(wx.Brush(wx.Colour(*backing_rgb)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRoundedRectangle(strip.x, strip.y, strip.width, strip.height, strip.width // 2)
        dc.DrawBitmap(
            _count_dots_bitmap(count, backing_rgb, dot_rgb), strip.x + pad, strip.y + pad, False
        )

    def _draw_actions(self, dc: wx.DC, rect: wx.Rect, name: str) -> None:
        # bold=True is buying glyph legibility at body size on top of card art,
        # not marking a heading -- see type_font's docstring.
        dc.SetFont(type_font("body", bold=True))
        for idx, (button_rect, glyph) in enumerate(
            zip(self._action_button_rects(rect), _ACTION_GLYPHS)
        ):
            # Three saturated accent chips on every hovered card was the densest
            # accent in the app after the toolbar, and it made `+`, `-` and `x`
            # read as three primary actions. Neutral raised chips instead; the
            # glyph is what says what each one does.
            pressed = self._pressed == (name, idx)
            bg = DARK_ALT if pressed else SURFACE_RAISED
            dc.SetBrush(wx.Brush(wx.Colour(*bg)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRoundedRectangle(button_rect, _ACTION_BUTTON_RADIUS)
            dc.SetTextForeground(wx.Colour(*TEXT_PRIMARY))
            gw, gh = dc.GetTextExtent(glyph)
            dc.DrawText(
                glyph,
                button_rect.x + (button_rect.width - gw) // 2,
                button_rect.y + (button_rect.height - gh) // 2,
            )
