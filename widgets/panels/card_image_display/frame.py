"""Card image display widget with navigation and transition animations.

Features:
- Display MTG card images with rounded corners
- Toggle between multiple faces with an overlay button
- Smooth fade transition animations between images
"""

from __future__ import annotations

from pathlib import Path

import wx

from utils.constants import (
    CARD_IMAGE_CORNER_RADIUS,
    CARD_IMAGE_DISPLAY_HEIGHT,
    CARD_IMAGE_DISPLAY_WIDTH,
    CARD_IMAGE_FLIP_ICON_MARGIN,
    CARD_IMAGE_FLIP_ICON_SIZE,
)
from widgets.panels.card_image_display.handlers import CardImageDisplayHandlersMixin
from widgets.panels.card_image_display.properties import CardImageDisplayPropertiesMixin


class CardImageDisplay(CardImageDisplayHandlersMixin, CardImageDisplayPropertiesMixin, wx.Panel):
    """A panel that displays MTG card images with navigation and animations."""

    def __init__(
        self,
        parent: wx.Window,
        width: int = CARD_IMAGE_DISPLAY_WIDTH,
        height: int = CARD_IMAGE_DISPLAY_HEIGHT,
    ):
        super().__init__(parent)

        self.image_width = width
        self.image_height = height
        self.corner_radius = CARD_IMAGE_CORNER_RADIUS

        # Flip icon state
        self.show_flip_icon_overlay = False
        self.flip_icon_size = CARD_IMAGE_FLIP_ICON_SIZE
        self.flip_icon_margin = (
            CARD_IMAGE_FLIP_ICON_MARGIN  # Small margin to align with card border
        )

        # Image navigation state
        self.image_paths: list[Path] = []
        self.current_index: int = 0

        # Animation state
        self.animation_timer: wx.Timer | None = None
        self.animation_alpha: float = 0.0
        self.animation_target_bitmap: wx.Bitmap | None = None
        self.animation_current_bitmap: wx.Bitmap | None = None

        # Set panel size
        self.SetMinSize((width, height))

        # Create UI components
        self._build_ui()

        # Show placeholder initially
        self.show_placeholder()

    def _build_ui(self) -> None:
        # Main vertical sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Image display area
        self.image_panel = wx.Panel(self, size=(self.image_width, self.image_height))

        # Card image bitmap
        self.bitmap_ctrl = wx.StaticBitmap(
            self.image_panel, size=(self.image_width, self.image_height), pos=(0, 0)
        )
        self.bitmap_ctrl.Bind(wx.EVT_LEFT_UP, self._on_bitmap_left_click)

        main_sizer.Add(self.image_panel, 1, wx.EXPAND | wx.ALL, 0)

        self.SetSizer(main_sizer)

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_down)

    def __del__(self):
        if self.animation_timer and self.animation_timer.IsRunning():
            self.animation_timer.Stop()
