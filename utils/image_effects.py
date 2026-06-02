"""Image-effect helpers used by deck-card renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PIL import Image as PilImage
from PIL import ImageDraw

if TYPE_CHECKING:
    import wx


def rounded_corner_mask_bytes(w: int, h: int, radius: int) -> bytes:
    """Return a ``w*h`` grayscale rounded-rectangle mask as raw bytes.

    Interior pixels are ``255``; pixels outside the rounded corners are ``0``.
    Rasterised by PIL (C-native) so it matches the discrete-circle reference
    implementation on all interior pixels.
    """
    mask_pil = PilImage.new("L", (w, h), 0)
    ImageDraw.Draw(mask_pil).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return mask_pil.tobytes()


def apply_rounded_corner_alpha_bytes(existing_alpha: bytes, w: int, h: int, radius: int) -> bytes:
    """Combine an existing per-pixel alpha buffer with a rounded-corner mask.

    Existing alpha inside the rounded region is preserved via per-pixel ``min``;
    pixels outside the rounded corners become fully transparent.
    """
    mask = np.frombuffer(rounded_corner_mask_bytes(w, h, radius), dtype=np.uint8)
    existing = np.frombuffer(existing_alpha, dtype=np.uint8)
    return np.minimum(existing, mask).tobytes()


def blend_rgb_bytes(data1: bytes, data2: bytes, w: int, h: int, alpha: float) -> bytes:
    """Blend two raw RGB byte buffers: ``out = data1*(1-alpha) + data2*alpha``.

    Both buffers must describe ``w*h`` RGB images (3 bytes/pixel, no alpha),
    matching ``wx.Image.GetData()`` / ``PIL.Image.frombytes("RGB")``.
    """
    pil1 = PilImage.frombytes("RGB", (w, h), data1)
    pil2 = PilImage.frombytes("RGB", (w, h), data2)
    return PilImage.blend(pil1, pil2, alpha).tobytes()


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
    # bytes(img.GetAlpha()) creates a copy, so frombuffer is not read-only.
    new_alpha = apply_rounded_corner_alpha_bytes(bytes(img.GetAlpha()), w, h, radius)
    img.SetAlpha(new_alpha)
    return img
