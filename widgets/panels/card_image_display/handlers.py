"""Public state setters and input/event callbacks for the card image display widget."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from widgets.panels.card_image_display.protocol import CardImageDisplayProto

    _Base = CardImageDisplayProto
else:
    _Base = object


class CardImageDisplayHandlersMixin(_Base):
    """Public state setters and input/event callbacks for :class:`CardImageDisplay`.

    The heavier concerns live in peer mixins: off-thread image loading in
    :class:`_ImageLoaderMixin`, the fade-transition loop in
    :class:`_AnimationMixin`, and bitmap rendering in
    :class:`_BitmapRendererMixin`.
    """

    def show_placeholder(self, text: str = "No image") -> None:
        self.image_paths = []
        self.current_index = 0
        bitmap = self._create_placeholder_bitmap(text)
        self.bitmap_ctrl.SetBitmap(bitmap)
        self._update_navigation()
        self.Refresh()

    def show_images(self, image_paths: list[Path], start_index: int = 0) -> bool:
        if not image_paths:
            self.show_placeholder("No images")
            return False

        # Filter to only existing paths
        valid_paths = [p for p in image_paths if p and p.exists()]
        if not valid_paths:
            self.show_placeholder("Images not found")
            return False

        self.image_paths = valid_paths
        self.current_index = min(start_index, len(valid_paths) - 1)

        # Load first image without animation
        success = self._load_image_at_index(self.current_index, animate=False)
        self._update_navigation()

        return success

    def show_image(self, image_path: Path) -> bool:
        return self.show_images([image_path] if image_path else [])

    def _update_navigation(self) -> None:
        has_alternate_face = len(self.image_paths) > 1

        # Update flip icon visibility state
        new_state = has_alternate_face
        if self.show_flip_icon_overlay != new_state:
            self.show_flip_icon_overlay = new_state
            # Reload current image to redraw with/without flip icon
            if self.image_paths and 0 <= self.current_index < len(self.image_paths):
                self._load_image_at_index(self.current_index, animate=False)

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        keycode = event.GetKeyCode()

        if keycode in (wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_SPACE):
            self._toggle_face()
        else:
            event.Skip()

    def _on_bitmap_left_click(self, event: wx.MouseEvent) -> None:
        """Handle clicks on the card image.

        If flip icon is visible and click is within icon bounds, toggle face.
        Otherwise, toggle face if multiple images exist.
        """
        if len(self.image_paths) <= 1:
            event.Skip()
            return

        # Check if click is within flip icon region (when visible)
        if self.show_flip_icon_overlay:
            click_pos = event.GetPosition()
            flip_rect = self._get_flip_icon_rect()

            # If clicked on flip icon, prioritize that
            if flip_rect.Contains(click_pos):
                self._toggle_face()
                return

        # Otherwise, any click on the image toggles
        self._toggle_face()

    def _toggle_face(self) -> None:
        if len(self.image_paths) <= 1:
            return
        self.current_index = (self.current_index + 1) % len(self.image_paths)
        self._load_image_at_index(self.current_index, animate=True)
        self._update_navigation()

    def show_flip_icon(self) -> None:
        if not self.show_flip_icon_overlay:
            self.show_flip_icon_overlay = True
            # Reload current image to redraw with flip icon
            if self.image_paths and 0 <= self.current_index < len(self.image_paths):
                self._load_image_at_index(self.current_index, animate=False)

    def hide_flip_icon(self) -> None:
        if self.show_flip_icon_overlay:
            self.show_flip_icon_overlay = False
            # Reload current image to redraw without flip icon
            if self.image_paths and 0 <= self.current_index < len(self.image_paths):
                self._load_image_at_index(self.current_index, animate=False)
