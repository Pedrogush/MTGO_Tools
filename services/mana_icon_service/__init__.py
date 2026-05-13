"""Mana Icon Service package - wx bitmap rendering for MTG mana symbols.

Split by responsibility into internal modules:

- ``resources``: :class:`ManaIconResources` (CSS/font asset loader)
- ``cache``: :class:`ManaBitmapCache` (bitmap + PNG cache state)
- ``bitmap_renderer``: :class:`BitmapRendererMixin` (wx drawing primitives)
- ``factory``: :class:`ManaIconFactory` public API + cost-string helpers
"""

from __future__ import annotations

from services.mana_icon_service.factory import (
    ManaIconFactory,
    normalize_mana_query,
    tokenize_mana_symbols,
    type_global_mana_symbol,
)
from services.mana_icon_service.resources import ManaIconResources

__all__ = [
    "ManaIconFactory",
    "ManaIconResources",
    "normalize_mana_query",
    "tokenize_mana_symbols",
    "type_global_mana_symbol",
]
