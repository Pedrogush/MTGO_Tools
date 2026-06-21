"""Threaded scaled-bitmap cache for the deck pile view.

Lifts ``DeckPileView``'s image plumbing — the tiny LRU bitmap cache plus the
background-thread loader that resolves a card's art path, scales it to the deck
card size, applies the rounded-corner alpha, and converts to a ``wx.Bitmap`` —
into one reusable collaborator (issue #799). The pile view owns an instance and
talks to it through ``self``; the cache talks back through the callables it is
constructed with.

Behaviour is identical to the inline version it replaces:

* ``put(name, None)`` marks a name as "loading" so a second pass over the same
  piles does not respawn a thread for it.
* The ``image_gen`` counter is bumped on every spawned load exactly as before
  (it guards stale async loads; kept coherent now the loader lives here).
* Loads run on daemon threads and marshal their result back onto the GUI thread
  with ``wx.CallAfter`` so the cache mutation and canvas patch happen on the
  main thread.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Thread

import wx
from PIL import Image as PilImage

from utils.constants import (
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
)
from utils.image_effects import apply_rounded_corner_alpha

_CARD_WIDTH = DECK_CARD_WIDTH
_CARD_HEIGHT = DECK_CARD_HEIGHT


class _ImageCache:
    """Tiny LRU-ish cache of scaled card-image bitmaps keyed by name."""

    def __init__(self, max_entries: int = 256) -> None:
        self._cache: dict[str, wx.Bitmap | None] = {}
        self._max_entries = max_entries

    def get(self, name: str) -> wx.Bitmap | None:
        return self._cache.get(name)

    def has(self, name: str) -> bool:
        return name in self._cache

    def put(self, name: str, bitmap: wx.Bitmap | None) -> None:
        if len(self._cache) >= self._max_entries:
            # Drop an arbitrary entry — pile contents change infrequently.
            self._cache.pop(next(iter(self._cache)))
        self._cache[name] = bitmap


class ScaledBitmapCache:
    """Owns the bitmap cache and the threaded loader for a card view.

    The owning widget supplies:

    * ``get_card_image(name, size)`` / ``get_printing_image(name)`` — the same
      resolvers the view already holds (the printing resolver may be ``None``).
    * ``is_alive()`` — guards a ``wx.CallAfter`` arriving after the window died.
    * ``on_loaded(name)`` — called on the GUI thread once a name's bitmap has
      been stored, so the view can patch just the piles holding it.
    """

    def __init__(
        self,
        *,
        get_card_image: Callable[[str, str], Path | None],
        get_printing_image: Callable[[str], Path | None] | None,
        is_alive: Callable[[], bool],
        on_loaded: Callable[[str], None],
        max_entries: int = 256,
    ) -> None:
        self._cache = _ImageCache(max_entries)
        self._get_card_image = get_card_image
        self._get_printing_image = get_printing_image
        self._is_alive = is_alive
        self._on_loaded = on_loaded
        self.image_gen = 0

    # ----- cache access -----
    def get(self, name: str) -> wx.Bitmap | None:
        return self._cache.get(name)

    def has(self, name: str) -> bool:
        return self._cache.has(name)

    def put(self, name: str, bitmap: wx.Bitmap | None) -> None:
        self._cache.put(name, bitmap)

    # ----- loading -----
    def prefetch(self, names: list[str]) -> None:
        """Spawn loads for any ``names`` not already cached or loading."""
        seen: set[str] = set()
        for name in names:
            if name in seen or self._cache.has(name):
                continue
            seen.add(name)
            self._cache.put(name, None)  # mark as loading
            self._spawn(name)

    def refresh(self, name: str) -> None:
        """Drop ``name``'s cached art and reload it (e.g. its printing changed).

        Bypasses the prefetch cached-bitmap skip so a printing swap actually
        re-renders rather than reusing the previous art (issue #792).
        """
        self._cache.put(name, None)
        self._spawn(name)

    def _spawn(self, name: str) -> None:
        self.image_gen += 1
        gen = self.image_gen
        Thread(target=self._image_worker, args=(gen, name), daemon=True).start()

    def _image_worker(self, gen: int, name: str) -> None:
        try:
            path: Path | None = None
            if self._get_printing_image is not None:
                try:
                    path = self._get_printing_image(name)
                except Exception:
                    path = None
                if path and not path.exists():
                    path = None
            if path is None:
                path = self._get_card_image(name, "normal")
            if not path or not path.exists():
                wx.CallAfter(self._image_loaded, name, None)
                return
            img = PilImage.open(str(path)).convert("RGB")
            w, h = img.size
            scale = min(_CARD_WIDTH / w, _CARD_HEIGHT / h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), PilImage.LANCZOS)
            wx.CallAfter(self._image_loaded, name, img)
        except Exception:
            wx.CallAfter(self._image_loaded, name, None)

    def _image_loaded(self, name: str, pil_img: PilImage.Image | None) -> None:
        try:
            if not self._is_alive():
                return
        except RuntimeError:
            return
        if pil_img is None:
            self._cache.put(name, None)
        else:
            w, h = pil_img.size
            wx_img = wx.Image(w, h)
            wx_img.SetData(pil_img.tobytes())
            wx_img = apply_rounded_corner_alpha(wx_img, DECK_CARD_CORNER_RADIUS)
            self._cache.put(name, wx_img.ConvertToBitmap())
        # A single card's art changed — let the view patch just the piles holding it.
        self._on_loaded(name)
