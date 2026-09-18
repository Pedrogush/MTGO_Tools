"""Card faces for the goldfish table, upright and turned ninety degrees.

The same shape as :mod:`widgets.panels.card_table_panel.grid_images` -- a bounded
thread pool decodes each card's art with PIL off the UI thread and marshals the
result back with ``wx.CallAfter`` -- with two differences the goldfish table
needs and the deck grid does not:

* **every copy is on screen at once.** The grid draws one cell per distinct card
  and puts the count in a badge; a goldfish hand holds four Lightning Bolts as
  four cards. The cache is still keyed by name, so those four share one decode.
* **a tapped card is the same card rotated**, so each name is cached in both
  orientations. The rotation is done once per card at decode time rather than in
  the paint handler, because the paint handler runs on every mouse move during a
  drag.

Corners are left transparent (``apply_rounded_corner_alpha``) rather than
flattened onto the surface colour the way the grid's are: cards on a table
overlap, and an opaque corner would punch a dark square out of whatever is
underneath.
"""

from __future__ import annotations

import atexit
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import wx
from PIL import Image as PilImage

from utils.constants import (
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_TEMPLATE_BORDER_WIDTH,
    GOLDFISH_CARD_HEIGHT,
    GOLDFISH_CARD_WIDTH,
)
from utils.constants.theme import SURFACE_BASE, TEXT_ON_FILL
from utils.image_effects import apply_rounded_corner_alpha
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    resolve_card_color,
)
from widgets.stylize import type_font

#: Shared with nothing: the grid's pool is sized for a 40-cell deck load, this
#: one is sized for the dozen or so distinct names a goldfish ever shows at once.
#: Threads idle out, so an unopened tab costs nothing.
_DECODE_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="goldfish-img")
atexit.register(_DECODE_POOL.shutdown, wait=False, cancel_futures=True)


class GoldfishArtCache:
    """Name -> ``(upright, tapped)`` bitmaps, with a placeholder until art lands.

    :param get_card_image: ``(name, size) -> Path | None``; the controller's
        image-cache lookup. Runs on a decode thread, so it must only read.
    :param get_metadata: ``name -> CardEntry | None``, for the placeholder's
        colour and mana cost.
    :param on_ready: called on the UI thread once a card's real art has replaced
        its placeholder, so the view can repaint.
    """

    def __init__(
        self,
        get_card_image: Callable[[str, str], Path | None],
        get_metadata: Callable[[str], Any],
        on_ready: Callable[[str], None],
    ) -> None:
        self._get_card_image = get_card_image
        self._get_metadata = get_metadata
        self._on_ready = on_ready
        self._upright: dict[str, wx.Bitmap] = {}
        self._tapped: dict[str, wx.Bitmap] = {}
        #: Names whose art has arrived, so a second prefetch does not re-decode.
        self._loaded: set[str] = set()
        #: Names with a decode in flight, for the same reason.
        self._in_flight: set[str] = set()

    def bitmap(self, name: str, *, tapped: bool = False) -> wx.Bitmap:
        """This card's face, building the placeholder and queuing art if needed."""
        cache = self._tapped if tapped else self._upright
        cached = cache.get(name)
        if cached is not None:
            return cached
        self._store(name, self._placeholder(name))
        self.prefetch([name])
        return (self._tapped if tapped else self._upright)[name]

    def prefetch(self, names: list[str]) -> None:
        """Start decoding any of ``names`` whose art is not cached or in flight."""
        for name in dict.fromkeys(names):
            if name in self._loaded or name in self._in_flight:
                continue
            self._in_flight.add(name)
            meta = self._get_metadata(name)
            candidates = build_image_name_candidates({"name": name}, meta)
            _DECODE_POOL.submit(self._decode, name, candidates)

    # ----- decode pipeline -----
    def _decode(self, name: str, candidates: list[str]) -> None:
        """Runs on a pool thread: find the file, resize it, hand it back."""
        path: Path | None = None
        for candidate in candidates:
            found = self._get_card_image(candidate, "normal")
            if found and found.exists():
                path = found
                break
        if path is None:
            wx.CallAfter(self._decoded, name, None)
            return
        try:
            image = PilImage.open(str(path)).convert("RGB")
            image = image.resize((GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT), PilImage.LANCZOS)
            wx.CallAfter(self._decoded, name, image)
        except Exception:
            # A truncated or unreadable file is a cache problem, not a reason to
            # lose the card: the placeholder already in the cache stands in.
            wx.CallAfter(self._decoded, name, None)

    def _decoded(self, name: str, image: PilImage.Image | None) -> None:
        self._in_flight.discard(name)
        if image is None:
            return
        wx_image = wx.Image(GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT)
        wx_image.SetData(image.tobytes())
        self._store(name, apply_rounded_corner_alpha(wx_image, DECK_CARD_CORNER_RADIUS))
        self._loaded.add(name)
        self._on_ready(name)

    def _store(self, name: str, image: wx.Image) -> None:
        self._upright[name] = image.ConvertToBitmap()
        # Clockwise: that is the way a card taps, on a table and in MTGO.
        self._tapped[name] = image.Rotate90(True).ConvertToBitmap()

    # ----- placeholder -----
    def _placeholder(self, name: str) -> wx.Image:
        """A card-coloured plate with the card's name on it, drawn once per name.

        The same stand-in the deck grid draws while art loads, minus the mana
        badge: at 100px wide the cost glyphs collide with the title, and the
        goldfish is about *which* cards are in the hand.
        """
        meta = self._get_metadata(name) or {}
        bitmap = wx.Bitmap(GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(*resolve_card_color(meta))))
        dc.Clear()
        dc.SetPen(wx.Pen(wx.Colour(*SURFACE_BASE), DECK_CARD_TEMPLATE_BORDER_WIDTH))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(
            0, 0, GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT, DECK_CARD_CORNER_RADIUS
        )
        dc.SetTextForeground(wx.Colour(*TEXT_ON_FILL))
        dc.SetFont(type_font("caption", bold=True))
        self._draw_name(dc, name)
        dc.SelectObject(wx.NullBitmap)
        return apply_rounded_corner_alpha(bitmap.ConvertToImage(), DECK_CARD_CORNER_RADIUS)

    @staticmethod
    def _draw_name(dc: wx.DC, name: str) -> None:
        max_width = GOLDFISH_CARD_WIDTH - DECK_CARD_BADGE_PADDING * 2
        lines: list[str] = []
        current = ""
        for word in name.split() or [name]:
            candidate = f"{current} {word}".strip()
            if dc.GetTextExtent(candidate)[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        line_height = dc.GetTextExtent("Ag")[1]
        y = (GOLDFISH_CARD_HEIGHT - line_height * len(lines)) // 2
        for line in lines:
            dc.DrawText(line, (GOLDFISH_CARD_WIDTH - dc.GetTextExtent(line)[0]) // 2, y)
            y += line_height
