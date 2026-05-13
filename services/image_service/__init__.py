"""Image Service package - Business logic for card image and bulk data management.

Split by responsibility into internal modules:

- ``schemas``: constants, msgspec decoders, :class:`CardImageRequest`
- ``path_resolver``: stored-path normalization helpers
- ``disk_cache``: :class:`CardImageCache` (SQLite + filesystem)
- ``downloader``: :class:`BulkImageDownloader` + high-level convenience helpers
- ``bulk_data``: bulk data freshness checks and metadata downloads (mixin)
- ``printing_index``: printing index build/load functions + mixin
- ``metadata``: on-demand printings metadata lookups (mixin)
- ``cache``: download queue orchestration and UI callbacks (mixin)
- ``download_queue``: background card-image download queue helper
- ``workers``: subprocess worker entry points
- ``process_worker``: subprocess runner
- ``service``: :class:`ImageService` assembled from the above mixins
"""

from __future__ import annotations

# ``time`` is re-exported so legacy tests that monkeypatch ``image_service.time``
# (e.g. ``monkeypatch.setattr(image_service.time, "sleep", ...)``) keep working
# after the module became a package.
import time  # noqa: F401

from services.image_service.disk_cache import CardImageCache
from services.image_service.download_queue import CardImageDownloadQueue
from services.image_service.downloader import (
    BulkImageDownloader,
    download_bulk_images,
    get_cache,
    get_cache_stats,
    get_card_image,
)
from services.image_service.printing_index import (
    build_printing_index,
    ensure_printing_index_cache,
    load_printing_index_payload,
)
from services.image_service.schemas import (
    BULK_DATA_CACHE,
    IMAGE_CACHE_DIR,
    IMAGE_DB_PATH,
    PRINTING_INDEX_CACHE,
    PRINTING_INDEX_VERSION,
    CardImageRequest,
)
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
    "BULK_DATA_CACHE",
    "BulkImageDownloader",
    "CardImageCache",
    "CardImageDownloadQueue",
    "CardImageRequest",
    "IMAGE_CACHE_DIR",
    "IMAGE_DB_PATH",
    "ImageService",
    "PRINTING_INDEX_CACHE",
    "PRINTING_INDEX_VERSION",
    "build_printing_index",
    "download_bulk_images",
    "ensure_printing_index_cache",
    "get_cache",
    "get_cache_stats",
    "get_card_image",
    "get_image_service",
    "load_printing_index_payload",
    "reset_image_service",
]
