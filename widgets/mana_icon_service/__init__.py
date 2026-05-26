"""Mana Icon Service package - wx bitmap rendering for MTG mana symbols.

Split by responsibility into internal modules:

- ``resources``: :class:`ManaIconResources` (CSS/font asset loader)
- ``cache``: :class:`ManaBitmapCache` (bitmap + PNG cache state)
- ``bitmap_renderer``: :class:`BitmapRendererMixin` (solid-background wx drawing)
- ``svg_renderer``: :class:`SvgRendererMixin` (transparent-PNG SVG rasterizer)
- ``factory``: :class:`ManaIconFactory` public API + cost-string helpers
- ``protocol``: :class:`ManaIconFactoryProto` (cross-mixin ``self`` contract)
"""

from __future__ import annotations

from widgets.mana_icon_service.factory import (
    ManaIconFactory,
    normalize_mana_query,
    tokenize_mana_symbols,
    type_global_mana_symbol,
)
from widgets.mana_icon_service.protocol import ManaIconFactoryProto
from widgets.mana_icon_service.resources import ManaIconResources

__all__ = [
    "ManaIconFactory",
    "ManaIconFactoryProto",
    "ManaIconResources",
    "normalize_mana_query",
    "tokenize_mana_symbols",
    "type_global_mana_symbol",
]
