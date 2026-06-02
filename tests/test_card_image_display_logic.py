"""Pixel-level regression tests for CardImageDisplay image processing.

These tests drive the *production* pure-byte helpers in ``utils.image_effects``
(``blend_rgb_bytes``, ``rounded_corner_mask_bytes``,
``apply_rounded_corner_alpha_bytes``) — the same functions the wx-dependent
``_blend_bitmaps`` / ``_apply_rounded_corners_to_image`` /
``apply_rounded_corner_alpha`` call internally. A regression in the production
math therefore fails these tests.

No wx display is required — the helpers operate on raw bytes, so only PIL and
numpy are needed.
"""

import importlib.util
import random
from pathlib import Path

import pytest

from utils.image_effects import (
    apply_rounded_corner_alpha_bytes,
    blend_rgb_bytes,
    rounded_corner_mask_bytes,
)

# Load the wx-free ``ui_images`` constants submodule by file path. Importing it
# normally (``from utils.constants...``) would execute the constants package
# ``__init__`` which pulls in wx (unavailable off-Windows), so we side-step it.
_ui_images_path = Path(__file__).resolve().parent.parent / "utils" / "constants" / "ui_images.py"
_spec = importlib.util.spec_from_file_location("_ui_images_for_test", _ui_images_path)
_ui_images = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ui_images)
CARD_IMAGE_CORNER_RADIUS = _ui_images.CARD_IMAGE_CORNER_RADIUS
CARD_IMAGE_DISPLAY_HEIGHT = _ui_images.CARD_IMAGE_DISPLAY_HEIGHT
CARD_IMAGE_DISPLAY_WIDTH = _ui_images.CARD_IMAGE_DISPLAY_WIDTH

# ── reference implementations (pre-PIL pure-Python loops) ────────────────────


def _blend_bitmaps_reference(data1: bytes, data2: bytes, alpha: float) -> bytes:
    """Original pure-Python blend loop (reference implementation)."""
    blended = bytearray(len(data1))
    for i in range(0, len(data1), 3):
        blended[i] = int(data1[i] * (1 - alpha) + data2[i] * alpha)
        blended[i + 1] = int(data1[i + 1] * (1 - alpha) + data2[i + 1] * alpha)
        blended[i + 2] = int(data1[i + 2] * (1 - alpha) + data2[i + 2] * alpha)
    return bytes(blended)


def _apply_corners_reference(alpha_data: bytes, w: int, h: int, radius: int) -> bytes:
    """Original nested-loop corner masking (reference implementation)."""
    arr = bytearray(alpha_data)

    def is_inside(px, py):
        if px < radius and py < radius:
            dx, dy = radius - px, radius - py
            return dx * dx + dy * dy <= radius * radius
        if px >= w - radius and py < radius:
            dx, dy = px - (w - radius - 1), radius - py
            return dx * dx + dy * dy <= radius * radius
        if px < radius and py >= h - radius:
            dx, dy = radius - px, py - (h - radius - 1)
            return dx * dx + dy * dy <= radius * radius
        if px >= w - radius and py >= h - radius:
            dx, dy = px - (w - radius - 1), py - (h - radius - 1)
            return dx * dx + dy * dy <= radius * radius
        return True

    for y in range(h):
        for x in range(w):
            if not is_inside(x, y):
                arr[y * w + x] = 0
    return bytes(arr)


# ── blend tests (exercise production blend_rgb_bytes) ────────────────────────

W, H = 8, 8  # Small image for fast tests; pixel math is identical at any size


@pytest.mark.parametrize("alpha", [0.0, 0.15, 0.5, 0.85, 1.0])
def test_blend_matches_reference(alpha):
    """Production blend output must match the original loop (±1 rounding)."""
    rng = random.Random(42)
    data1 = bytes(rng.randint(0, 255) for _ in range(W * H * 3))
    data2 = bytes(rng.randint(0, 255) for _ in range(W * H * 3))

    expected = _blend_bitmaps_reference(data1, data2, alpha)
    actual = blend_rgb_bytes(data1, data2, W, H, alpha)

    # PIL uses float32 internally; allow ±1 rounding tolerance.
    for i, (e, a) in enumerate(zip(expected, actual)):
        assert abs(e - a) <= 1, f"Pixel mismatch at byte {i}: expected {e}, got {a} (alpha={alpha})"


def test_blend_identical_images_returns_same():
    """Blending identical images must return the original."""
    data = bytes([100, 150, 200] * (W * H))
    result = blend_rgb_bytes(data, data, W, H, 0.5)
    for i in range(0, len(data), 3):
        assert abs(result[i] - data[i]) <= 1


def test_blend_alpha_zero_returns_first():
    data1 = bytes([10] * W * H * 3)
    data2 = bytes([200] * W * H * 3)
    result = blend_rgb_bytes(data1, data2, W, H, 0.0)
    assert all(abs(b - 10) <= 1 for b in result)


def test_blend_alpha_one_returns_second():
    data1 = bytes([10] * W * H * 3)
    data2 = bytes([200] * W * H * 3)
    result = blend_rgb_bytes(data1, data2, W, H, 1.0)
    assert all(abs(b - 200) <= 1 for b in result)


def test_blend_output_length_matches_input():
    """Output must be the same RGB byte length as the inputs."""
    data1 = bytes([10] * W * H * 3)
    data2 = bytes([200] * W * H * 3)
    assert len(blend_rgb_bytes(data1, data2, W, H, 0.5)) == W * H * 3


# ── rounded corner tests (exercise production corner helpers) ─────────────────

RW, RH = 20, 20

