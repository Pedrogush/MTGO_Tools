"""
Repositories package - Data access layer.

This package contains repository classes that handle all data persistence
and retrieval operations, isolating the UI and business logic from data
access details.

Repository classes are imported lazily via :func:`__getattr__` so that
importing the package (or any single submodule, e.g.
``repositories.deck_text_cache``) does not eagerly pull in every sibling
repository. Eager aggregation here was responsible for the
``repositories -> repositories.scrapers -> repositories`` cycle risk
flagged in #449; lazy loading keeps the package import cheap and
cycle-free. Mirrors ``services/__init__.py``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

# Public attribute -> submodule providing it.
_EXPORTS = {
    "CardRepository": "repositories.card_repository",
    "get_card_repository": "repositories.card_repository",
    "DeckRepository": "repositories.deck_repository",
    "get_deck_repository": "repositories.deck_repository",
    "DeckTextCache": "repositories.deck_text_cache",
    "get_deck_cache": "repositories.deck_text_cache",
    "FormatCardPoolRepository": "repositories.format_card_pool_repository",
    "get_format_card_pool_repository": "repositories.format_card_pool_repository",
    "MetagameRepository": "repositories.metagame_repository",
    "get_metagame_repository": "repositories.metagame_repository",
    "RadarRepository": "repositories.radar_repository",
    "get_radar_repository": "repositories.radar_repository",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value
