"""Pure-data helpers for the card image display widget."""

from __future__ import annotations

import numpy as np
import wx
from PIL import Image as PilImage
from PIL import ImageDraw

from utils.perf import timed


class CardImageDisplayPropertiesMixin:
    """Pure helpers (no UI mutation) for :class:`CardImageDisplay`.

    Kept as a mixin (no ``__init__``) so :class:`CardImageDisplay` remains the
    single source of truth for instance-state initialization.
    """

    # Attributes supplied by :class:`CardImageDisplay`.
    flip_icon_size: int
    flip_icon_margin: int

    def _blend_bitmaps(self, bmp1: wx.Bitmap, bmp2: wx.Bitmap, alpha: float) -> wx.Bitmap:
        img1 = bmp1.ConvertToImage()
        img2 = bmp2.ConvertToImage()

        w1, h1 = img1.GetWidth(), img1.GetHeight()
        w2, h2 = img2.GetWidth(), img2.GetHeight()

        # Normalise to same size (preserves existing size-mismatch contract)
        if (w1, h1) != (w2, h2):
            img1 = img1.Resize(img2.GetSize(), (0, 0))
            w1, h1 = w2, h2

        # Convert wx.Image RGB data to PIL, blend in C, convert back.
        # wx.Image.GetData() always returns raw RGB bytes (3 bytes/pixel, no alpha),
        # matching PIL.Image.frombytes("RGB"). Semantics: out = img1*(1-alpha) + img2*alpha.
        pil1 = PilImage.frombytes("RGB", (w1, h1), bytes(img1.GetData()))
        pil2 = PilImage.frombytes("RGB", (w2, h2), bytes(img2.GetData()))
        blended = PilImage.blend(pil1, pil2, alpha)

        result = wx.Image(w1, h1)
        result.SetData(blended.tobytes())
        return wx.Bitmap(result)

    def _get_flip_icon_rect(self) -> wx.Rect:
        icon_x = self.flip_icon_margin
        icon_y = self.flip_icon_margin
        return wx.Rect(icon_x, icon_y, self.flip_icon_size, self.flip_icon_size)

    @timed
    def _apply_rounded_corners_to_image(self, image: wx.Image, radius: int) -> wx.Image:
        img = image.Copy()
        if not img.HasAlpha():
            img.InitAlpha()

        w, h = img.GetWidth(), img.GetHeight()

        # Build a binary rounded-rectangle mask via PIL (C-native rasterisation).
        # Interior pixels are 255; outside-corner pixels are 0.
        mask_pil = PilImage.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask_pil)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        mask_bytes = np.frombuffer(mask_pil.tobytes(), dtype=np.uint8)

        # Apply mask: np.minimum preserves partial alpha inside the rect and
        # forces alpha=0 in the transparent corner regions.
        # bytes(img.GetAlpha()) creates a copy, so frombuffer is not read-only.
        existing_alpha = np.frombuffer(bytes(img.GetAlpha()), dtype=np.uint8)
        new_alpha = np.minimum(existing_alpha, mask_bytes)
        img.SetAlpha(new_alpha.tobytes())
        return img
