"""Card faces for the goldfish table, upright and turned ninety degrees.

The decode is the deck grid's and the pile view's -- :func:`load_card_face`, one
LANCZOS step from the file straight to the size the card is drawn at. This used
to go through an intermediate width and a ``wx.Image.Scale`` down from it, which
resamples twice and is what made a goldfish card look soft next to the same card
in the deck grid.

The rest of the shape is the grid's pipeline too (a bounded pool decodes off the
UI thread and marshals back with ``wx.CallAfter``), with three differences the
goldfish table needs and the grid does not:

* **every copy is on screen at once.** The grid draws one cell per distinct card
  and puts the count in a badge; a goldfish hand holds four Lightning Bolts as
  four cards. The cache is still keyed by name, so those four share one decode.
* **a tapped card is the same card rotated**, so each name is cached in both
  orientations. ``Rotate90`` is lossless and runs once per decode rather than in
  the paint handler, which runs on every mouse move during a drag.
* **the card has no fixed size.** It is measured from the panel (see
  ``layout.card_metrics``), so a size change re-decodes at the new size instead
  of rescaling what is already in memory. The previous size's face stands in,
  scaled, for the frame or two that takes: a card that goes soft while the window
  is being dragged and snaps sharp when it is let go is the right trade, and a
  card that is permanently soft is the bug this replaced.

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
)
from utils.constants.theme import SURFACE_BASE, TEXT_ON_FILL
from utils.image_effects import apply_rounded_corner_alpha
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    load_card_face,
    resolve_card_color,
)
from widgets.panels.deck_goldfish_panel.layout import CardMetrics
from widgets.stylize import type_font

#: Shared with nothing: the grid's pool is sized for a 40-cell deck load, this
#: one is sized for the dozen or so distinct names a goldfish ever shows at once.
#: Threads idle out, so an unopened tab costs nothing.
_DECODE_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="goldfish-img")
atexit.register(_DECODE_POOL.shutdown, wait=False, cancel_futures=True)


class GoldfishArtCache:
    """Name -> card face at the panel's current size, upright or turned.

    :param get_card_image: ``(name, size) -> Path | None``; the controller's
        image-cache lookup. Runs on a decode thread, so it must only read.
    :param get_metadata: ``name -> CardEntry | None``, for the placeholder's
        colour and for the DFC image-name candidates.
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
        #: ``(name, tapped)`` -> the face decoded at :attr:`_metrics`.
        self._faces: dict[tuple[str, bool], wx.Bitmap] = {}
        #: The same, from before the last resize: stretched stand-ins, dropped
        #: as each name's real decode lands at the new size.
        self._previous: dict[tuple[str, bool], wx.Bitmap] = {}
        self._metrics: CardMetrics | None = None
        #: Bumped on every size change. A decode that started at an older
        #: generation is dropped rather than cached at the wrong size -- the
        #: same guard the grid's ``_load_gen`` makes for a superseded load.
        self._generation = 0
        #: Names whose art has arrived at the current size.
        self._loaded: set[str] = set()
        #: Names with a decode in flight, so a repaint does not re-submit.
        self._in_flight: set[str] = set()

    def bitmap(self, name: str, metrics: CardMetrics, *, tapped: bool = False) -> wx.Bitmap:
        """This card's face at ``metrics``, queuing a decode if it is not here yet."""
        if self._metrics is None or metrics.width != self._metrics.width:
            self._resize(metrics)
        face = self._faces.get((name, tapped))
        if face is None:
            self._store(name, self._stand_in(name, metrics))
            self.prefetch([name], metrics)
            face = self._faces[(name, tapped)]
        return face

    def prefetch(self, names: list[str], metrics: CardMetrics) -> None:
        """Start decoding any of ``names`` not already cached at this size."""
        if self._metrics is None or metrics.width != self._metrics.width:
            self._resize(metrics)
        for name in dict.fromkeys(names):
            if name in self._loaded or name in self._in_flight:
                continue
            self._in_flight.add(name)
            meta = self._get_metadata(name)
            candidates = build_image_name_candidates({"name": name}, meta)
            _DECODE_POOL.submit(self._decode, name, candidates, metrics, self._generation)

    # ----- resizing -----
    def _resize(self, metrics: CardMetrics) -> None:
        """The panel changed size: everything cached is the wrong size now.

        The old faces are kept as ``_previous`` rather than thrown away, so the
        next paint has something of this card to draw while the new decode runs.
        Dropping them instead would flash every card back to its placeholder for
        every step of a window drag.
        """
        self._previous = self._faces
        self._faces = {}
        self._metrics = metrics
        self._generation += 1
        self._loaded.clear()
        self._in_flight.clear()

    def _stand_in(self, name: str, metrics: CardMetrics) -> wx.Image:
        """What to draw for ``name`` until its decode at this size lands.

        The previous size's face, stretched, when there is one -- soft for a
        frame or two beats the card disappearing. Otherwise the placeholder,
        which is drawn at the target size and so is not soft at all.
        """
        previous = self._previous.get((name, False))
        if previous is not None:
            return previous.ConvertToImage().Scale(
                metrics.width, metrics.height, wx.IMAGE_QUALITY_HIGH
            )
        return self._placeholder(name, metrics)

    # ----- decode pipeline -----
    def _decode(
        self, name: str, candidates: list[str], metrics: CardMetrics, generation: int
    ) -> None:
        """Runs on a pool thread: find the file, resize it, hand it back."""
        path: Path | None = None
        for candidate in candidates:
            found = self._get_card_image(candidate, "normal")
            if found and found.exists():
                path = found
                break
        if path is None:
            wx.CallAfter(self._decoded, name, None, generation)
            return
        try:
            image = load_card_face(path, metrics.width, metrics.height)
            wx.CallAfter(self._decoded, name, image, generation)
        except Exception:
            # A truncated or unreadable file is a cache problem, not a reason to
            # lose the card: the stand-in already in the cache holds the slot.
            wx.CallAfter(self._decoded, name, None, generation)

    def _decoded(self, name: str, image: PilImage.Image | None, generation: int) -> None:
        if generation != self._generation:
            return  # the panel resized while this was decoding
        self._in_flight.discard(name)
        if image is None:
            return
        width, height = image.size
        wx_image = wx.Image(width, height)
        wx_image.SetData(image.tobytes())
        self._store(name, apply_rounded_corner_alpha(wx_image, DECK_CARD_CORNER_RADIUS))
        self._loaded.add(name)
        self._previous.pop((name, False), None)
        self._previous.pop((name, True), None)
        self._on_ready(name)

    def _store(self, name: str, image: wx.Image) -> None:
        self._faces[(name, False)] = image.ConvertToBitmap()
        # Clockwise: that is the way a card taps, on a table and in MTGO.
        self._faces[(name, True)] = image.Rotate90(True).ConvertToBitmap()

    # ----- placeholder -----
    def _placeholder(self, name: str, metrics: CardMetrics) -> wx.Image:
        """A card-coloured plate with the card's name on it, at the drawn size.

        The same stand-in the deck grid draws while art loads, minus the mana
        badge: the cost glyphs collide with the title at the width a goldfish
        card is drawn at, and the goldfish is about *which* cards are in hand.

        Drawn at ``metrics`` rather than at some fixed size and scaled, for the
        same reason the art is decoded there: scaled text is soft text.
        """
        meta = self._get_metadata(name) or {}
        width, height = metrics.width, metrics.height
        bitmap = wx.Bitmap(width, height)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(*resolve_card_color(meta))))
        dc.Clear()
        dc.SetPen(wx.Pen(wx.Colour(*SURFACE_BASE), DECK_CARD_TEMPLATE_BORDER_WIDTH))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(0, 0, width, height, DECK_CARD_CORNER_RADIUS)
        dc.SetTextForeground(wx.Colour(*TEXT_ON_FILL))
        dc.SetFont(type_font("caption", bold=True))
        self._draw_name(dc, name, width, height)
        dc.SelectObject(wx.NullBitmap)
        return apply_rounded_corner_alpha(bitmap.ConvertToImage(), DECK_CARD_CORNER_RADIUS)

    @staticmethod
    def _draw_name(dc: wx.DC, name: str, width: int, height: int) -> None:
        max_width = width - DECK_CARD_BADGE_PADDING * 2
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
        y = (height - line_height * len(lines)) // 2
        for line in lines:
            dc.DrawText(line, (width - dc.GetTextExtent(line)[0]) // 2, y)
            y += line_height
