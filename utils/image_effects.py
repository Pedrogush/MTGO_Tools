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


def composite_rounded_on_background_bytes(
    rgb_data: bytes,
    existing_alpha: bytes,
    w: int,
    h: int,
    radius: int,
    bg_rgb: tuple[int, int, int],
) -> bytes:
    """Flatten a rounded card's RGB onto an opaque ``bg_rgb`` background.

    Pure-byte core of :func:`composite_rounded_on_background`. ``rgb_data`` is a
    ``w*h`` RGB buffer (3 bytes/pixel); ``existing_alpha`` is the matching
    ``w*h`` per-pixel alpha buffer. The rounded-corner mask is combined with the
    existing alpha (per-pixel ``min``) and used to blend the card over ``bg_rgb``
    via ``out = rgb*alpha + bg*(1-alpha)``. Returns a ``w*h`` RGB byte buffer
    with no alpha channel.
    """
    alpha = (
        np.frombuffer(
            apply_rounded_corner_alpha_bytes(existing_alpha, w, h, radius), dtype=np.uint8
        ).astype(np.float32)
        / 255.0
    )
    rgb = np.frombuffer(rgb_data, dtype=np.uint8).astype(np.float32).reshape(-1, 3)
    bg = np.array(bg_rgb, dtype=np.float32)
    out = (rgb * alpha[:, None] + bg * (1.0 - alpha[:, None])).astype(np.uint8)
    return out.tobytes()


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


def composite_rounded_on_background(
    image: wx.Image, radius: int, bg_rgb: tuple[int, int, int]
) -> wx.Image:
    """Flatten a rounded card onto an opaque ``bg_rgb`` background.

    Like :func:`apply_rounded_corner_alpha`, but instead of leaving the corners
    transparent it blends the card (using the rounded-corner mask as alpha) onto
    ``bg_rgb`` and returns an image with **no** alpha channel. An opaque bitmap
    draws via a fast ``BitBlt`` rather than the much slower per-pixel
    ``AlphaBlend``, which matters when dozens of cards are composited into the
    cached canvas on every resize — the alpha path is what stalled side-panel
    toggles and left a visible "void" band (#782 follow-up). Wherever the card is
    drawn on a ``bg_rgb`` surface (e.g. the grid canvas, cleared to that colour)
    the result is pixel-identical to the transparent-corner version.
    """
    import wx

    img = image.Copy()
    if not img.HasAlpha():
        img.InitAlpha()
    w, h = img.GetWidth(), img.GetHeight()
    out = composite_rounded_on_background_bytes(
        bytes(img.GetData()), bytes(img.GetAlpha()), w, h, radius, bg_rgb
    )
    result = wx.Image(w, h)
    result.SetData(out)
    return result
