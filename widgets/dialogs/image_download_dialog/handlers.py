"""Download worker and progress handlers for the image download dialog."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

if TYPE_CHECKING:
    from services.image_service import BulkImageDownloader


class ImageDownloadDialogHandlersMixin:
    """Threaded download worker that reports progress to the status bar."""

    image_cache: Any
    image_downloader: BulkImageDownloader
    bulk_data_cache_path: Path
    on_status_update: Callable[..., None] | None

    def start_download(self, quality: str, max_cards: int | None) -> None:
        # No blocking progress dialog: progress is reported to the main
        # application status bar so the rest of the UI stays usable.
        self._report_status("app.status.image_download_starting")

        def progress_callback(completed: int, total: int, message: str):
            wx.CallAfter(
                self._report_status,
                "app.status.image_download_progress",
                completed=completed,
                total=total,
                details=message,
            )

        def worker():
            try:
                # Ensure bulk data is downloaded
                if not self.bulk_data_cache_path.exists():
                    wx.CallAfter(self._report_status, "app.status.image_download_metadata")
                    success, msg = self.image_downloader.download_bulk_metadata(force=False)
                    if not success:
                        wx.CallAfter(
                            self._on_download_failed, f"Failed to download metadata: {msg}"
                        )
                        return

                # Download images
                result = self.image_downloader.download_all_images(
                    size=quality, max_cards=max_cards, progress_callback=progress_callback
                )

                if result.get("success"):
                    wx.CallAfter(self._on_download_complete, result)
                else:
                    wx.CallAfter(
                        self._on_download_failed,
                        result.get("error", "Unknown error"),
                    )

            except Exception as exc:
                logger.exception("Image download failed")
                wx.CallAfter(self._on_download_failed, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _report_status(self, key: str, **kwargs: object) -> None:
        if not self.on_status_update:
            return
        try:
            self.on_status_update(key, **kwargs)
        except TypeError:
            # Older callbacks that accept a single positional arg only.
            self.on_status_update(key)

    def _on_download_complete(self, result: dict[str, Any]):
        self._report_status("app.status.image_download_complete")

    def _on_download_failed(self, error_msg: str):
        wx.MessageBox(f"Download failed: {error_msg}", "Download Error", wx.OK | wx.ICON_ERROR)
        self._report_status("app.status.ready")
