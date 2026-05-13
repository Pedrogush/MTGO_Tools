"""Public :class:`ManaIconFactory` API and module-level mana-cost helpers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import wx

from utils.constants import SUBDUED_TEXT
from utils.constants.ui_images import (
    BUILDER_MANA_ICON_GAP,
    MANA_COST_BITMAP_GAP,
    MANA_ICON_DEFAULT_SIZE,
    MANA_ICON_MIN_SIZE,
    MANA_ICON_PANEL_HEIGHT_PADDING,
    MANA_ICON_SPAN_PADDING,
)
from services.mana_icon_service.bitmap_renderer import BitmapRendererMixin
from services.mana_icon_service.cache import ManaBitmapCache
from services.mana_icon_service.resources import ManaIconResources
from services.mana_icon_service.svg_renderer import SvgRendererMixin


def _split_mana_cost_tokens(cost: str, *, uppercase: bool) -> list[str]:
    tokens: list[str] = []
    if not cost:
        return tokens
    for part in cost.replace("}", "").split("{"):
        token = part.strip()
        if not token:
            continue
        tokens.append(token.upper() if uppercase else token)
    return tokens


class ManaIconFactory(BitmapRendererMixin, SvgRendererMixin):
    def __init__(self, icon_size: int = MANA_ICON_DEFAULT_SIZE) -> None:
        self._cache = ManaBitmapCache()
        assets_root = self._assets_root()
        self._glyph_map, self._color_map = ManaIconResources.load_css_resources(
            assets_root,
            self.FALLBACK_COLORS,
        )
        ManaIconResources.ensure_font_loaded(assets_root)
        self._icon_size = max(MANA_ICON_MIN_SIZE, icon_size)
        # SVG renderer state — separate color map preserves the lighter palette
        # that reads better on the dark Card-panel HTML background.
        self._svg_color_map = SvgRendererMixin._load_svg_color_map(assets_root)
        self._svg_cache = {}
        self._png_cache = {}
        self._rasterizer_cache_dir = None

    def render(self, parent: wx.Window, mana_cost: str) -> wx.Window:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(parent.GetBackgroundColour())
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel.SetSizer(sizer)
        tokens = self._tokenize(mana_cost)
        if not tokens:
            label = wx.StaticText(panel, label="—")
            label.SetForegroundColour(SUBDUED_TEXT)
            sizer.Add(label)
            return panel
        for idx, token in enumerate(tokens):
            bmp = self._get_bitmap(token)
            icon = wx.StaticBitmap(panel, bitmap=bmp)
            margin = BUILDER_MANA_ICON_GAP if idx < len(tokens) - 1 else 0
            sizer.Add(icon, 0, wx.RIGHT, margin)
        icon_span = self._icon_size + MANA_ICON_SPAN_PADDING
        panel.SetMinSize(
            (
                max(icon_span, len(tokens) * icon_span),
                self._icon_size + MANA_ICON_PANEL_HEIGHT_PADDING,
            )
        )
        return panel

    def bitmap_for_symbol_hires(self, symbol: str) -> wx.Bitmap | None:
        """Return the symbol bitmap at render-scale resolution (before final downscale).

        Callers that need to scale to an arbitrary target size should use this
        instead of bitmap_for_symbol to avoid a second downscale of an already
        small source.  Non-circle symbols (e.g. energy) are rendered as bare
        glyphs and included here.
        """
        token = symbol.strip()
        if token.startswith("{") and token.endswith("}"):
            token = token[1:-1]
        key = token or ""
        if key not in self._cache.hires_bitmaps:
            self._get_bitmap(key)  # populates both caches as a side-effect
        return self._cache.hires_bitmaps.get(key) or self._get_bitmap(key)

    def bitmap_for_symbol(self, symbol: str) -> wx.Bitmap | None:
        token = symbol.strip()
        if token.startswith("{") and token.endswith("}"):
            token = token[1:-1]
        return self._get_bitmap(token or "")

    def png_path_for_symbol(self, symbol: str, height: int = 0) -> Path | None:
        """Return a Path to a PNG file rendering ``symbol``, suitable for HTML.

        Bitmaps are persisted lazily to a per-process temp directory and cached
        by token + height. ``height=0`` writes the symbol at its native size.
        """
        token = symbol.strip()
        if token.startswith("{") and token.endswith("}"):
            token = token[1:-1]
        if not token:
            return None
        cache_key = (token, height)
        cached = self._cache.png_paths.get(cache_key)
        if cached is not None and cached.exists():
            return cached
        bmp = self._get_bitmap(token)
        if bmp is None:
            return None
        if height > 0 and bmp.GetHeight() != height:
            img = bmp.ConvertToImage()
            ratio = height / max(1, bmp.GetHeight())
            new_w = max(1, int(round(bmp.GetWidth() * ratio)))
            img = img.Scale(new_w, height, wx.IMAGE_QUALITY_HIGH)
        else:
            img = bmp.ConvertToImage()
        if self._cache.png_dir is None:
            self._cache.png_dir = Path(tempfile.mkdtemp(prefix="mtgo_mana_icons_"))
        safe = "".join(c if c.isalnum() else "_" for c in token).lower() or "sym"
        suffix = f"_{height}" if height > 0 else ""
        path = self._cache.png_dir / f"{safe}{suffix}.png"
        img.SaveFile(str(path), wx.BITMAP_TYPE_PNG)
        self._cache.png_paths[cache_key] = path
        return path

    def bitmap_for_cost(self, mana_cost: str) -> wx.Bitmap | None:
        tokens = self._tokenize(mana_cost)
        if not tokens:
            return None
        cache_key = "|".join(tokens)
        if cache_key in self._cache.cost_bitmaps:
            return self._cache.cost_bitmaps[cache_key]
        bitmaps = [self._get_bitmap(token) for token in tokens]
        height = max((bmp.GetHeight() for bmp in bitmaps), default=0)
        width = (
            sum(bmp.GetWidth() for bmp in bitmaps) + max(0, len(bitmaps) - 1) * MANA_COST_BITMAP_GAP
        )
        if width <= 0 or height <= 0:
            return None
        composed = wx.Bitmap(width, height)
        dc = wx.MemoryDC(composed)
        try:
            dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0, 0)))
        except TypeError:
            dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0)))
        dc.Clear()
        x = 0
        for idx, bmp in enumerate(bitmaps):
            y = (height - bmp.GetHeight()) // 2
            dc.DrawBitmap(bmp, x, max(0, y), True)
            x += bmp.GetWidth()
            if idx < len(bitmaps) - 1:
                x += MANA_COST_BITMAP_GAP
        dc.SelectObject(wx.NullBitmap)
        self._cache.cost_bitmaps[cache_key] = composed
        return composed

    def _tokenize(self, cost: str) -> list[str]:
        return _split_mana_cost_tokens(cost, uppercase=False)

    def _assets_root(self) -> Path:
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            return Path(frozen_root)
        return Path(__file__).resolve().parents[2]


def normalize_mana_query(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "{" in text and "}" in text:
        return text
    upper_text = text.upper()
    tokens: list[str] = []
    i = 0
    length = len(upper_text)
    while i < length:
        ch = upper_text[i]
        if ch.isspace() or ch in {",", ";"}:
            i += 1
            continue
        if ch.isdigit():
            num = ch
            i += 1
            while i < length and upper_text[i].isdigit():
                num += upper_text[i]
                i += 1
            tokens.append(num)
            continue
        if ch == "{":
            end = upper_text.find("}", i + 1)
            if end != -1:
                tokens.append(upper_text[i + 1 : end])
                i = end + 1
                continue
            i += 1
            continue
        if ch in {"/", "}"}:
            i += 1
            continue
        if ch.isalpha() or ch in {"∞", "½"}:
            token = ch
            i += 1
            while i < length and (upper_text[i].isalpha() or upper_text[i] in {"/", "½"}):
                token += upper_text[i]
                i += 1
            if "/" in token:
                tokens.append(token)
            elif len(token) > 1:
                tokens.extend(token)
            else:
                tokens.append(token)
            continue
        i += 1
    return "".join(f"{{{tok}}}" for tok in tokens if tok)


def tokenize_mana_symbols(cost: str) -> list[str]:
    return _split_mana_cost_tokens(cost, uppercase=True)


def type_global_mana_symbol(token: str) -> None:
    text = normalize_mana_query(token)
    if not text:
        return
    simulator = wx.UIActionSimulator()
    for ch in text:
        simulator.Char(ord(ch))
