"""
Services package - Business logic layer.

This package contains service classes that handle all business logic,
orchestrating between repositories and the UI layer.

Service classes are imported lazily via :func:`__getattr__` so that importing
the package (or any single submodule, e.g. ``services.card_data_service``)
does not eagerly pull in every sibling service. Eager imports here created a
``repositories.card_repository -> services -> services.search_service ->
repositories.card_repository`` import cycle; lazy loading keeps the package
import cheap and cycle-free. Mirrors ``widgets/panels/__init__.py``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

# Public attribute -> submodule providing it.
_EXPORTS = {
    "CollectionService": "services.collection_service",
    "CollectionStatus": "services.collection_service",
    "get_collection_service": "services.collection_service",
    "BundleSnapshotClient": "services.bundle_snapshot_client",
    "BundleSnapshotError": "services.bundle_snapshot_client",
    "get_bundle_snapshot_client": "services.bundle_snapshot_client",
    "reset_bundle_snapshot_client": "services.bundle_snapshot_client",
    "DeckService": "services.deck_service",
    "ZoneUpdateResult": "services.deck_service",
    "get_deck_service": "services.deck_service",
    "FormatCardPoolService": "services.format_card_pool_service",
    "get_format_card_pool_service": "services.format_card_pool_service",
    "ImageService": "services.image_service",
    "get_image_service": "services.image_service",
    "MetagameService": "services.metagame_service",
    "get_metagame_service": "services.metagame_service",
    "reset_metagame_service": "services.metagame_service",
    "SearchService": "services.search_service",
    "get_search_service": "services.search_service",
    "StoreService": "services.store_service",
    "get_store_service": "services.store_service",
}

# Names that must degrade gracefully if their (wx-bound) submodule fails to
# import, preserving the previous defensive behaviour for CollectionService.
_COLLECTION_NAMES = {"CollectionService", "CollectionStatus", "get_collection_service"}

__all__ = sorted(_EXPORTS)


def _collection_fallback(name: str) -> Any:
    if name == "get_collection_service":

        def get_collection_service():
            raise RuntimeError("CollectionService is unavailable (wxPython not installed)")

        return get_collection_service
    return None


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        value = getattr(import_module(module_name), name)
    except Exception:
        if name in _COLLECTION_NAMES:  # defensive: broken wx UI import chain
            value = _collection_fallback(name)
        else:
            raise
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value
