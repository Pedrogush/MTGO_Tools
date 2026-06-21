"""Scryfall request loop and bulk fetch.

Contains:
- :class:`BulkImageDownloader` — fetches metadata and individual card images,
  composed from three responsibility-specific mixins:

  - :class:`~services.image_service.bulk_metadata.BulkMetadataMixin` — bulk-data
    metadata lifecycle (Scryfall metadata fetch, freshness check, streamed
    atomic download).
  - :class:`~services.image_service.local_resolver.LocalResolverMixin` — local
    name -> image index plus the ``/cards/named`` and ``/cards/search`` fallbacks.
  - :class:`~services.image_service.image_writer.ImageWriterMixin` — per-face
    layout dispatch, fetch, atomic write and cache record.

- Top-level helpers used by scripts and widgets: :func:`get_cache`,
  :func:`get_card_image`, :func:`download_bulk_images`, :func:`get_cache_stats`.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from services.image_service.bulk_metadata import BulkMetadataMixin
from services.image_service.disk_cache import CardImageCache
from services.image_service.image_writer import ImageWriterMixin
from services.image_service.local_resolver import LocalResolverMixin
from services.image_service.schemas import BulkCardImage
from utils.atomic_io import locked_path
from utils.constants import (
    SCRYFALL_DOWNLOAD_PROGRESS_INTERVAL,
    SCRYFALL_MAX_DOWNLOAD_WORKERS,
)


class BulkImageDownloader(
    BulkMetadataMixin,
    LocalResolverMixin,
    ImageWriterMixin,
):
    """High-throughput bulk image downloader using Scryfall data.

    Composed from :class:`BulkMetadataMixin`, :class:`LocalResolverMixin` and
    :class:`ImageWriterMixin`. All shared instance state — ``session``,
    ``cache`` and the lazily-built local image index — is initialized here on
    the concrete class; the mixins reach it via ``self``.
    """

    def __init__(self, cache: CardImageCache, max_workers: int = SCRYFALL_MAX_DOWNLOAD_WORKERS):
        self.cache = cache
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MTGOMetagameCrawler/1.0"})
        # Lazily-built name -> [card records with image_uris] map from the
        # locally-cached bulk data. Resolving image URLs locally avoids a
        # blocking Scryfall ``/cards/named`` round-trip per uncached card.
        self._local_image_index: dict[str, list[BulkCardImage]] | None = None
        self._local_image_index_mtime: float | None = None
        self._local_image_index_lock = threading.Lock()

    def download_card_image_by_name(
        self, name: str, size: str = "normal", set_code: str | None = None
    ) -> tuple[bool, str]:
        card = self._resolve_card_locally(name, set_code=set_code)
        if card is None:
            card = self.fetch_card_by_name(name, set_code=set_code)
        return self._download_single_image(card, size)

    def download_all_images(
        self,
        size: str = "normal",
        max_cards: int | None = None,
        progress_callback: callable | None = None,
    ) -> dict[str, Any]:
        from services.image_service import schemas as _schemas

        if not _schemas.BULK_DATA_CACHE.exists():
            return {
                "success": False,
                "error": "Bulk data not downloaded. Call download_bulk_metadata() first.",
            }

        try:
            from utils.json_io import fast_load

            with locked_path(_schemas.BULK_DATA_CACHE):
                cards_data = fast_load(_schemas.BULK_DATA_CACHE)
            if max_cards:
                cards_data = cards_data[:max_cards]

            total = len(cards_data)
            completed = 0
            successful = 0
            failed = 0
            skipped = 0

            logger.info(f"Starting bulk download of {total} cards ({size} size)")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._download_single_image, card, size): card
                    for card in cards_data
                }

                for future in as_completed(futures):
                    completed += 1
                    try:
                        success, message = future.result()
                        if success:
                            if "Already cached" in message:
                                skipped += 1
                            else:
                                successful += 1
                        else:
                            failed += 1
                            logger.debug(message)
                    except Exception as exc:
                        failed += 1
                        logger.debug(f"Exception in download: {exc}")

                    # Progress callback
                    if progress_callback and completed % SCRYFALL_DOWNLOAD_PROGRESS_INTERVAL == 0:
                        progress_callback(
                            completed,
                            total,
                            f"{successful} downloaded, {skipped} cached, {failed} failed",
                        )

            logger.info(
                f"Bulk download complete: {successful} downloaded, {skipped} cached, {failed} failed"
            )

            return {
                "success": True,
                "total": total,
                "downloaded": successful,
                "skipped": skipped,
                "failed": failed,
            }

        except Exception as exc:
            logger.exception("Bulk download failed")
            return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Singleton + high-level convenience helpers
# ---------------------------------------------------------------------------

# Singleton instance
_cache_instance: CardImageCache | None = None


def get_cache() -> CardImageCache:
    """Get singleton CardImageCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CardImageCache()
    return _cache_instance


def get_card_image(card_name: str, size: str = "normal") -> Path | None:
    """Get card image from cache."""
    cache = get_cache()
    return cache.get_image_path(card_name, size)


def download_bulk_images(
    size: str = "normal", max_cards: int | None = None, progress_callback: callable | None = None
) -> dict[str, Any]:
    """High-level function to download all card images."""
    cache = get_cache()
    downloader = BulkImageDownloader(cache)

    # Download metadata first
    success, msg = downloader.download_bulk_metadata()
    if not success:
        return {"success": False, "error": msg}

    # Download images
    return downloader.download_all_images(size, max_cards, progress_callback)


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    cache = get_cache()
    return cache.get_cache_stats()


__all__ = [
    "BulkImageDownloader",
    "download_bulk_images",
    "get_cache",
    "get_cache_stats",
    "get_card_image",
]
