"""Shared ``self`` contract that the :class:`ManaIconFactory` mixins assume.

:class:`ManaIconFactory` composes :class:`BitmapRendererMixin` (solid-background
bitmap rendering) and :class:`SvgRendererMixin` (transparent-PNG rendering via
vendored SVG glyphs). This Protocol captures the cross-mixin attributes each
expects on ``self``, so type checkers see a single coherent surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import wx
import wx.svg

from services.mana_icon_service.cache import ManaBitmapCache


class ManaIconFactoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``ManaIconFactory``."""

    # Shared resource state owned by the composing class.
    _cache: ManaBitmapCache
    _icon_size: int
    _glyph_map: dict[str, str]
    _color_map: dict[str, tuple[int, int, int]]

    # SVG-renderer-only state.
    _svg_color_map: dict[str, tuple[int, int, int]]
    _svg_cache: dict[str, "wx.svg.SVGimage | None"]
    _png_cache: dict[tuple[str, int], Path]
    _rasterizer_cache_dir: Path | None

    def _assets_root(self) -> Path: ...