# Parametrise over small test images AND the actual production dimensions so
# that regressions at the real card size are caught immediately.
_CORNER_CASES = [
    (RW, RH, 0),
    (RW, RH, 2),
    (RW, RH, 4),
    (CARD_IMAGE_DISPLAY_WIDTH, CARD_IMAGE_DISPLAY_HEIGHT, CARD_IMAGE_CORNER_RADIUS),
]


def _is_in_corner(x: int, y: int, w: int, h: int, radius: int) -> bool:
    return (
        (x < radius and y < radius)
        or (x >= w - radius and y < radius)
        or (x < radius and y >= h - radius)
        or (x >= w - radius and y >= h - radius)
    )


@pytest.mark.parametrize("iw,ih,radius", _CORNER_CASES)
def test_corners_match_reference(iw, ih, radius):
    """Production corner mask must agree with the original on all interior pixels.

    PIL's rounded_rectangle rasterises the corner arc slightly differently from
    the discrete circle equation used in the original loop: it may include 1-2
    extra pixels on the corner arc boundary per corner.  Interior pixels must be
    identical; PIL must never make a pixel *more* transparent than the original.
    """
    alpha_in = bytes([255] * iw * ih)  # fully opaque
    expected = _apply_corners_reference(alpha_in, iw, ih, radius)
    actual = apply_rounded_corner_alpha_bytes(alpha_in, iw, ih, radius)

    if radius == 0:
        assert expected == actual, "radius=0 must produce identical output"
        return

    diffs = [(i, e, a) for i, (e, a) in enumerate(zip(expected, actual)) if e != a]

    # Bound: generous budget for 4 corners, each contributing ~radius/2 pixels
    assert len(diffs) <= 4 * radius, (
        f"Too many differing pixels at radius={radius} on {iw}x{ih}: "
        f"{len(diffs)} > {4 * radius}"
    )

    for idx, orig_val, pil_val in diffs:
        x = idx % iw
        y = idx // iw
        assert _is_in_corner(x, y, iw, ih, radius), (
            f"Pixel diff outside corner region at ({x},{y}) on {iw}x{ih} "
            f"r={radius}: orig={orig_val}, pil={pil_val}"
        )
        assert (
            pil_val >= orig_val
        ), f"PIL made pixel more transparent at ({x},{y}): orig={orig_val}, pil={pil_val}"

    # Strict invariant: every interior pixel that original kept opaque must
    # also be opaque in the production result.  This directly verifies the
    # directional claim and is not dependent on the diff count.
    for i, (e, a) in enumerate(zip(expected, actual)):
        if e == 255:
            assert a == 255, (
                f"PIL zeroed an opaque interior pixel at index {i} "
                f"({i % iw},{i // iw}) on {iw}x{ih} r={radius}"
            )


def test_corner_mask_interior_is_uniformly_opaque():
    """The production mask must be 255 everywhere except the rounded corners.

    ``apply_rounded_corner_alpha_bytes`` relies on the mask interior being a
    flat 255 so ``np.minimum`` preserves (rather than erodes) partial alpha.
    """
    radius = 4
    mask = rounded_corner_mask_bytes(RW, RH, radius)
    assert len(mask) == RW * RH
    for i, v in enumerate(mask):
        x, y = i % RW, i // RW
        if not _is_in_corner(x, y, RW, RH, radius):
            assert v == 255, f"interior pixel ({x},{y}) was {v}, expected 255"


def test_corners_zero_radius_preserves_all_alpha():
    """radius=0 means no rounding; all pixels should remain opaque."""
    alpha_in = bytes([255] * RW * RH)
    result = apply_rounded_corner_alpha_bytes(alpha_in, RW, RH, radius=0)
    assert all(b == 255 for b in result)


def test_corners_does_not_elevate_transparent_pixels():
    """Pixels that are already alpha=0 inside the round rect must stay 0."""
    alpha_in = bytes([0] * RW * RH)
    result = apply_rounded_corner_alpha_bytes(alpha_in, RW, RH, radius=3)
    assert all(b == 0 for b in result)


def test_corners_center_pixel_opaque():
    """Center pixel must always be inside the rounded rect, alpha=255."""
    alpha_in = bytes([255] * RW * RH)
    result = apply_rounded_corner_alpha_bytes(alpha_in, RW, RH, radius=4)
    center_idx = (RH // 2) * RW + (RW // 2)
    assert result[center_idx] == 255


def test_corners_true_corner_transparent():
    """The (0,0) pixel must be outside a rounded rect with radius > 0."""
    alpha_in = bytes([255] * RW * RH)
    result = apply_rounded_corner_alpha_bytes(alpha_in, RW, RH, radius=4)
    assert result[0] == 0  # top-left corner pixel


def test_corners_preserves_partial_alpha_in_interior():
    """np.minimum must not clip partial alpha values that lie inside the rounded rect.

    If the mask interior is not uniformly 255, np.minimum would silently erode
    valid semi-transparent pixels.  This test guards against that.
    """
    rng = random.Random(99)
    radius = 3
    # Use a value guaranteed to be in the non-corner interior
    interior_x, interior_y = RW // 2, RH // 2
    # Build alpha map with a distinctive value at the interior pixel
    alpha_list = [rng.randint(0, 255) for _ in range(RW * RH)]
    partial_value = 128
    alpha_list[interior_y * RW + interior_x] = partial_value
    alpha_in = bytes(alpha_list)

    result = apply_rounded_corner_alpha_bytes(alpha_in, RW, RH, radius)
    center_idx = interior_y * RW + interior_x
    assert (
        result[center_idx] == partial_value
    ), f"Interior partial alpha {partial_value} was changed to {result[center_idx]}"
