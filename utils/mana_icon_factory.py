import re
import sys
from pathlib import Path

import wx
from loguru import logger

from utils.constants import DARK_ALT, SUBDUED_TEXT


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


class ManaIconFactory:
    FALLBACK_COLORS = {
        "w": (253, 251, 206),
        "u": (188, 218, 247),
        "b": (128, 115, 128),
        "r": (241, 155, 121),
        "g": (159, 203, 166),
        "c": (208, 198, 187),
        "multicolor": (246, 223, 138),
    }
    _FONT_LOADED = False
    _FONT_NAME = "Mana"

    def __init__(self, icon_size: int = 26) -> None:
        self._cache: dict[str, wx.Bitmap] = {}
        self._cost_cache: dict[str, wx.Bitmap] = {}
        self._glyph_map, self._color_map = self._load_css_resources()
        self._ensure_font_loaded()
        self._icon_size = max(8, icon_size)

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
            margin = 1 if idx < len(tokens) - 1 else 0
            sizer.Add(icon, 0, wx.RIGHT, margin)
        icon_span = self._icon_size + 2
        panel.SetMinSize((max(icon_span, len(tokens) * icon_span), self._icon_size + 6))
        return panel

    def bitmap_for_symbol(self, symbol: str) -> wx.Bitmap:
        token = symbol.strip()
        if token.startswith("{") and token.endswith("}"):
            token = token[1:-1]
        return self._get_bitmap(token or "")

    def bitmap_for_cost(self, mana_cost: str) -> wx.Bitmap | None:
        """
        Render an entire mana cost into a single bitmap for compact display.

        Args:
            mana_cost: Mana cost string using curly-brace tokens (e.g., "{1}{G}{G}")

        Returns:
            wx.Bitmap with all mana symbols composed horizontally, or None if no symbols.
        """
        tokens = self._tokenize(mana_cost)
        if not tokens:
            return None
        cache_key = "|".join(tokens)
        if cache_key in self._cost_cache:
            return self._cost_cache[cache_key]
        bitmaps = [self._get_bitmap(token) for token in tokens]
        height = max((bmp.GetHeight() for bmp in bitmaps), default=0)
        width = sum(bmp.GetWidth() for bmp in bitmaps) + max(0, len(bitmaps) - 1) * 2
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
                x += 2
        dc.SelectObject(wx.NullBitmap)
        self._cost_cache[cache_key] = composed
        return composed

    def _tokenize(self, cost: str) -> list[str]:
        return _split_mana_cost_tokens(cost, uppercase=False)

    def _get_bitmap(self, symbol: str) -> wx.Bitmap:
        if symbol in self._cache:
            return self._cache[symbol]
        key = self._normalize_symbol(symbol)
        components = self._hybrid_components(key)
        second_color: tuple[int, int, int] | None = None
        glyph = self._glyph_map.get(key or "") if not components else ""
        scale = 3
        size = self._icon_size * scale
        bmp = wx.Bitmap(size, size)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(DARK_ALT))
        dc.Clear()

        cx = cy = size // 2
        radius = (size // 2) - scale
        gctx = wx.GraphicsContext.Create(dc)
        shadow_colour = wx.Colour(0, 0, 0, 80)
        gctx.SetPen(wx.Pen(wx.Colour(0, 0, 0, 0)))
        gctx.SetBrush(wx.Brush(shadow_colour))
        gctx.DrawEllipse(cx - radius + scale, cy - radius + scale, radius * 2, radius * 2)

        text_font = self._build_render_font(13 * scale)
        text_color = wx.Colour(20, 20, 20)
        if components:
            second_color = self._draw_hybrid_circle(gctx, cx, cy, radius, components)
        else:
            fill_color = self._color_for_key(key or "")
            gctx.SetPen(wx.Pen(wx.Colour(25, 25, 25, 140), 2))
            gctx.SetBrush(wx.Brush(wx.Colour(*fill_color)))
            gctx.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
            glyph_to_draw = glyph or self._glyph_fallback(key)
            if glyph_to_draw:
                gctx.SetFont(text_font, text_color)
                tw, th = gctx.GetTextExtent(glyph_to_draw)
                gctx.DrawText(glyph_to_draw, cx - tw / 2, cy - th / 2)

        dc.SelectObject(wx.NullBitmap)

        if components and second_color:
            bmp = self._apply_hybrid_overlay(bmp, cx, cy, radius, second_color)
            dc = wx.MemoryDC(bmp)
            gctx = wx.GraphicsContext.Create(dc)
            self._draw_hybrid_glyph(gctx, cx, cy, radius, components, text_font, text_color)
            dc.SelectObject(wx.NullBitmap)
        img = bmp.ConvertToImage()
        img = img.Blur(1)
        img = img.Scale(self._icon_size, self._icon_size, wx.IMAGE_QUALITY_HIGH)
        final = wx.Bitmap(img)
        self._cache[symbol] = final
        return final

    def _build_render_font(self, font_size: int) -> wx.Font:
        if self._FONT_LOADED:
            return wx.Font(
                font_size,
                wx.FONTFAMILY_DEFAULT,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
                False,
                self._FONT_NAME,
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
        pen_color = wx.Colour(25, 25, 25, 160) if outline else wx.Colour(0, 0, 0, 0)
        width = 2 if outline else 0
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
        gctx.SetPen(wx.Pen(wx.Colour(25, 25, 25, 200), 2))
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
        offsets = [(-radius * 0.3, -radius * 0.3), (radius * 0.3, radius * 0.3)]
        glyph_font = self._scaled_font(font, 0.52)
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

    def _scaled_font(self, font: wx.Font, factor: float) -> wx.Font:
        size = max(6, int(font.GetPointSize() * factor))
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

    def _ensure_font_loaded(self) -> None:
        if ManaIconFactory._FONT_LOADED:
            return
        font_path = self._assets_root() / "assets" / "mana" / "fonts" / "mana.ttf"
        if not font_path.exists():
            logger.debug("Mana font not found at %s; using fallback glyphs", font_path)
            return
        try:
            wx.Font.AddPrivateFont(str(font_path))
            ManaIconFactory._FONT_LOADED = True
        except Exception as exc:  # pragma: no cover
            logger.debug(f"Unable to load mana font: {exc}")

    def _load_css_resources(self) -> tuple[dict[str, str], dict[str, tuple[int, int, int]]]:
        glyphs: dict[str, str] = {}
        colors: dict[str, tuple[int, int, int]] = {}
        css_path = self._assets_root() / "assets" / "mana" / "css" / "mana.min.css"
        if not css_path.exists():
            return glyphs, {k: tuple(v) for k, v in self.FALLBACK_COLORS.items()}
        css_text = css_path.read_text(encoding="utf-8")
        color_re = re.compile(r"--ms-mana-([a-z0-9-]+):\s*#([0-9a-fA-F]{6})")
        for match in color_re.finditer(css_text):
            key = match.group(1).lower()
            hex_value = match.group(2)
            colors[key] = tuple(int(hex_value[i : i + 2], 16) for i in (0, 2, 4))
        for block in css_text.split("}"):
            if "content" not in block or "::" not in block:
                continue
            parts = block.split("{", 1)
            if len(parts) != 2:
                continue
            selectors, body = parts
            content_match = re.search(r'content:\s*"([^"]+)"', body)
            if not content_match:
                continue
            glyph_char = content_match.group(1)
            for raw_selector in selectors.split(","):
                raw_selector = raw_selector.strip()
                if not raw_selector.startswith(".ms-"):
                    continue
                cls = raw_selector.split("::", 1)[0].replace(".ms-", "").lower()
                if cls:
                    glyphs[cls] = glyph_char
        for base, rgb in self.FALLBACK_COLORS.items():
            colors.setdefault(base, rgb)
        return glyphs, colors

    def _assets_root(self) -> Path:
        """Locate bundled assets in both source and PyInstaller builds."""
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            return Path(frozen_root)
        return Path(__file__).resolve().parents[1]


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
