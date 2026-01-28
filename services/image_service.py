"""
Image Service - Business logic for card image and bulk data management.

This module handles:
- Bulk data freshness checking
- Bulk metadata downloading
- Printing index loading
- Image cache management
"""

import threading
from collections.abc import Callable
from typing import Any

from loguru import logger

from utils.card_images import (
    BULK_DATA_CACHE,
    BulkImageDownloader,
    ensure_printing_index_cache,
    get_cache,
)


class ImageService:
    """Service for managing card image bulk data and printing indices."""

    def __init__(self):
        """Initialize the image service."""
        self.image_cache = get_cache()
        self.image_downloader: BulkImageDownloader | None = None
        self.bulk_data_by_name: dict[str, list[dict[str, Any]]] | None = None
        self.printing_index_loading: bool = False
        self._bulk_check_worker_active: bool = False

    # ============= Bulk Data Management =============

    def check_bulk_data_exists(self) -> tuple[bool, str]:
        """
        Check if bulk data exists.

        Returns:
            Tuple of (exists: bool, reason: str)
        """
        if not BULK_DATA_CACHE.exists():
            return False, "Bulk data cache not found"

        return True, "Bulk data cache exists"

    def download_bulk_metadata_async(
        self,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
        force: bool = False,
    ) -> None:
        """
        Download bulk metadata in a background thread.

        Args:
            on_success: Callback for successful download (receives success message)
            on_error: Callback for failed download (receives error message)
            force: Force download even if vendor metadata matches cache
        """
        if self.image_downloader is None:
            self.image_downloader = BulkImageDownloader(self.image_cache)

        def worker():
            try:
                success, msg = self.image_downloader.download_bulk_metadata(force=force)
                if success:
                    on_success(msg)
                else:
                    on_error(msg)
            except Exception as exc:
                logger.exception("Failed to download bulk data")
                on_error(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def ensure_data_ready(
        self,
        *,
        force_cached: bool,
        max_age_days: int,
        worker_factory: Callable[..., Any],
        set_status: Callable[[str], None],
        on_load_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_load_error: Callable[[str], None],
        on_download_success: Callable[[str], None],
        on_download_error: Callable[[str], None],
        on_check_failed: Callable[[Exception], None],
    ) -> None:
        """
        Coordinate card image bulk data lifecycle.

        Checks freshness, loads cached data, or initiates download as needed.

        Args:
            force_cached: If True, skip freshness check and use cached data only
            max_age_days: Maximum age of bulk data before triggering download
            worker_factory: Factory function to create background workers
            set_status: Callback to update status text
            on_load_success: Callback for successful bulk data load
            on_load_error: Callback for failed bulk data load
            on_download_success: Callback for successful download
            on_download_error: Callback for failed download
            on_check_failed: Callback for freshness check failure
        """
        if self._bulk_check_worker_active:
            logger.debug("Bulk data check already running")
            return

        status_msg = (
            "Loading cached card image database…"
            if force_cached
            else "Checking card image database…"
        )
        set_status(status_msg)
        self._bulk_check_worker_active = True

        def worker():
            if force_cached:
                return False, "Cached-only mode enabled"
            if self.image_downloader is None:
                self.image_downloader = BulkImageDownloader(self.image_cache)
            max_staleness = max_age_days * 86400 if max_age_days else None
            is_outdated, _metadata = self.image_downloader.is_bulk_data_outdated(
                max_staleness_seconds=max_staleness
            )
            reason = "Bulk data is outdated" if is_outdated else "Bulk data is current"
            return is_outdated, reason

        def on_success(result: tuple[bool, str]) -> None:
            self._bulk_check_worker_active = False
            needs_download, reason = result
            self._handle_check_result(
                needs_download=needs_download,
                reason=reason,
                force_cached=force_cached,
                set_status=set_status,
                on_load_success=on_load_success,
                on_load_error=on_load_error,
                on_download_success=on_download_success,
                on_download_error=on_download_error,
            )

        def on_error(exc: Exception) -> None:
            self._bulk_check_worker_active = False
            on_check_failed(exc)

        worker_factory(worker, on_success=on_success, on_error=on_error).start()

    def _handle_check_result(
        self,
        *,
        needs_download: bool,
        reason: str,
        force_cached: bool,
        set_status: Callable[[str], None],
        on_load_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_load_error: Callable[[str], None],
        on_download_success: Callable[[str], None],
        on_download_error: Callable[[str], None],
    ) -> None:
        """Handle the result of bulk data freshness check."""
        if force_cached or not needs_download:
            self._load_bulk_data(
                set_status=set_status,
                force=force_cached,
                on_success=on_load_success,
                on_error=on_load_error,
            )
            if force_cached:
                set_status("Using cached card image database")
            else:
                set_status("Card image database ready")
            return

        if not self.bulk_data_by_name:
            self._load_bulk_data(
                set_status=set_status,
                force=False,
                on_success=on_load_success,
                on_error=on_load_error,
            )

        logger.info(f"Bulk data needs update: {reason}")
        set_status("Downloading card image database...")
        self.download_bulk_metadata_async(
            on_success=on_download_success,
            on_error=on_download_error,
        )

    def _load_bulk_data(
        self,
        *,
        set_status: Callable[[str], None],
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Load bulk data from cache."""
        set_status("Preparing card printings cache…")
        started = self.load_printing_index_async(
            force=force,
            on_success=on_success,
            on_error=on_error,
        )
        if not started:
            set_status("Ready")

    def load_bulk_data_direct(
        self,
        *,
        force: bool,
        set_status: Callable[[str], None],
        on_load_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_load_error: Callable[[str], None],
    ) -> None:
        """Expose bulk data loading for fallback flows."""
        self._load_bulk_data(
            set_status=set_status,
            force=force,
            on_success=on_load_success,
            on_error=on_load_error,
        )

    # ============= Printing Index Management =============

    def load_printing_index_async(
        self,
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> bool:
        """
        Load printing index in a background thread.

        Args:
            force: Force reload even if already loading/loaded
            on_success: Callback for successful load (receives bulk_data_by_name, stats)
            on_error: Callback for failed load (receives error message)

        Returns:
            True if load was started, False if skipped
        """
        if self.printing_index_loading and not force:
            logger.debug("Printing index already loading")
            return False

        if self.bulk_data_by_name and not force:
            logger.debug("Printing index already loaded")
            return False

        self.printing_index_loading = True

        def worker():
            try:
                payload = ensure_printing_index_cache(force=force)
                data = payload.get("data", {})
                stats = {
                    "unique_names": payload.get("unique_names", len(data)),
                    "total_printings": payload.get(
                        "total_printings", sum(len(v) for v in data.values())
                    ),
                }
                on_success(data, stats)
            except Exception as exc:
                logger.exception("Failed to prepare card printings index")
                on_error(str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def set_bulk_data(self, bulk_data: dict[str, list[dict[str, Any]]]) -> None:
        """Set the bulk data reference."""
        self.bulk_data_by_name = bulk_data

    def clear_printing_index_loading(self) -> None:
        """Clear the printing index loading flag."""
        self.printing_index_loading = False

    def get_bulk_data(self) -> dict[str, list[dict[str, Any]]] | None:
        """Get the current bulk data."""
        return self.bulk_data_by_name

    def is_loading(self) -> bool:
        """Check if printing index is currently loading."""
        return self.printing_index_loading


# Global instance for backward compatibility
_default_service = None


def get_image_service() -> ImageService:
    """Get the default image service instance."""
    global _default_service
    if _default_service is None:
        _default_service = ImageService()
    return _default_service


def reset_image_service() -> None:
    """
    Reset the global image service instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_service
    _default_service = None
