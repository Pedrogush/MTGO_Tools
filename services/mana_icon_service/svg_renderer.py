"""SVG-based transparent-PNG rendering for mana symbols.

Distinct from :class:`BitmapRendererMixin`, which composes onto a solid
``DARK_ALT`` square for :class:`wx.StaticBitmap` use. This mixin renders each
symbol on a fully transparent canvas at high resolution from the vendored
``assets/mana/svg`` glyphs, then downscales once with high quality. The
resulting PNGs blend invisibly with whatever ``bgcolor`` the consuming
``wx.html.HtmlWindow`` uses.

Expects the composing class to supply ``_color_map`` (loaded by
:class:`ManaIconResources`) and an ``_assets_root()`` method. The mixin owns
its own SVG image cache, PNG path cache, and rasterized PNG directory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import wx
import wx.svg

_RENDER_SCALE = 4
_GLYPH_INSET_RATIO = 0.30
_HYBRID_GLYPH_INSET_RATIO = 0.42
_OUTLINE_WIDTH_PX = 1

# Lighter palette than ``BitmapRendererMixin.FALLBACK_COLORS`` — these read
# better on the dark Card-panel HTML background. ``ManaIconResources``-loaded
# colors take precedence when present.
_FALLBACK_COLORS: dict[str, tuple[int, int, int]] = {
    "w": (240, 242, 192),
    "u": (181, 205, 227),
    "b": (172, 162, 154),
    "r": (219, 134, 100),
    "g": (147, 180, 131),
    "c": (208, 198, 187),
    "tap": (208, 198, 187),
    "untap": (17, 17, 17),
    "s": (210, 217, 227),
    "multicolor": (246, 223, 138),
}

_GLYPH_COLOR_RGB = (0, 0, 0)
_GLYPH_COLOR_ON_DARK_RGB = (235, 235, 235)
_OUTLINE_COLOR_RGBA = (20, 20, 20, 180)

_MANA_BASE = frozenset("wubrg")


def _normalize_token(symbol: str) -> str:
    token = symbol.strip().lower()
    if token.startswith("{") and token.endswith("}"):
        token = token[1:-1]
    token = token.replace("{", "").replace("}", "").strip()
    if "/" in token:
        parts = [p for p in token.split("/") if p]
        if all(p.isdigit() for p in parts):
            token = "-".join(parts)
        else:
            token = "".join(parts)
    aliases = {
        "t": "tap",
        "untap": "untap",
        "snow": "s",
        "energy": "e",
        "1-2": "half",
        "½": "half",
    }
    return aliases.get(token, token)


def _svg_hybrid_components(key: str) -> list[str] | None:
    """Return ``[a, b]`` for two-color hybrid tokens like ``ub``, ``2w``, ``cw``.

    Phyrexian (``wp``) is treated as a single-color token with a phyrexian
    glyph, not a split.
    """
    if len(key) != 2:
        return None
    a, b = key[0], key[1]
    if a in _MANA_BASE and b in _MANA_BASE:
        return [a, b]
    if a == "2" and b in _MANA_BASE:
        return ["c", b]
    if a == "c" and b in _MANA_BASE:
        return ["c", b]
    return None


def _is_phyrexian(key: str) -> bool:
    return len(key) == 2 and key[1] == "p" and key[0] in _MANA_BASE


class SvgRendererMixin:
    """Transparent-PNG rendering of mana symbols via vendored SVG glyphs.

    Expects the composing class to supply an ``_assets_root()`` method. Owns
    its own ``_svg_color_map``, ``_svg_cache``, ``_png_cache``, and
    ``_rasterizer_cache_dir`` mutable state, initialized in the composer's
    ``__init__``. The SVG color map is intentionally separate from
    :class:`BitmapRendererMixin`'s ``_color_map`` so the lighter
    ``_FALLBACK_COLORS`` here (better contrast on the dark Card-panel HTML
    background) don't bleed into the solid-background bitmap rendering.
    """

    _svg_color_map: dict[str, tuple[int, int, int]]
    _svg_cache: dict[str, "wx.svg.SVGimage | None"]
    _png_cache: dict[tuple[str, int], Path]
    _rasterizer_cache_dir: Path | None

    def _assets_root(self) -> Path: ...  # supplied by composing class

    @staticmethod
    def _load_svg_color_map(assets_root: Path) -> dict[str, tuple[int, int, int]]:
        """Build the SVG-renderer color map: CSS values + lighter fallbacks."""
        from services.mana_icon_service.resources import ManaIconResources

        _, colors = ManaIconResources.load_css_resources(assets_root, _FALLBACK_COLORS)
        for k, v in _FALLBACK_COLORS.items():
            colors.setdefault(k, v)
        return colors

    def transparent_png_path(self, symbol: str, height: int) -> Path | None:
        """Return the cached transparent PNG for ``symbol`` at ``height`` px.

        Returns ``None`` if the symbol cannot be rasterized (missing glyph for
        an unrecognized token). Callers fall back to the literal ``{TOKEN}``
        text in that case.
        """
        if height <= 0:
            return None
        key = _normalize_token(symbol)
        if not key:
            return None
        cache_key = (key, height)
        cached = self._png_cache.get(cache_key)
        if cached is not None and cached.exists():
            return cached
        bmp = self._render_transparent(key, height)
        if bmp is None:
            return None
        path = self._svg_destination_path(key, height)
        bmp.ConvertToImage().SaveFile(str(path), wx.BITMAP_TYPE_PNG)
        self._png_cache[cache_key] = path
        return path

    # ============= Private =============

    def _render_transparent(self, key: str, height: int) -> wx.Bitmap | None:
        size = max(8, height) * _RENDER_SCALE
        bmp = self._make_transparent_bitmap(size)
        components = _svg_hybrid_components(key)
        # Draw the colored circle (and split overlay) using pixel ops on the
        # underlying image, then redraw glyphs through a GraphicsContext on the
        # resulting bitmap. wx.GraphicsContext.Clip() doesn't accept paths, and
        # we need a precise diagonal split for hybrid mana — pixels are simpler
        # and the result is cached.
        dc = wx.MemoryDC(bmp)
        gctx = wx.GraphicsContext.Create(dc)
        try:
            self._draw_svg_background(gctx, key, size, components)
        finally:
            dc.SelectObject(wx.NullBitmap)
        if components is not None:
            bmp = self._apply_split_overlay(bmp, size, components)

        dc = wx.MemoryDC(bmp)
        gctx = wx.GraphicsContext.Create(dc)
        try:
            self._draw_svg_glyphs(gctx, key, size, components)
        finally:
            dc.SelectObject(wx.NullBitmap)

        img = bmp.ConvertToImage()
        if not img.HasAlpha():
            img.InitAlpha()
        img = img.Scale(height, height, wx.IMAGE_QUALITY_HIGH)
        return wx.Bitmap(img)

    def _draw_svg_background(
        self,
        gctx: wx.GraphicsContext,
        key: str,
        size: int,
        components: list[str] | None,
    ) -> None:
        cx = cy = size / 2
        radius = (size / 2) - _OUTLINE_WIDTH_PX * _RENDER_SCALE / 2

        if key == "e":
            return  # Energy renders as a standalone glyph with no circle.

        if components is not None:
            top_color = self._svg_color_for(components[0])
            self._draw_filled_circle(gctx, cx, cy, radius, top_color)
            return

        color_key = (
            key[0]
            if _is_phyrexian(key)
            else key if key in {"tap", "untap"} else self._svg_color_key_for(key)
        )
        self._draw_filled_circle(gctx, cx, cy, radius, self._svg_color_for(color_key))

    def _draw_svg_glyphs(
        self,
        gctx: wx.GraphicsContext,
        key: str,
        size: int,
        components: list[str] | None,
    ) -> None:
        cx = cy = size / 2
        radius = (size / 2) - _OUTLINE_WIDTH_PX * _RENDER_SCALE / 2

        if components is not None:
            self._draw_hybrid_svg_glyphs(gctx, cx, cy, radius, components, key)
            return

        if key == "e":
            self._draw_standalone_svg_glyph(gctx, cx, cy, radius, "e")
            return

        if _is_phyrexian(key):
            self._draw_svg_glyph(gctx, cx, cy, radius, "p", on_dark=False)
            return

        if key == "untap":
            self._draw_svg_glyph(gctx, cx, cy, radius, "tap", on_dark=True)
            return

        self._draw_svg_glyph(gctx, cx, cy, radius, key, on_dark=False)

    def _make_transparent_bitmap(self, size: int) -> wx.Bitmap:
        # FromRGBA initializes every pixel to (0,0,0,0) — fully transparent.
        return wx.Bitmap.FromRGBA(size, size, 0, 0, 0, 0)

    def _draw_filled_circle(
        self,
        gctx: wx.GraphicsContext,
        cx: float,
        cy: float,
        radius: float,
        color: tuple[int, int, int],
    ) -> None:
        gctx.SetPen(wx.Pen(wx.Colour(*_OUTLINE_COLOR_RGBA), _OUTLINE_WIDTH_PX * _RENDER_SCALE))
        gctx.SetBrush(wx.Brush(wx.Colour(*color)))
        gctx.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

    def _apply_split_overlay(
        self,
        bmp: wx.Bitmap,
        size: int,
        components: list[str],
    ) -> wx.Bitmap:
        """Repaint the lower-right half of the colored circle with the second
        component's color. Operates in pixel space because GraphicsContext
        clipping does not accept arbitrary paths in our wx build.
        """
        bottom_color = self._svg_color_for(components[1])
        img = bmp.ConvertToImage()
        if not img.HasAlpha():
            img.InitAlpha()
        cx = cy = size / 2
        radius = (size / 2) - _OUTLINE_WIDTH_PX * _RENDER_SCALE / 2
        # Inset by one px so the outline stroke isn't overwritten.
        limit = max(1.0, radius - 1.5)
        limit_sq = limit * limit
        cr, cg, cb = bottom_color
        width, height = img.GetWidth(), img.GetHeight()
        for x in range(width):
            dx = x - cx
            dxsq = dx * dx
            for y in range(height):
                dy = y - cy
                if dxsq + dy * dy > limit_sq:
                    continue
                if dx + dy >= 0:
                    img.SetRGB(x, y, cr, cg, cb)
        return wx.Bitmap(img)

    def _draw_svg_glyph(
        self,
        gctx: wx.GraphicsContext,
        cx: float,
        cy: float,
        radius: float,
        glyph_key: str,
        *,
        on_dark: bool,
    ) -> None:
        svg = self._load_svg(glyph_key)
        if svg is None:
            return
        glyph_box = (radius * 2) * (1 - _GLYPH_INSET_RATIO)
        self._render_svg_glyph(gctx, svg, cx, cy, glyph_box, on_dark=on_dark)

    def _draw_standalone_svg_glyph(
        self,
        gctx: wx.GraphicsContext,
        cx: float,
        cy: float,
        radius: float,
        glyph_key: str,
    ) -> None:
        svg = self._load_svg(glyph_key)
        if svg is None:
            return
        glyph_box = radius * 2 * 0.95
        self._render_svg_glyph(gctx, svg, cx, cy, glyph_box, on_dark=False)

    def _draw_hybrid_svg_glyphs(
        self,
        gctx: wx.GraphicsContext,
        cx: float,
        cy: float,
        radius: float,
        components: list[str],
        key: str,
    ) -> None:
        glyph_box = (radius * 2) * (1 - _HYBRID_GLYPH_INSET_RATIO)
        offset = radius * 0.42
        # Top-left: first component (or "2" for {2/W}-style).
        first_glyph = key[0] if key[0] == "2" else components[0]
        second_glyph = components[1]
        first_svg = self._load_svg(first_glyph)
        second_svg = self._load_svg(second_glyph)
        if first_svg is not None:
            self._render_svg_glyph(
                gctx, first_svg, cx - offset, cy - offset, glyph_box, on_dark=False
            )
        if second_svg is not None:
            self._render_svg_glyph(
                gctx, second_svg, cx + offset, cy + offset, glyph_box, on_dark=False
            )

    def _render_svg_glyph(
        self,
        gctx: wx.GraphicsContext,
        svg: wx.svg.SVGimage,
        cx: float,
        cy: float,
        target: float,
        *,
        on_dark: bool,
    ) -> None:
        size_px = max(1, int(round(target)))
        bmp = svg.ConvertToScaledBitmap(wx.Size(size_px, size_px))
        # The vendored SVGs are filled with #444 — recolor unconditionally so
        # the glyph renders as pure black (or _GLYPH_COLOR_ON_DARK_RGB on dark bg).
        color = wx.Colour(*(_GLYPH_COLOR_ON_DARK_RGB if on_dark else _GLYPH_COLOR_RGB))
        bmp = self._recolor_glyph(bmp, color)
        gctx.DrawBitmap(bmp, cx - size_px / 2, cy - size_px / 2, size_px, size_px)

    def _recolor_glyph(self, bmp: wx.Bitmap, color: wx.Colour) -> wx.Bitmap:
        """Replace the dark glyph fill with ``color``, preserving alpha."""
        img = bmp.ConvertToImage()
        if not img.HasAlpha():
            img.InitAlpha()
        width, height = img.GetWidth(), img.GetHeight()
        data = bytearray(img.GetData())
        r, g, b = color.Red(), color.Green(), color.Blue()
        for i in range(0, len(data), 3):
            data[i] = r
            data[i + 1] = g
            data[i + 2] = b
        new_img = wx.Image(width, height)
        new_img.SetData(bytes(data))
        new_img.SetAlpha(img.GetAlpha())
        return wx.Bitmap(new_img)

    def _load_svg(self, glyph_key: str) -> "wx.svg.SVGimage | None":
        if glyph_key in self._svg_cache:
            return self._svg_cache[glyph_key]
        svg_dir = self._assets_root() / "assets" / "mana" / "svg"
        path = svg_dir / f"{glyph_key}.svg"
        svg: wx.svg.SVGimage | None = None
        if path.exists():
            try:
                svg = wx.svg.SVGimage.CreateFromFile(str(path))
            except Exception:
                svg = None
        self._svg_cache[glyph_key] = svg
        return svg

    def _svg_color_key_for(self, key: str) -> str | None:
        if not key:
            return None
        if key in self._svg_color_map:
            return key
        if key in _FALLBACK_COLORS:
            return key
        if key.isdigit() or key in {"x", "y", "z"}:
            return "c"
        if key[0] in _MANA_BASE:
            return key[0]
        return None

    def _svg_color_for(self, key: str | None) -> tuple[int, int, int]:
        if key and key in self._svg_color_map:
            return self._svg_color_map[key]
        if key and key in _FALLBACK_COLORS:
            return _FALLBACK_COLORS[key]
        return _FALLBACK_COLORS["multicolor"]

    def _svg_destination_path(self, key: str, height: int) -> Path:
        if self._rasterizer_cache_dir is None:
            self._rasterizer_cache_dir = Path(tempfile.mkdtemp(prefix="mtgo_card_panel_mana_"))
        safe = "".join(c if c.isalnum() else "_" for c in key) or "sym"
        return self._rasterizer_cache_dir / f"{safe}_{height}.png"
