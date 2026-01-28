"""Coordinator for bulk card image data flows."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from utils.background_worker import BackgroundWorker
    from widgets.app_frame import AppFrame


class BulkDataHelpers:
    def __init__(
        self,
        *,
        image_service: Any,
        worker: BackgroundWorker,
        frame_provider: Callable[[], AppFrame | None],
    ) -> None:
        self._image_service = image_service
        self._worker = worker
        self._frame_provider = frame_provider
        self._bulk_check_worker_active = False

    def check_and_download_bulk_data(self, callbacks: dict[str, Callable[..., Any]]) -> None:
        if self._bulk_check_worker_active:
            logger.debug("Bulk data check already running")
            return

        on_status = callbacks.get("on_status", lambda msg: None)
        on_download_needed = callbacks.get("on_bulk_download_needed", lambda reason: None)
        on_download_complete = callbacks.get("on_bulk_download_complete", lambda msg: None)
        on_download_failed = callbacks.get("on_bulk_download_failed", lambda msg: None)

        on_status("Checking card image database…")
        self._bulk_check_worker_active = True

        def worker():
            return self._image_service.check_bulk_data_exists()

        def success_handler(result: tuple[bool, str]):
            self._bulk_check_worker_active = False
            exists, reason = result

            if exists:
                self.load_bulk_data_into_memory(on_status)
                on_status("Card image database ready")
                return

            logger.info(f"Bulk data needs download: {reason}")
            on_download_needed(reason)
            on_status("Downloading card image database...")

            def _on_download_complete(msg: str) -> None:
                on_download_complete(msg)
                self.load_bulk_data_into_memory(on_status, force=True)

            def _on_download_failed(msg: str) -> None:
                on_download_failed(msg)
                on_status("Ready")

            self._image_service.download_bulk_metadata_async(
                on_success=_on_download_complete,
                on_error=_on_download_failed,
            )

        def error_handler(exc: Exception):
            self._bulk_check_worker_active = False
            logger.warning(f"Failed to check bulk data existence: {exc}")
            if not self._image_service.get_bulk_data():
                self.load_bulk_data_into_memory(on_status)
            else:
                on_status("Ready")

        self._worker.submit(worker, on_success=success_handler, on_error=error_handler)

    def load_bulk_data_into_memory(
        self, on_status: Callable[[str], None], force: bool = False
    ) -> None:
        on_status("Preparing card printings cache…")

        def success_callback(data, stats):
            import wx

            # Persist bulk data and notify UI
            self._image_service.set_bulk_data(data)
            frame = self._frame_provider()
            if frame:
                wx.CallAfter(frame._on_bulk_data_loaded, data, stats)

        def error_callback(msg):
            import wx

            logger.warning(f"Bulk data load issue: {msg}")
            frame = self._frame_provider()
            if frame:
                wx.CallAfter(frame._on_bulk_data_load_failed, msg)

        started = self._image_service.load_printing_index_async(
            force=force,
            on_success=success_callback,
            on_error=error_callback,
        )

        if not started:
            on_status("Ready")

    def force_bulk_data_update(self, callbacks: dict[str, Callable[..., Any]]) -> None:
        """Force download of bulk data regardless of current state."""
        if self._bulk_check_worker_active:
            logger.debug("Bulk data update already running")
            return

        on_status = callbacks.get("on_status", lambda msg: None)
        on_download_complete = callbacks.get("on_bulk_download_complete", lambda msg: None)
        on_download_failed = callbacks.get("on_bulk_download_failed", lambda msg: None)

        on_status("Downloading card image database...")
        self._bulk_check_worker_active = True

        def _on_download_complete(msg: str) -> None:
            self._bulk_check_worker_active = False
            on_download_complete(msg)
            self.load_bulk_data_into_memory(on_status, force=True)

        def _on_download_failed(msg: str) -> None:
            self._bulk_check_worker_active = False
            on_download_failed(msg)
            on_status("Ready")

        self._image_service.download_bulk_metadata_async(
            on_success=_on_download_complete,
            on_error=_on_download_failed,
            force=True,
        )
