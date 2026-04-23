"""Image Service package - Business logic for card image and bulk data management.

Split by responsibility into internal modules:

- ``bulk_data``: bulk data freshness checks and metadata downloads
- ``printing_index``: printing index loading and state
- ``metadata``: on-demand printings metadata lookups
- ``cache``: download queue orchestration and UI callbacks
- ``download_queue``: background card-image download queue helper
- ``service``: :class:`ImageService` assembled from the above mixins
"""

from __future__ import annotations

# ``time`` is re-exported so legacy tests that monkeypatch ``image_service.time``
# (e.g. ``monkeypatch.setattr(image_service.time, "sleep", ...)``) keep working
# after the module became a package.
import time  # noqa: F401

from services.image_service.download_queue import CardImageDownloadQueue
from services.image_service.service import ImageService

# Global instance for backward compatibility
_default_service: ImageService | None = None


def get_image_service() -> ImageService:
    """Get the default image service instance."""
    global _default_service
    if _default_service is None:
        _default_service = ImageService()
    return _default_service


def reset_image_service() -> None:
    """Reset the global image service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "CardImageDownloadQueue",
    "ImageService",
    "get_image_service",
    "reset_image_service",
]
