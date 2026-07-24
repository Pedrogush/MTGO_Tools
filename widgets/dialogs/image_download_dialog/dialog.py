"""Dialog for enabling offline images mode (bulk card-image download)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx

from utils.constants import DARK_BG, LIGHT_TEXT, SUBDUED_TEXT
from widgets.dialogs.image_download_dialog.handlers import ImageDownloadDialogHandlersMixin
from widgets.dialogs.image_download_dialog.properties import ImageDownloadDialogPropertiesMixin

if TYPE_CHECKING:
    from services.image_service import BulkImageDownloader


class ImageDownloadDialog(
    ImageDownloadDialogHandlersMixin, ImageDownloadDialogPropertiesMixin, wx.Dialog
):
    """Explains offline images mode and confirms the one-time bulk download.

    The app works without this: images are prefetched in the background and
    fetched on demand as cards are browsed (issue #951). Enabling offline mode
    trades ~12 GB of disk for having *every* card image local, so nothing ever
    needs the network again. Only the medium ("normal") Scryfall size is
    downloaded — it reads well on both low- and high-resolution monitors.
    """

    def __init__(
        self,
        parent: wx.Window,
        image_cache: Any,
        image_downloader: BulkImageDownloader | None,
        bulk_data_cache_path: Path,
        on_status_update: Callable[[str], None] | None = None,
    ):
        super().__init__(parent, title="Offline Images Mode", size=(460, 320))
        self.SetBackgroundColour(DARK_BG)

        self.image_cache = image_cache
        self.image_downloader = image_downloader
        self.bulk_data_cache_path = bulk_data_cache_path
        self.on_status_update = on_status_update

        self._build_ui()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Title
        title = wx.StaticText(panel, label="Enable Offline Images Mode")
        title.SetForegroundColour(LIGHT_TEXT)
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # What this is for
        purpose_text = wx.StaticText(
            panel,
            label=(
                "Normally, card images are fetched over the internet as you browse — "
                "the app predicts what you are about to look at and downloads those "
                "images a few seconds ahead of you.\n\n"
                "Offline images mode instead downloads a medium-quality image for every "
                "Magic card (100,000+ images) up front, so every card displays instantly "
                "and keeps working with no internet connection at all."
            ),
        )
        purpose_text.SetForegroundColour(LIGHT_TEXT)
        purpose_text.Wrap(430)
        sizer.Add(purpose_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # The tradeoff
        tradeoff_text = wx.StaticText(
            panel,
            label=(
                "Tradeoff: this uses about 12.2 GB of disk space. The download runs in "
                "the background and typically takes 30-60 minutes depending on your "
                "connection; you can keep using the app while it runs. If it is "
                "interrupted, enabling it again skips the images you already have."
            ),
        )
        tradeoff_text.SetForegroundColour(SUBDUED_TEXT)
        tradeoff_text.Wrap(430)
        sizer.Add(tradeoff_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer(1)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Cancel")
        button_sizer.Add(cancel_btn, 0, wx.RIGHT, 6)

        enable_btn = wx.Button(panel, wx.ID_OK, label="Enable Offline Mode")
        enable_btn.SetDefault()
        button_sizer.Add(enable_btn, 0)

        sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizerAndFit(sizer)
        self.SetClientSize(panel.GetBestSize())
        self.Centre()


def show_image_download_dialog(
    parent: wx.Window,
    image_cache: Any,
    image_downloader: BulkImageDownloader,
    bulk_data_cache_path: Path,
    on_status_update: Callable[[str], None] | None = None,
) -> None:
    dialog = ImageDownloadDialog(
        parent, image_cache, image_downloader, bulk_data_cache_path, on_status_update
    )

    if dialog.ShowModal() == wx.ID_OK:
        quality, max_cards = dialog.get_selected_options()
        dialog.start_download(quality, max_cards)

    dialog.Destroy()
