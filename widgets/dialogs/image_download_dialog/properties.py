"""Selection accessors for the image download dialog."""

from __future__ import annotations

import wx


class ImageDownloadDialogPropertiesMixin:
    """Option accessors for :class:`ImageDownloadDialog`."""

    quality_choice: wx.Choice
    amount_choice: wx.Choice

    def get_selected_options(self) -> tuple[str, int | None]:
        quality_map = {0: "small", 1: "normal", 2: "large", 3: "png"}
        quality = quality_map[self.quality_choice.GetSelection()]

        amount_map = {0: 100, 1: 1000, 2: 5000, 3: 10000, 4: None}
        max_cards = amount_map[self.amount_choice.GetSelection()]

        return quality, max_cards
