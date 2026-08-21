"""Bulk data freshness checks and metadata downloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.image_service.downloader import BulkImageDownloader
from services.image_service.workers import download_bulk_metadata_worker

if TYPE_CHECKING:
    from services.image_service.protocol import ImageServiceProto

    _Base = ImageServiceProto
else:
    _Base = object


class BulkDataMixin(_Base):
    """Bulk data freshness + download handling."""

    def seed_image_cache_if_needed(self) -> list[str]:
        """Decompress the installer-bundled bulk snapshot on first run.

        Returns the names of any files written. Runs before the existence check
        so a fresh install finds the bulk data already present and skips the
        cold-start download entirely. Safe to call every startup; it's a no-op
        once the cache is populated.
        """
        from services.image_service.seed import seed_image_cache_if_needed

        return [path.name for path in seed_image_cache_if_needed()]

    def check_bulk_data_exists(self) -> tuple[bool, str]:
        from services.image_service import schemas as _schemas

        if not _schemas.BULK_DATA_CACHE.exists():
            return False, "Bulk data cache not found"

        return True, "Bulk data cache exists"

    def is_bulk_data_stale(self) -> tuple[bool, str]:
        """Whether a newer bulk file should be fetched over the cached one.

        Separate from :meth:`check_bulk_data_exists` on purpose: a *missing*
        cache has to block until the download lands, while a *stale* one is
        perfectly usable and should be shown immediately and replaced in the
        background. Nothing called the freshness check at all before, so an
        install only ever saw the bulk data it downloaded on its first run —
        cards from every set released since had no printings, no editions, and
        no art pager (issue #986 follow-up).

        Answers ``False`` when the check itself cannot be made (offline,
        Scryfall down): the cached file is what we have either way, and a
        download started on a guess would only fail.
        """
        downloader = self.image_downloader or BulkImageDownloader(self.image_cache)
        try:
            outdated, _metadata = downloader.is_bulk_data_outdated()
        except Exception as exc:
            logger.debug(f"Bulk data freshness check failed: {exc}")
            return False, f"Freshness check unavailable: {exc}"
        if outdated:
            return True, "A newer Scryfall bulk file is available"
        return False, "Bulk data is current"

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
