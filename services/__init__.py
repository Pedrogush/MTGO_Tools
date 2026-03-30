"""
Services package - Business logic layer.

This package contains service classes that handle all business logic,
orchestrating between repositories and the UI layer.
"""

try:  # wxPython may be missing in headless environments
    from services.collection_service import (
        CollectionService,
        CollectionStatus,
        get_collection_service,
    )
except Exception:  # pragma: no cover - collection service not available without wx
    CollectionService = None
    CollectionStatus = None

    def get_collection_service():
        raise RuntimeError("CollectionService is unavailable (wxPython not installed)")


from services.bundle_snapshot_client import (
    BundleSnapshotClient,
    BundleSnapshotError,
    get_bundle_snapshot_client,
    reset_bundle_snapshot_client,
)
from services.deck_service import DeckService, ZoneUpdateResult, get_deck_service
from services.format_card_pool_service import (
    FormatCardPoolService,
    get_format_card_pool_service,
)
from services.image_service import ImageService, get_image_service
from services.search_service import SearchService, get_search_service
from services.store_service import StoreService, get_store_service

__all__ = [
    "BundleSnapshotClient",
    "BundleSnapshotError",
    "CollectionService",
    "CollectionStatus",
    "DeckService",
    "FormatCardPoolService",
    "ImageService",
    "SearchService",
    "StoreService",
    "ZoneUpdateResult",
    "get_bundle_snapshot_client",
    "get_collection_service",
    "get_deck_service",
    "get_format_card_pool_service",
    "get_image_service",
    "get_search_service",
    "get_store_service",
    "reset_bundle_snapshot_client",
]
