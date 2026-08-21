"""Bulk card-image data: existence check, download, and in-memory preparation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto

    _Base = AppControllerProto
else:
    _Base = object


class BulkDataMixin(_Base):
    """Check/download the Scryfall bulk data and feed it into the printing index."""

    def check_and_download_bulk_data(self) -> None:
        if self._bulk_check_worker_active:
            logger.debug("Bulk data check already running")
            return

        callbacks = self._ui_callbacks
        on_status = callbacks.on_status if callbacks else lambda msg: None
        on_download_needed = callbacks.on_bulk_download_needed if callbacks else lambda reason: None
        on_download_complete = (
            callbacks.on_bulk_download_complete if callbacks else lambda msg: None
        )
        on_download_failed = callbacks.on_bulk_download_failed if callbacks else lambda msg: None

        on_status("bulk.status.checking")
        self._bulk_check_worker_active = True

        def worker():
            # First run: decompress the installer-bundled bulk snapshot (if any)
            # before checking, so a fresh install starts warm instead of racing
            # a cold download. No-op once the cache is populated.
            self.image_service.seed_image_cache_if_needed()
            return self.image_service.check_bulk_data_exists()

        def success_handler(result: tuple[bool, str]):
            self._bulk_check_worker_active = False
            exists, reason = result

            if exists:
                self.load_bulk_data_into_memory(on_status)
                on_status("bulk.status.ready")
                # Show what we have now, then quietly pick up anything Scryfall
                # has published since. A stale cache is usable; a missing one
                # is not, which is why only this branch refreshes in the
                # background instead of blocking on the download.
                self._refresh_bulk_data_if_stale(on_status, on_download_complete)
                return

            logger.info(f"Bulk data needs download: {reason}")
            on_download_needed(reason)
            on_status("bulk.status.downloading")

            def _on_download_complete(msg: str) -> None:
                on_download_complete(msg)
                self.load_bulk_data_into_memory(on_status, force=True)
                # The local index now exists: re-attempt any images that failed
                # while it was still downloading (cold-start self-heal).
                self.image_service.retry_failed_image_downloads()

            def _on_download_failed(msg: str) -> None:
                on_download_failed(msg)
                on_status("app.status.ready")

            self.image_service.download_bulk_metadata_async(
                on_success=_on_download_complete,
                on_error=_on_download_failed,
            )

        def error_handler(exc: Exception):
            self._bulk_check_worker_active = False
            logger.warning(f"Failed to check bulk data existence: {exc}")
            if not self.image_service.get_bulk_data():
                self.load_bulk_data_into_memory(on_status)
            else:
                on_status("app.status.ready")

        self._worker.submit(worker, on_success=success_handler, on_error=error_handler)

    def _refresh_bulk_data_if_stale(
        self,
        on_status: Callable[[str], None],
        on_download_complete: Callable[[str], None],
    ) -> None:
        """Replace a stale bulk cache in the background, on a worker thread.

        The freshness check is one small HTTP request but it is still network
        I/O, so it runs off the UI thread; the download it may trigger is a
        separate process (``download_bulk_metadata_async``) that already
        refuses to start a second copy of itself. Any failure is swallowed —
        the app is fully usable on the cache it just loaded.
        """

        def worker() -> tuple[bool, str]:
            return self.image_service.is_bulk_data_stale()

        def on_checked(result: tuple[bool, str]) -> None:
            stale, reason = result
            if not stale:
                logger.debug(f"Bulk data refresh not needed: {reason}")
                return
            logger.info(f"Refreshing bulk data in the background: {reason}")

            def _complete(msg: str) -> None:
                on_download_complete(msg)
                # Rebuild the printing index from the new file, then re-attempt
                # the images that failed against the old one — that is what
                # makes a newly-released set's cards get their printings, their
                # editions and their art without a restart.
                self.load_bulk_data_into_memory(on_status, force=True)
                self.image_service.retry_failed_image_downloads()

            def _failed(msg: str) -> None:
                logger.warning(f"Background bulk data refresh failed: {msg}")

            self.image_service.download_bulk_metadata_async(
                on_success=_complete,
                on_error=_failed,
            )

        def on_check_failed(exc: Exception) -> None:
            logger.debug(f"Bulk data freshness check failed: {exc}")

        self._worker.submit(worker, on_success=on_checked, on_error=on_check_failed)

    def load_bulk_data_into_memory(
        self, on_status: Callable[[str], None], force: bool = False
    ) -> None:
        on_status("bulk.status.preparing_cache")

        def success_callback(data, stats):
            import wx

            self.image_service.set_bulk_data(data)
            if self.frame:
                wx.CallAfter(self.frame._on_bulk_data_loaded, data, stats)

        def error_callback(msg):
            import wx

            logger.warning(f"Bulk data load issue: {msg}")
            if self.frame:
                wx.CallAfter(self.frame._on_bulk_data_load_failed, msg)

        started = self.image_service.load_printing_index_async(
            force=force,
            on_success=success_callback,
            on_error=error_callback,
        )

        if not started:
            on_status("app.status.ready")

    def force_bulk_data_update(self) -> None:
        if self._bulk_check_worker_active:
            logger.debug("Bulk data update already running")
            return

        callbacks = self._ui_callbacks
        on_status = callbacks.on_status if callbacks else lambda msg: None
        on_download_complete = (
            callbacks.on_bulk_download_complete if callbacks else lambda msg: None
        )
        on_download_failed = callbacks.on_bulk_download_failed if callbacks else lambda msg: None

        on_status("bulk.status.downloading")
        self._bulk_check_worker_active = True

        def _on_download_complete(msg: str) -> None:
            self._bulk_check_worker_active = False
            on_download_complete(msg)
            self.load_bulk_data_into_memory(on_status, force=True)
            # Re-attempt any images that failed against the per-card API while
            # the freshly-downloaded index was unavailable (cold-start self-heal).
            self.image_service.retry_failed_image_downloads()

        def _on_download_failed(msg: str) -> None:
            self._bulk_check_worker_active = False
            on_download_failed(msg)
            on_status("app.status.ready")

        self.image_service.download_bulk_metadata_async(
            on_success=_on_download_complete,
            on_error=_on_download_failed,
            force=True,
        )
