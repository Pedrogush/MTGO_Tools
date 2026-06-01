"""Shared ``self`` contract that the :class:`CardImageDisplay` mixins assume."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import wx


class CardImageDisplayProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardImageDisplay``.

    Typed once here so each helper mixin can inherit it (via a
    ``TYPE_CHECKING`` ``_Base``) instead of re-declaring the shared attributes
    and the wx :class:`wx.Panel` methods every mixin reaches for.
    """

    # Geometry / styling (set in ``CardImageDisplay.__init__``).
    image_width: int
    image_height: int
    corner_radius: int

    # Flip icon state.
    show_flip_icon_overlay: bool
    flip_icon_size: int
    flip_icon_margin: int

    # Image navigation state.
    image_paths: list[Path]
    current_index: int

    # Generation counter guarding stale off-thread decodes.
    _image_load_gen: int

    # Fade-animation state.
    animation_timer: wx.Timer | None
    animation_alpha: float
    animation_target_bitmap: wx.Bitmap | None
    animation_current_bitmap: wx.Bitmap | None

    # UI components.
    bitmap_ctrl: wx.StaticBitmap
    image_panel: wx.Panel

    # ── wx.Panel surface the mixins call ────────────────────────────────
    def Refresh(self, *args, **kwargs) -> None: ...

    def GetParent(self) -> wx.Window: ...

    def Bind(self, *args, **kwargs) -> None: ...

    # ── Cross-mixin helpers ─────────────────────────────────────────────
    # Properties mixin (pure helpers).
    def _blend_bitmaps(self, bmp1: wx.Bitmap, bmp2: wx.Bitmap, alpha: float) -> wx.Bitmap: ...

    def _get_flip_icon_rect(self) -> wx.Rect: ...

    def _apply_rounded_corners_to_image(self, image: wx.Image, radius: int) -> wx.Image: ...

    # Image-loader mixin.
    def _load_image_at_index(self, index: int, animate: bool = ...) -> bool: ...

    def _apply_decoded_image(self, gen: int, masked_image: wx.Image, animate: bool) -> None: ...

    # Animation mixin.
    def _start_fade_animation(self, target_bitmap: wx.Bitmap) -> None: ...

    def _on_animation_tick(self, event: wx.TimerEvent) -> None: ...

    # Bitmap-renderer mixin.
    def _create_rounded_bitmap(self, masked_image: wx.Image) -> wx.Bitmap: ...

    def _draw_flip_icon_on_gc(self, gc: wx.GraphicsContext) -> None: ...

    def _create_placeholder_bitmap(self, text: str) -> wx.Bitmap: ...

    # Handlers / public state.
    def _update_navigation(self) -> None: ...

    def _toggle_face(self) -> None: ...
