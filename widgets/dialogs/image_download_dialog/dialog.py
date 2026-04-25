"""Dialog for downloading card images from Scryfall with progress tracking."""

from collections.abc import Callable
from typing import Any

import wx

from utils.card_images import BulkImageDownloader
from utils.constants import DARK_BG, LIGHT_TEXT, SUBDUED_TEXT
from widgets.dialogs.image_download_dialog.handlers import ImageDownloadDialogHandlersMixin
from widgets.dialogs.image_download_dialog.properties import ImageDownloadDialogPropertiesMixin


class ImageDownloadDialog(
    ImageDownloadDialogHandlersMixin, ImageDownloadDialogPropertiesMixin, wx.Dialog
):
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


def show_image_download_dialog(
    parent: wx.Window,
    image_cache: Any,
    image_downloader: BulkImageDownloader | None,
    on_status_update: Callable[[str], None] | None = None,
) -> None:
    dialog = ImageDownloadDialog(parent, image_cache, image_downloader, on_status_update)

    if dialog.ShowModal() == wx.ID_OK:
        quality, max_cards = dialog.get_selected_options()
        dialog.start_download(quality, max_cards)

    dialog.Destroy()
