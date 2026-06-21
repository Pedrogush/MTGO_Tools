"""Async image pipeline + placeholder templates for :class:`DeckGridView`.

Two collaborating responsibilities, both extracted as a thin mixin in the
package's view-collaborator style:

* the off-UI-thread decode pipeline — a shared, bounded :class:`ThreadPoolExecutor`
  (with an ``atexit`` non-blocking shutdown) that resizes each card's art with
  PIL and marshals the result back via ``wx.CallAfter``. The liveness contract
  matters: the worker runs off-thread and ``_image_loaded`` guards against a
  destroyed view (``if not self``) and against stale loads (per-name
  ``_load_gen`` generation check) before touching the cache or canvas.
* the placeholder templates drawn while a card's art is still loading — a
  card-colour background, mana-cost badge and wrapped name, cached per name.

The decode pool is a module-level singleton shared across every grid view, so it
lives here rather than on the instance; ``atexit`` cancels in-flight decodes so
shutdown never blocks on a join.
"""

from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import wx
from PIL import Image as PilImage

from utils.constants import (
    DARK_PANEL,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_IMAGE_BG,
    DECK_CARD_NAME_FONT_SIZE,
    DECK_CARD_TEMPLATE_BORDER_ALPHA,
    DECK_CARD_TEMPLATE_BORDER_WIDTH,
    LIGHT_TEXT,
)
from utils.image_effects import composite_rounded_on_background
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    resolve_card_color,
)
from widgets.panels.card_table_panel.grid_layout import _CARD_HEIGHT, _CARD_WIDTH

# Shared, bounded pool for decoding deck-cell card images off the UI thread.
# One shared pool makes dispatch a near-free submit() and caps the number of
# concurrent PIL decodes so 40 LANCZOS resizes don't thrash the GIL. Threads
# idle out, so the pool costs nothing between deck loads.
_IMAGE_DECODE_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="card-img-decode")
# Don't let the executor's atexit join block app shutdown on in-flight decodes.
atexit.register(_IMAGE_DECODE_POOL.shutdown, wait=False, cancel_futures=True)


