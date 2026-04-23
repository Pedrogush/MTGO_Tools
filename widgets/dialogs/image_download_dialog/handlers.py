"""Download worker and progress handlers for the image download dialog."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import wx
from loguru import logger

from utils.card_images import BULK_DATA_CACHE, BulkImageDownloader


class ImageDownloadDialogHandlersMixin:
    """Threaded download worker and progress/completion handlers."""

    image_cache: Any
    image_downloader: BulkImageDownloader | None
    on_status_update: Callable[[str], None] | None

    def start_download(self, quality: str, max_cards: int | None) -> None:
        # Create progress dialog
        max_value = max_cards if max_cards else 80000
        progress_dialog = wx.ProgressDialog(
            "Downloading Card Images",
            "Preparing download...",
            maximum=max_value,
            parent=self.GetParent(),
            style=wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME,
        )

        # Track cancellation
        download_cancelled = [False]

        def progress_callback(completed: int, total: int, message: str):
            wx.CallAfter(
                self._update_progress,
                progress_dialog,
                completed,
                total,
                message,
                download_cancelled,
            )

        def worker():
            try:
                # Ensure downloader exists
                if self.image_downloader is None:
                    self.image_downloader = BulkImageDownloader(self.image_cache)

                # Ensure bulk data is downloaded
                if not BULK_DATA_CACHE.exists():
                    wx.CallAfter(progress_dialog.Update, 0, "Downloading bulk metadata first...")
                    success, msg = self.image_downloader.download_bulk_metadata(force=False)
                    if not success:
                        wx.CallAfter(
                            self._on_download_failed,
                            progress_dialog,
                            f"Failed to download metadata: {msg}",
                        )
                        return

                # Download images
                result = self.image_downloader.download_all_images(
                    size=quality, max_cards=max_cards, progress_callback=progress_callback
                )

                # Check if cancelled
                if download_cancelled[0]:
                    wx.CallAfter(self._on_download_cancelled, progress_dialog)
                elif result.get("success"):
                    wx.CallAfter(self._on_download_complete, progress_dialog, result)
                else:
                    wx.CallAfter(
                        self._on_download_failed,
                        progress_dialog,
                        result.get("error", "Unknown error"),
                    )

            except Exception as exc:
                logger.exception("Image download failed")
                wx.CallAfter(self._on_download_failed, progress_dialog, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(
        self,
        dialog: wx.ProgressDialog,
        completed: int,
        total: int,
        message: str,
        cancelled_flag: list,
    ):
        if not dialog:
            return

        try:
            # Check if dialog still exists
            _ = dialog.GetTitle()
        except RuntimeError:
            # Dialog was destroyed
            cancelled_flag[0] = True
            return

        # Ensure the dialog range matches the total
        if total:
            try:
                dialog.SetRange(max(total, 1))
            except Exception as exc:
                logger.debug("Failed to update progress dialog range: %s", exc)

        # Clamp the reported completed count to the dialog range
        try:
            current_range = dialog.GetRange()
        except Exception:
            current_range = None

        value = completed
        if current_range and current_range > 0:
            value = min(completed, current_range)

        # Update progress
        continue_download, skip = dialog.Update(value, message)
        if not continue_download:
            # User clicked cancel
            cancelled_flag[0] = True
            dialog.Destroy()

    def _on_download_complete(self, dialog: wx.ProgressDialog, result: dict[str, Any]):
        try:
            dialog.Destroy()
        except RuntimeError:
            pass
        if self.on_status_update:
            self.on_status_update("app.status.image_download_complete")

    def _on_download_failed(self, dialog: wx.ProgressDialog, error_msg: str):
        try:
            dialog.Destroy()
        except RuntimeError:
            pass

        wx.MessageBox(f"Download failed: {error_msg}", "Download Error", wx.OK | wx.ICON_ERROR)

        if self.on_status_update:
            self.on_status_update("app.status.ready")

    def _on_download_cancelled(self, dialog: wx.ProgressDialog):
        try:
            dialog.Destroy()
        except RuntimeError:
            pass

        if self.on_status_update:
            self.on_status_update("app.status.image_download_cancelled")
