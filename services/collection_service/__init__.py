"""Collection Service package - Business logic for collection/inventory management.

Split by responsibility into internal modules:

- ``cache``: cache file discovery and collection loading (+ :class:`CollectionStatus`)
- ``parsing``: normalizing card lists into ``name -> quantity`` inventories
- ``ownership``: owned-count lookups and owned-status formatting
- ``deck_analysis``: deck-vs-inventory comparisons (missing cards etc.)
- ``stats``: aggregate collection statistics
- ``bridge_refresh``: async refresh from the MTGO bridge
- ``exporter``: JSON export helpers
- ``service``: :class:`CollectionService` assembled from the above mixins
"""

from __future__ import annotations

from services.collection_service.cache import CollectionStatus
from services.collection_service.service import CollectionService

# Global instance for backward compatibility
_default_service: CollectionService | None = None


def get_collection_service() -> CollectionService:
    global _default_service
    if _default_service is None:
        _default_service = CollectionService()
    return _default_service


def reset_collection_service() -> None:
    """Reset the global collection service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "CollectionService",
    "CollectionStatus",
    "get_collection_service",
    "reset_collection_service",
]
