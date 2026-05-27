"""Image-effect helpers used by deck-card renderers."""

from __future__ import annotations

import numpy as np
import wx
from PIL import Image as PilImage
from PIL import ImageDraw


def apply_rounded_corner_alpha(image: wx.Image, radius: int) -> wx.Image:
    """Return a copy of ``image`` with a rounded-corner alpha mask applied.

    Pixels outside the rounded rectangle become fully transparent so the
    surface below shows through; existing alpha inside the rounded region is
    preserved via per-pixel ``min``.
    """
    img = image.Copy()
    if not img.HasAlpha():
        img.InitAlpha()

    w, h = img.GetWidth(), img.GetHeight()
    mask_pil = PilImage.new("L", (w, h), 0)
    ImageDraw.Draw(mask_pil).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    mask_bytes = np.frombuffer(mask_pil.tobytes(), dtype=np.uint8)
    existing_alpha = np.frombuffer(bytes(img.GetAlpha()), dtype=np.uint8)
    new_alpha = np.minimum(existing_alpha, mask_bytes)
    img.SetAlpha(new_alpha.tobytes())
    return img
