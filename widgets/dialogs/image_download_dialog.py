"""Dialog for downloading card images from Scryfall with progress tracking."""

import threading
from collections.abc import Callable
from typing import Any

import wx
from loguru import logger

from utils.card_images import BULK_DATA_CACHE, BulkImageDownloader
from utils.constants import DARK_BG, LIGHT_TEXT, SUBDUED_TEXT


class ImageDownloadDialog(wx.Dialog):
    """Dialog for configuring and executing bulk card image downloads."""

    QUALITY_OPTIONS = [
        "Small (146x204, ~100KB/card, ~8GB total)",
        "Normal (488x680, ~300KB/card, ~25GB total)",
        "Large (672x936, ~500KB/card, ~40GB total)",
        "PNG (745x1040, ~700KB/card, ~55GB total)",
    ]

    AMOUNT_OPTIONS = [
        "Test mode (first 100 cards)",
        "First 1,000 cards",
        "First 5,000 cards",
        "First 10,000 cards",
        "All cards (~80,000+)",
    ]

    def __init__(
        self,
        parent: wx.Window,
        image_cache: Any,
        image_downloader: BulkImageDownloader | None,
        on_status_update: Callable[[str], None] | None = None,
    ):
        super().__init__(parent, title="Download Card Images", size=(450, 320))
        self.SetBackgroundColour(DARK_BG)

        self.image_cache = image_cache
        self.image_downloader = image_downloader
        self.on_status_update = on_status_update

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Title
        title = wx.StaticText(panel, label="Download Card Images from Scryfall")
        title.SetForegroundColour(LIGHT_TEXT)
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Image quality selection
        quality_label = wx.StaticText(panel, label="Image Quality:")
        quality_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(quality_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.quality_choice = wx.Choice(panel, choices=self.QUALITY_OPTIONS)
        self.quality_choice.SetSelection(1)  # Default to Normal
        sizer.Add(self.quality_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Download amount selection
        amount_label = wx.StaticText(panel, label="Download Amount:")
        amount_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(amount_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.amount_choice = wx.Choice(panel, choices=self.AMOUNT_OPTIONS)
        self.amount_choice.SetSelection(0)  # Default to Test mode
        sizer.Add(self.amount_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Info text
        info_text = wx.StaticText(
            panel,
            label=(
                "Note: Images are downloaded from Scryfall's CDN (no rate limits).\n"
                "This may take 30-60 minutes for all cards depending on your connection.\n"
                "You can use the app while downloading."
            ),
        )
        info_text.SetForegroundColour(SUBDUED_TEXT)
        info_text.Wrap(420)
        sizer.Add(info_text, 0, wx.ALL, 10)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer(1)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Cancel")
        button_sizer.Add(cancel_btn, 0, wx.RIGHT, 6)

        download_btn = wx.Button(panel, wx.ID_OK, label="Download")
        download_btn.SetDefault()
        button_sizer.Add(download_btn, 0)

        sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizerAndFit(sizer)
        self.SetClientSize(panel.GetBestSize())
        self.Centre()

    def get_selected_options(self) -> tuple[str, int | None]:
        """Get the user-selected quality and download amount."""
        quality_map = {0: "small", 1: "normal", 2: "large", 3: "png"}
        quality = quality_map[self.quality_choice.GetSelection()]

        amount_map = {0: 100, 1: 1000, 2: 5000, 3: 10000, 4: None}
        max_cards = amount_map[self.amount_choice.GetSelection()]

        return quality, max_cards

    def start_download(self, quality: str, max_cards: int | None) -> None:
        """Start the image download process with a progress dialog."""
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
            """Update progress dialog from worker thread."""
            wx.CallAfter(
                self._update_progress,
                progress_dialog,
                completed,
                total,
                message,
                download_cancelled,
            )

        def worker():
            """Background download worker."""
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
        """Update progress dialog (called from main thread via wx.CallAfter)."""
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
        """Handle successful image download."""
        try:
            dialog.Destroy()
        except RuntimeError:
            pass
        if self.on_status_update:
            self.on_status_update("app.status.image_download_complete")

    def _on_download_failed(self, dialog: wx.ProgressDialog, error_msg: str):
        """Handle image download failure."""
        try:
            dialog.Destroy()
        except RuntimeError:
            pass

        wx.MessageBox(f"Download failed: {error_msg}", "Download Error", wx.OK | wx.ICON_ERROR)

        if self.on_status_update:
            self.on_status_update("app.status.ready")

    def _on_download_cancelled(self, dialog: wx.ProgressDialog):
        """Handle image download cancellation."""
        try:
            dialog.Destroy()
        except RuntimeError:
            pass

        if self.on_status_update:
            self.on_status_update("app.status.image_download_cancelled")


def show_image_download_dialog(
    parent: wx.Window,
    image_cache: Any,
    image_downloader: BulkImageDownloader | None,
    on_status_update: Callable[[str], None] | None = None,
) -> None:
    """
    Show the image download dialog and start download if user confirms.

    Args:
        parent: Parent window
        image_cache: Image cache instance
        image_downloader: Bulk image downloader instance (or None to create)
        on_status_update: Optional callback for status bar updates
    """
    dialog = ImageDownloadDialog(parent, image_cache, image_downloader, on_status_update)

    if dialog.ShowModal() == wx.ID_OK:
        quality, max_cards = dialog.get_selected_options()
        dialog.start_download(quality, max_cards)

    dialog.Destroy()
