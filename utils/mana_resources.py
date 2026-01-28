import re
from pathlib import Path

import wx
from loguru import logger


class ManaIconResources:
    _FONT_LOADED = False
    FONT_NAME = "Mana"

    @classmethod
    def font_loaded(cls) -> bool:
        return cls._FONT_LOADED

    @classmethod
    def ensure_font_loaded(cls, assets_root: Path) -> bool:
        if cls._FONT_LOADED:
            return True
        font_path = assets_root / "assets" / "mana" / "fonts" / "mana.ttf"
        if not font_path.exists():
            logger.debug("Mana font not found at %s; using fallback glyphs", font_path)
            return False
        try:
            wx.Font.AddPrivateFont(str(font_path))
            cls._FONT_LOADED = True
        except Exception as exc:  # pragma: no cover
            logger.debug("Unable to load mana font: %s", exc)
        return cls._FONT_LOADED

    @classmethod
    def load_css_resources(
        cls,
        assets_root: Path,
        fallback_colors: dict[str, tuple[int, int, int]],
    ) -> tuple[dict[str, str], dict[str, tuple[int, int, int]]]:
        glyphs: dict[str, str] = {}
        colors: dict[str, tuple[int, int, int]] = {}
        css_path = assets_root / "assets" / "mana" / "css" / "mana.min.css"
        if not css_path.exists():
            return glyphs, {k: tuple(v) for k, v in fallback_colors.items()}
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
                cls_name = raw_selector.split("::", 1)[0].replace(".ms-", "").lower()
                if cls_name:
                    glyphs[cls_name] = glyph_char
        for base, rgb in fallback_colors.items():
            colors.setdefault(base, rgb)
        return glyphs, colors
