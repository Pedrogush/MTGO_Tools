"""wx bitmap rendering for mana symbols.

Drawing primitives plus the cache-aware ``_get_bitmap`` / ``_get_standalone_bitmap``
entry points used by :class:`ManaIconFactory`. Reads/writes to the shared
:class:`ManaBitmapCache` instance owned by the factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from services.mana_icon_service.resources import ManaIconResources
from utils.constants import DARK_ALT
from utils.constants.ui_images import (
    MANA_GLYPH_FONT_SIZE_BASE,
    MANA_GLYPH_FONT_SIZE_MIN,
    MANA_ICON_BLUR_RADIUS,
    MANA_OUTLINE_DARK_RGB,
    MANA_TEXT_DARK_RGB,
)

if TYPE_CHECKING:
    from services.mana_icon_service.cache import ManaBitmapCache


class BitmapRendererMixin:
    """Drawing methods for :class:`ManaIconFactory`.

    Expects the composing class to supply ``_cache`` (a :class:`ManaBitmapCache`),
    ``_icon_size``, ``_glyph_map``, and ``_color_map`` attributes on ``self``.
    """

    _HYBRID_GLYPH_OFFSETS = ((-0.3, -0.3), (0.3, 0.3))
    _HYBRID_GLYPH_SCALE = 0.52
    _SHADOW_ALPHA = 80
    _OUTLINE_ALPHA = 140
    _OUTLINE_ALPHA_STRONG = 200
    _OUTLINE_ALPHA_COMPONENT = 160
    _OUTLINE_WIDTH = 2
    _PADDING = 2
    _RENDER_SCALE = 3

    FALLBACK_COLORS = {
        "w": (253, 251, 206),
        "u": (188, 218, 247),
        "b": (128, 115, 128),
        "r": (241, 155, 121),
        "g": (159, 203, 166),
        "c": (208, 198, 187),
        "tap": (208, 198, 187),
        "multicolor": (246, 223, 138),
    }

    # Symbols that are NOT circle-enclosed mana icons — rendered as bare glyphs.
    _NON_CIRCLE_SYMBOLS: frozenset[str] = frozenset({"e", "energy"})

    # Glyph colours for standalone (non-circle) symbols.
    # Energy is silver-grey to match how it appears on actual MTG cards.
    _STANDALONE_COLORS: dict[str, tuple[int, int, int]] = {
        "e": (175, 170, 165),
        "energy": (175, 170, 165),
    }

    # Attributes supplied by the composing class's __init__.
    _cache: ManaBitmapCache
    _icon_size: int
    _glyph_map: dict[str, str]
    _color_map: dict[str, tuple[int, int, int]]

    def _get_bitmap(self, symbol: str) -> wx.Bitmap:
        if symbol in self._cache.bitmaps:
            return self._cache.bitmaps[symbol]
        key = self._normalize_symbol(symbol)
        if key in self._NON_CIRCLE_SYMBOLS:
            return self._get_standalone_bitmap(symbol, key)
        components = self._hybrid_components(key)
        second_color: tuple[int, int, int] | None = None
        glyph = self._glyph_map.get(key or "") if not components else ""
        scale = self._RENDER_SCALE
        size = self._icon_size * scale
        bmp = wx.Bitmap(size, size)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(DARK_ALT))
        dc.Clear()

        cx = cy = size // 2
        radius = (size // 2) - scale
        gctx = wx.GraphicsContext.Create(dc)
        shadow_colour = wx.Colour(0, 0, 0, self._SHADOW_ALPHA)
        gctx.SetPen(wx.Pen(wx.Colour(0, 0, 0, 0)))
        gctx.SetBrush(wx.Brush(shadow_colour))
        gctx.DrawEllipse(
            cx - radius + scale,
            cy - radius + scale,
            radius * 2,
            radius * 2,
        )

        text_font = self._build_render_font(MANA_GLYPH_FONT_SIZE_BASE * scale)
        text_color = wx.Colour(MANA_TEXT_DARK_RGB, MANA_TEXT_DARK_RGB, MANA_TEXT_DARK_RGB)
        if components:
            second_color = self._draw_hybrid_circle(gctx, cx, cy, radius, components)
        else:
            fill_color = self._color_for_key(key or "")
            gctx.SetPen(
                wx.Pen(
                    wx.Colour(
                        MANA_OUTLINE_DARK_RGB,
                        MANA_OUTLINE_DARK_RGB,
                        MANA_OUTLINE_DARK_RGB,
                        self._OUTLINE_ALPHA,
                    ),
                    self._OUTLINE_WIDTH,
                )
            )
            gctx.SetBrush(wx.Brush(wx.Colour(*fill_color)))
            gctx.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
            glyph_to_draw = glyph or self._glyph_fallback(key)
            if glyph_to_draw:
                gctx.SetFont(text_font, text_color)
                tw, th = gctx.GetTextExtent(glyph_to_draw)
                gctx.DrawText(glyph_to_draw, cx - tw / 2, cy - th / 2)

        dc.SelectObject(wx.NullBitmap)

        if components and second_color:
            bmp = self._render_hybrid_overlay(
                bmp,
                cx,
                cy,
                radius,
                second_color,
                components,
                text_font,
                text_color,
            )
        img = bmp.ConvertToImage()
        img = img.Blur(MANA_ICON_BLUR_RADIUS)
        self._cache.hires_bitmaps[symbol] = wx.Bitmap(img)  # store at render-scale before downscale
        img = img.Scale(self._icon_size, self._icon_size, wx.IMAGE_QUALITY_HIGH)
        final = wx.Bitmap(img)
        self._cache.bitmaps[symbol] = final
        return final

    def _get_standalone_bitmap(self, symbol: str, key: str | None) -> wx.Bitmap:
        """Render a standalone glyph without a circle background (e.g. energy {E})."""
        scale = self._RENDER_SCALE
        size = self._icon_size * scale
        bmp = wx.Bitmap(size, size)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(DARK_ALT))
        dc.Clear()
        glyph = self._glyph_map.get(key or "") if key else ""
        if glyph:
            cx = cy = size // 2
            gctx = wx.GraphicsContext.Create(dc)
            # Slightly larger font than in-circle glyphs — no border to eat into space.
            font_size = int(MANA_GLYPH_FONT_SIZE_BASE * scale * 1.25)
            text_font = self._build_render_font(font_size)
            color_rgb = self._STANDALONE_COLORS.get(key or "", (220, 200, 140))
            text_color = wx.Colour(*color_rgb)
            gctx.SetFont(text_font, text_color)
            tw, th = gctx.GetTextExtent(glyph)
            gctx.DrawText(glyph, cx - tw / 2, cy - th / 2)
        dc.SelectObject(wx.NullBitmap)
        img = bmp.ConvertToImage()
        img = img.Blur(MANA_ICON_BLUR_RADIUS)
        self._cache.hires_bitmaps[symbol] = wx.Bitmap(img)
        img = img.Scale(self._icon_size, self._icon_size, wx.IMAGE_QUALITY_HIGH)
        final = wx.Bitmap(img)
        self._cache.bitmaps[symbol] = final
        return final

    def _build_render_font(self, font_size: int) -> wx.Font:
        if ManaIconResources.font_loaded():
            return wx.Font(
                font_size,
                wx.FONTFAMILY_DEFAULT,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
                False,
                ManaIconResources.FONT_NAME,
            )
        font = wx.Font(wx.FontInfo(font_size).Family(wx.FONTFAMILY_SWISS))
        font.MakeBold()
        return font

    def _draw_component(
        self,
        gctx: wx.GraphicsContext,
        cx: int,
        cy: int,
        radius: int,
        key: str | None,
        font: wx.Font,
        text_color: wx.Colour,
        outline: bool = True,
    ) -> None:
        color = self._color_for_key(key or "")
        pen_color = (
            wx.Colour(
                MANA_OUTLINE_DARK_RGB,
                MANA_OUTLINE_DARK_RGB,
                MANA_OUTLINE_DARK_RGB,
                self._OUTLINE_ALPHA_COMPONENT,
            )
            if outline
            else wx.Colour(0, 0, 0, 0)
        )
        width = self._OUTLINE_WIDTH if outline else 0
        gctx.SetPen(wx.Pen(pen_color, width))
        gctx.SetBrush(wx.Brush(wx.Colour(*color)))
        gctx.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        glyph = self._glyph_fallback(key)
        if glyph:
            gctx.SetFont(font, text_color)
            tw, th = gctx.GetTextExtent(glyph)
            gctx.DrawText(glyph, cx - tw / 2, cy - th / 2)

    def _draw_hybrid_circle(
        self,
        gctx: wx.GraphicsContext,
        cx: int,
        cy: int,
        radius: int,
        components: list[str],
    ) -> tuple[int, int, int]:
        rect = (cx - radius, cy - radius, radius * 2, radius * 2)
        base = self._color_for_key(components[0])
        second = self._color_for_key(components[1])
        gctx.SetPen(
            wx.Pen(
                wx.Colour(
                    MANA_OUTLINE_DARK_RGB,
                    MANA_OUTLINE_DARK_RGB,
                    MANA_OUTLINE_DARK_RGB,
                    self._OUTLINE_ALPHA_STRONG,
                ),
                self._OUTLINE_WIDTH,
            )
        )
        gctx.SetBrush(wx.Brush(wx.Colour(*base)))
        gctx.DrawEllipse(*rect)
        gctx.StrokeLine(cx - radius, cy + radius, cx + radius, cy - radius)
        return second

    def _draw_hybrid_glyph(
        self,
        gctx: wx.GraphicsContext,
        cx: int,
        cy: int,
        radius: int,
        components: list[str],
        font: wx.Font,
        text_color: wx.Colour,
    ) -> None:
        offsets = [
            (radius * self._HYBRID_GLYPH_OFFSETS[0][0], radius * self._HYBRID_GLYPH_OFFSETS[0][1]),
            (radius * self._HYBRID_GLYPH_OFFSETS[1][0], radius * self._HYBRID_GLYPH_OFFSETS[1][1]),
        ]
        glyph_font = self._scaled_font(font, self._HYBRID_GLYPH_SCALE)
        for idx, component in enumerate(components):
            glyph = self._glyph_fallback(component)
            if not glyph:
                continue
            gctx.SetFont(glyph_font, text_color)
            dx, dy = offsets[idx] if idx < len(offsets) else (0, 0)
            tw, th = gctx.GetTextExtent(glyph)
            gctx.DrawText(glyph, cx - tw / 2 + dx, cy - th / 2 + dy)
        # Restore original font to avoid surprising callers.
        gctx.SetFont(font, text_color)

    def _apply_hybrid_overlay(
        self,
        bmp: wx.Bitmap,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
    ) -> wx.Bitmap:
        img = bmp.ConvertToImage()
        width, height = img.GetWidth(), img.GetHeight()
        limit = max(1, radius - 1)
        limit_sq = limit * limit
        cr, cg, cb = color
        for x in range(width):
            dx = x - cx
            for y in range(height):
                dy = y - cy
                if dx * dx + dy * dy > limit_sq:
                    continue
                if dx + dy >= 0:
                    img.SetRGB(x, y, cr, cg, cb)
        return wx.Bitmap(img)

    def _render_hybrid_overlay(
        self,
        bmp: wx.Bitmap,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
        components: list[str],
        font: wx.Font,
        text_color: wx.Colour,
    ) -> wx.Bitmap:
        bmp = self._apply_hybrid_overlay(bmp, cx, cy, radius, color)
        dc = wx.MemoryDC(bmp)
        gctx = wx.GraphicsContext.Create(dc)
        self._draw_hybrid_glyph(gctx, cx, cy, radius, components, font, text_color)
        dc.SelectObject(wx.NullBitmap)
        return bmp

    def _scaled_font(self, font: wx.Font, factor: float) -> wx.Font:
        size = max(MANA_GLYPH_FONT_SIZE_MIN, int(font.GetPointSize() * factor))
        try:
            return wx.Font(
                size,
                font.GetFamily(),
                font.GetStyle(),
                font.GetWeight(),
                font.GetUnderlined(),
                font.GetFaceName(),
            )
        except Exception:
            return font

    def _glyph_fallback(self, key: str | None) -> str:
        if not key:
            return ""
        glyph = self._glyph_map.get(key)
        if glyph:
            return glyph
        compact = key.replace("/", "")
        glyph = self._glyph_map.get(compact)
        if glyph:
            return glyph
        if len(key) > 1:
            tail = key[-1]
            glyph = self._glyph_map.get(tail)
            if glyph:
                return glyph
        fallback = key.upper()
        return fallback

    def _color_for_key(self, key: str | None) -> tuple[int, int, int]:
        if not key:
            return self.FALLBACK_COLORS["multicolor"]
        if key in self._color_map:
            return self._color_map[key]
        if key in self.FALLBACK_COLORS:
            return self.FALLBACK_COLORS[key]
        if key.isdigit() or key in {"x", "y", "z"}:
            return self._color_map.get("c", self.FALLBACK_COLORS["c"])
        if "-" in key:
            for part in key.split("-"):
                if part in self._color_map:
                    return self._color_map[part]
        if key[0] in self._color_map:
            return self._color_map[key[0]]
        if len(key) >= 2 and key[0].isdigit() and key[1] in self._color_map:
            return self._color_map[key[1]]
        return self.FALLBACK_COLORS["multicolor"]

    def _normalize_symbol(self, symbol: str) -> str | None:
        token = symbol.strip().lower().replace("{", "").replace("}", "")
        if not token:
            return None
        token = token.replace("½", "half")
        if "/" in token:
            parts = [part for part in token.split("/") if part]
            if all(part.isdigit() for part in parts if part):
                token = "-".join(filter(None, parts))
            else:
                token = "".join(parts)
        aliases = {
            "∞": "infinity",
            "1/2": "1-2",
            "half": "1-2",
            "snow": "s",
            "t": "tap",
        }
        return aliases.get(token, token)

    def _hybrid_components(self, key: str | None) -> list[str] | None:
        if not key or len(key) < 2:
            return None
        base = set("wubrg")
        first, second = key[0], key[1]
        if first in base.union({"c"}) and second in base:
            return [first, second]
        if first == "2" and second in base:
            return ["c", second]
        return None
