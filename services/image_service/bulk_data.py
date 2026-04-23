"""Bulk data freshness checks and metadata downloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from utils.card_images import BULK_DATA_CACHE
from utils.card_images_workers import download_bulk_metadata_worker


class BulkDataMixin:
    """Bulk data freshness + download handling."""

    def check_bulk_data_exists(self) -> tuple[bool, str]:
        if not BULK_DATA_CACHE.exists():
            return False, "Bulk data cache not found"

        return True, "Bulk data cache exists"

    def download_bulk_metadata_async(
        self,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
        force: bool = False,
    ) -> None:
        if self._bulk_download_handle and self._bulk_download_handle.process.is_alive():
            logger.debug("Bulk data download already running")
            return

        def _on_success(result: dict[str, Any]) -> None:
            msg = result.get("message", "Bulk data downloaded")
            on_success(msg)

        def _on_error(msg: str) -> None:
            on_error(msg)

        try:
            self._bulk_download_handle = self._process_worker.run_async(
                target=download_bulk_metadata_worker,
                args=(),
                kwargs={
                    "cache_dir": str(self.image_cache.cache_dir),
                    "db_path": str(self.image_cache.db_path),
                    "force": force,
                },
                on_success=_on_success,
                on_error=_on_error,
                call_after=self._call_after,
            )
        except Exception as exc:
            logger.exception("Failed to start bulk metadata process")
            on_error(str(exc))
