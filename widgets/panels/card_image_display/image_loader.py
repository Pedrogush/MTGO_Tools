"""Off-thread image-loading pipeline for the card image display widget."""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.perf import timed

if TYPE_CHECKING:
    from widgets.panels.card_image_display.protocol import CardImageDisplayProto

    _Base = CardImageDisplayProto
else:
    _Base = object


class _ImageLoaderMixin(_Base):
    """Decode/scale/mask images off-thread and composite them on the UI thread."""

    def _load_image_at_index(self, index: int, animate: bool = True) -> bool:
        """Kick off an off-thread decode/scale/mask, then composite on the UI thread.

        The expensive work (``wx.Image`` decode, high-quality ``Scale`` and the
        PIL/numpy rounded-corner masking) runs in a background thread so rapid
        card selection / face flips / printing navigation do not hitch the UI.
        Only the lightweight DC compositing + ``SetBitmap`` runs on the main
        thread, marshalled via :func:`wx.CallAfter`. Mirrors the off-thread
        pattern in ``card_table_panel/pile_view.py``.

        Returns ``True`` when a load was dispatched (the path exists and is in
        range); the actual decode result is applied asynchronously.
        """
        if not 0 <= index < len(self.image_paths):
            return False

        image_path = self.image_paths[index]

        # Bump the generation so any in-flight decode for a previous image is
        # discarded when it reaches the UI thread.
        self._image_load_gen += 1
        gen = self._image_load_gen

        Thread(
            target=self._decode_image_worker,
            args=(gen, image_path, animate),
            daemon=True,
        ).start()
        return True

    @timed
    def _decode_image_worker(self, gen: int, image_path: Path, animate: bool) -> None:
        """Background worker: decode, scale and rounded-corner mask ``image_path``.

        Produces a ready ``wx.Image`` and marshals the final composite back to
        the UI thread. No wx UI objects are touched here — ``wx.Image`` is a
        plain pixel container and the masking is pure PIL/numpy.
        """
        try:
            img = wx.Image(str(image_path), wx.BITMAP_TYPE_ANY)
            if not img.IsOk():
                logger.debug(f"Failed to load image: {image_path}")
                return

            # Scale to fit while maintaining aspect ratio.
            img_width = img.GetWidth()
            img_height = img.GetHeight()
            scale = min(self.image_width / img_width, self.image_height / img_height)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            img = img.Scale(new_width, new_height, wx.IMAGE_QUALITY_HIGH)

            # Apply the rounded-corner alpha mask off-thread (PIL/numpy only).
            masked_image = self._apply_rounded_corners_to_image(img, self.corner_radius)
        except Exception as exc:
            logger.exception(f"Error loading image {image_path}: {exc}")
            return

        wx.CallAfter(self._apply_decoded_image, gen, masked_image, animate)

    def _apply_decoded_image(self, gen: int, masked_image: wx.Image, animate: bool) -> None:
        """UI-thread: composite the pre-masked image and display it.

        Discards stale results via the generation counter so only the most
        recent request is shown.
        """
        if gen != self._image_load_gen:
            return
        try:
            # Composite background, border and flip icon around the masked image.
            bitmap = self._create_rounded_bitmap(masked_image)

            # Display with or without animation.
            if animate and self.bitmap_ctrl.GetBitmap().IsOk():
                self._start_fade_animation(bitmap)
            else:
                self.bitmap_ctrl.SetBitmap(bitmap)
                self.Refresh()
        except RuntimeError:
            # Widget was destroyed (e.g. during app shutdown) while a
            # CallAfter callback was still pending – silently bail out.
            return
