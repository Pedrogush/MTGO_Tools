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
from services.deck_research_service import DeckResearchService
from services.deck_service import DeckService, ZoneUpdateResult, get_deck_service
from services.image_service import ImageService, get_image_service
from services.search_service import SearchService, get_search_service
from services.state_service import StateService
from services.store_service import StoreService, get_store_service

__all__ = [
    "BundleSnapshotClient",
    "BundleSnapshotError",
    "CollectionService",
    "CollectionStatus",
    "DeckResearchService",
    "DeckService",
    "ImageService",
    "SearchService",
    "StateService",
    "StoreService",
    "ZoneUpdateResult",
    "get_bundle_snapshot_client",
    "get_collection_service",
    "get_deck_research_service",
    "get_deck_service",
    "get_image_service",
    "get_search_service",
    "get_state_service",
    "get_store_service",
    "reset_bundle_snapshot_client",
]


def get_deck_research_service() -> DeckResearchService:
    return DeckResearchService()


def get_state_service() -> StateService:
    return StateService()
