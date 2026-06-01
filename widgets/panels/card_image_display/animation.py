"""Fade-transition animation timer loop for the card image display widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    CARD_IMAGE_ANIMATION_ALPHA_STEP,
    CARD_IMAGE_ANIMATION_INTERVAL_MS,
)

if TYPE_CHECKING:
    from widgets.panels.card_image_display.protocol import CardImageDisplayProto

    _Base = CardImageDisplayProto
else:
    _Base = object


class _AnimationMixin(_Base):
    """Drives the cross-fade between the current and target card bitmaps."""

    def _start_fade_animation(self, target_bitmap: wx.Bitmap) -> None:
        # Cancel any existing animation
        if self.animation_timer and self.animation_timer.IsRunning():
            self.animation_timer.Stop()

        # Set up animation state
        self.animation_current_bitmap = self.bitmap_ctrl.GetBitmap()
        self.animation_target_bitmap = target_bitmap
        self.animation_alpha = 0.0

        # Create and start timer (60 FPS)
        self.animation_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_animation_tick, self.animation_timer)
        self.animation_timer.Start(CARD_IMAGE_ANIMATION_INTERVAL_MS)  # ~60 FPS

    def _on_animation_tick(self, event: wx.TimerEvent) -> None:
        # Increment alpha (fade speed)
        self.animation_alpha += CARD_IMAGE_ANIMATION_ALPHA_STEP

        if self.animation_alpha >= 1.0:
            # Animation complete
            self.animation_timer.Stop()
            self.bitmap_ctrl.SetBitmap(self.animation_target_bitmap)
            self.animation_current_bitmap = None
            self.animation_target_bitmap = None
            self.Refresh()
            return

        # Create blended bitmap
        blended = self._blend_bitmaps(
            self.animation_current_bitmap, self.animation_target_bitmap, self.animation_alpha
        )

        self.bitmap_ctrl.SetBitmap(blended)
        self.Refresh()