class GridImagesMixin:
    """Async art-decode pipeline + placeholder templates for the grid view."""

    # ----- image loading -----
    def _prefetch_images(self) -> None:
        seen: set[str] = set()
        for card in self._cards:
            name = card["name"]
            if name in seen or self._image_cache.has(name):
                continue
            seen.add(name)
            self._start_image_load(name)

    def _start_image_load(self, name: str) -> None:
        gen = self._load_gen.get(name, 0) + 1
        self._load_gen[name] = gen
        # Mark as in-flight so _prefetch_images won't double-submit; the cache
        # returning None for a known key falls back to the placeholder template.
        self._image_cache.put(name, None)
        meta = self._get_metadata(name) or {}
        candidates = build_image_name_candidates({"name": name}, meta)
        _IMAGE_DECODE_POOL.submit(self._image_worker, name, gen, candidates)

    def _image_worker(self, name: str, gen: int, candidates: list[str]) -> None:
        image_path: Path | None = None
        # Prefer the card's chosen printing (issue #792). Falls through to the
        # name-based candidates when no printing is selected or its image isn't
        # cached yet (a download is queued by the resolver; refresh_image reruns
        # this worker once it arrives).
        if self._get_printing_image is not None:
            try:
                chosen = self._get_printing_image(name)
            except Exception:
                chosen = None
            if chosen and chosen.exists():
                image_path = chosen
        if image_path is None:
            for candidate in candidates:
                path = self._get_card_image(candidate, "normal")
                if path and path.exists():
                    image_path = path
                    break
        if image_path is None:
            wx.CallAfter(self._image_loaded, name, gen, None)
            return
        try:
            img = PilImage.open(str(image_path)).convert("RGB")
            w, h = img.size
            scale = min(_CARD_WIDTH / w, _CARD_HEIGHT / h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), PilImage.LANCZOS)
            wx.CallAfter(self._image_loaded, name, gen, img)
        except Exception:
            wx.CallAfter(self._image_loaded, name, gen, None)

    def _image_loaded(self, name: str, gen: int, pil_img: PilImage.Image | None) -> None:
        try:
            if not self:
                return
        except RuntimeError:
            return
        if self._load_gen.get(name) != gen:
            return  # superseded by a newer load for this card
        if pil_img is None:
            self._image_cache.put(name, None)  # keep placeholder
        else:
            w, h = pil_img.size
            wx_img = wx.Image(w, h)
            wx_img.SetData(pil_img.tobytes())
            # Flatten onto the canvas background (DARK_PANEL) so the cached
            # bitmap is opaque and blits via a fast BitBlt — see
            # composite_rounded_on_background. Grid cells never overlap and sit
            # on DARK_PANEL, so this is pixel-identical to a transparent corner.
            wx_img = composite_rounded_on_background(wx_img, DECK_CARD_CORNER_RADIUS, DARK_PANEL)
            self._image_cache.put(name, wx_img.ConvertToBitmap())
        # A single card's art changed — patch just its cell in the cached image.
        self._patch_card_on_canvas(name)

    # ----- placeholder template -----
    def _template_for(self, name: str) -> wx.Bitmap:
        cached = self._template_cache.get(name)
        if cached is not None:
            return cached
        meta = self._get_metadata(name) or {}
        bitmap = self._build_template_bitmap(name, meta)
        self._template_cache[name] = bitmap
        return bitmap

    def _build_template_bitmap(self, name: str, meta: dict[str, Any]) -> wx.Bitmap:
        color = resolve_card_color(meta)
        mana_cost = meta.get("mana_cost") or ""
        bitmap = wx.Bitmap(_CARD_WIDTH, _CARD_HEIGHT)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(*color)))
        dc.Clear()
        rect = wx.Rect(0, 0, _CARD_WIDTH, _CARD_HEIGHT)
        dc.SetPen(
            wx.Pen(
                wx.Colour(*DECK_CARD_IMAGE_BG, DECK_CARD_TEMPLATE_BORDER_ALPHA),
                DECK_CARD_TEMPLATE_BORDER_WIDTH,
            )
        )
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)
        self._draw_placeholder_details(dc, rect, name, mana_cost)
        dc.SelectObject(wx.NullBitmap)
        flat = composite_rounded_on_background(
            bitmap.ConvertToImage(), DECK_CARD_CORNER_RADIUS, DARK_PANEL
        )
        return flat.ConvertToBitmap()

    def _draw_placeholder_details(
        self, dc: wx.DC, rect: wx.Rect, name: str, mana_cost: str
    ) -> None:
        cost_bitmap = self._icon_factory.bitmap_for_cost(mana_cost) if mana_cost else None
        if cost_bitmap:
            cost_x = rect.x + rect.width - cost_bitmap.GetWidth() - DECK_CARD_BADGE_PADDING
            cost_y = rect.y + DECK_CARD_BADGE_PADDING
            dc.DrawBitmap(cost_bitmap, cost_x, cost_y, True)
        elif mana_cost:
            dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
            dc.DrawText(
                mana_cost,
                rect.x + rect.width - (DECK_CARD_BADGE_PADDING * 6),
                rect.y + DECK_CARD_BADGE_PADDING,
            )

        dc.SetTextForeground(wx.Colour(0, 0, 0))
        dc.SetFont(
            wx.Font(
                DECK_CARD_NAME_FONT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_BOLD,
            )
        )
        name_lines = self._wrap_text(dc, name, rect.width - (DECK_CARD_BADGE_PADDING * 2))
        line_height = dc.GetTextExtent("Ag")[1]
        total_height = line_height * len(name_lines)
        start_y = rect.y + (rect.height - total_height) // 2
        for line in name_lines:
            text_width = dc.GetTextExtent(line)[0]
            dc.DrawText(line, rect.x + (rect.width - text_width) // 2, start_y)
            start_y += line_height

    @staticmethod
    def _wrap_text(dc: wx.DC, text: str, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if dc.GetTextExtent(test)[0] <= max_width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
