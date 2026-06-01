"""Bitmap rendering (canvas, border, flip icon, placeholder) for the card image display widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    CARD_IMAGE_FLIP_ICON_TEXT_SCALE,
    CARD_IMAGE_PLACEHOLDER_INSET,
)

if TYPE_CHECKING:
    from widgets.panels.card_image_display.protocol import CardImageDisplayProto

    _Base = CardImageDisplayProto
else:
    _Base = object


class _BitmapRendererMixin(_Base):
    """Composites the card canvas, anti-aliased border, flip icon and placeholder bitmaps."""

    def _create_rounded_bitmap(self, masked_image: wx.Image) -> wx.Bitmap:
        """Composite a pre-masked card image onto the dark, bordered canvas.

        ``masked_image`` must already have its rounded-corner alpha applied
        (done off-thread in :meth:`_decode_image_worker`); this method performs
        only the UI-thread DC compositing of the background, border and flip
        icon.
        """
        # Create a bitmap canvas
        bitmap = wx.Bitmap(self.image_width, self.image_height)
        dc = wx.MemoryDC(bitmap)

        # Fill background with parent color
        bg_color = self.GetParent().GetBackgroundColour()
        dc.SetBackground(wx.Brush(bg_color))
        dc.Clear()

        # Draw dark background rounded rectangle
        dc.SetPen(wx.Pen(wx.Colour(40, 40, 40), 1))
        dc.SetBrush(wx.Brush(wx.Colour(40, 40, 40)))
        dc.DrawRoundedRectangle(0, 0, self.image_width, self.image_height, self.corner_radius)

        # Center the image
        img_width = masked_image.GetWidth()
        img_height = masked_image.GetHeight()
        x = (self.image_width - img_width) // 2
        y = (self.image_height - img_height) // 2

        # Draw the (already masked) image
        dc.DrawBitmap(wx.Bitmap(masked_image), x, y, True)

        # Draw border using GraphicsContext for smooth anti-aliased edges
        gc = wx.GraphicsContext.Create(dc)
        if gc:
            gc.SetPen(wx.Pen(wx.Colour(60, 60, 60), 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            path = gc.CreatePath()
            path.AddRoundedRectangle(
                0.5, 0.5, self.image_width - 1, self.image_height - 1, self.corner_radius
            )
            gc.DrawPath(path)

            # Draw flip icon overlay if enabled
            if self.show_flip_icon_overlay:
                self._draw_flip_icon_on_gc(gc)
        else:
            # Fallback border without antialiasing
            dc.SetPen(wx.Pen(wx.Colour(60, 60, 60), 1))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRoundedRectangle(0, 0, self.image_width, self.image_height, self.corner_radius)

        dc.SelectObject(wx.NullBitmap)
        return bitmap

    def _draw_flip_icon_on_gc(self, gc: wx.GraphicsContext) -> None:
        # Calculate icon position (top-left corner)
        icon_x = self.flip_icon_margin
        icon_y = self.flip_icon_margin

        # Draw semi-transparent shadow effect
        # Outer shadow
        gc.SetBrush(
            gc.CreateRadialGradientBrush(
                icon_x + self.flip_icon_size / 2,
                icon_y + self.flip_icon_size / 2 + 2,
                icon_x + self.flip_icon_size / 2,
                icon_y + self.flip_icon_size / 2 + 2,
                self.flip_icon_size / 2 + 2,
                wx.Colour(0, 0, 0, 100),  # semi-transparent black shadow
                wx.Colour(0, 0, 0, 0),  # fully transparent
            )
        )
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawEllipse(icon_x - 2, icon_y, self.flip_icon_size + 4, self.flip_icon_size + 4)

        # Main background circle (black with semi-transparency)
        gc.SetBrush(
            gc.CreateRadialGradientBrush(
                icon_x + self.flip_icon_size / 2,
                icon_y + self.flip_icon_size / 2,
                icon_x + self.flip_icon_size / 2,
                icon_y + self.flip_icon_size / 2,
                self.flip_icon_size / 2,
                wx.Colour(40, 40, 40, 220),  # center: dark gray, semi-transparent
                wx.Colour(20, 20, 20, 200),  # edge: darker gray, semi-transparent
            )
        )
        gc.SetPen(wx.Pen(wx.Colour(80, 80, 80, 200), 2))
        gc.DrawEllipse(icon_x, icon_y, self.flip_icon_size, self.flip_icon_size)

        # Draw the flip icon text (yellow)
        font_size = int(self.flip_icon_size * CARD_IMAGE_FLIP_ICON_TEXT_SCALE)
        font = wx.Font(wx.FontInfo(font_size).Bold())
        gc.SetFont(font, wx.Colour(255, 220, 0, 255))  # Yellow text, opaque

        text = "⟳"
        tw, th = gc.GetTextExtent(text)
        text_x = icon_x + (self.flip_icon_size - tw) / 2
        text_y = icon_y + (self.flip_icon_size - th) / 2
        gc.DrawText(text, text_x, text_y)

    def _create_placeholder_bitmap(self, text: str) -> wx.Bitmap:
        bitmap = wx.Bitmap(self.image_width, self.image_height)
        dc = wx.MemoryDC(bitmap)

        # Background
        bg_color = self.GetParent().GetBackgroundColour()
        dc.SetBackground(wx.Brush(bg_color))
        dc.Clear()

        # Draw rounded rectangle
        dc.SetPen(wx.Pen(wx.Colour(80, 80, 80), 2))
        dc.SetBrush(wx.Brush(wx.Colour(50, 50, 50)))
        dc.DrawRoundedRectangle(
            CARD_IMAGE_PLACEHOLDER_INSET,
            CARD_IMAGE_PLACEHOLDER_INSET,
            self.image_width - (CARD_IMAGE_PLACEHOLDER_INSET * 2),
            self.image_height - (CARD_IMAGE_PLACEHOLDER_INSET * 2),
            self.corner_radius,
        )

        # Draw text
        dc.SetTextForeground(wx.Colour(150, 150, 150))
        font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        dc.SetFont(font)

        text_width, text_height = dc.GetTextExtent(text)
        text_x = (self.image_width - text_width) // 2
        text_y = (self.image_height - text_height) // 2
        dc.DrawText(text, text_x, text_y)

        dc.SelectObject(wx.NullBitmap)
        return bitmap
