"""Bitmap and PNG caches owned by :class:`ManaIconFactory`.

The renderer reads from and writes to these dicts on each request; this module
just owns the mutable state so the renderer mixin can stay focused on drawing.
"""

from __future__ import annotations

from pathlib import Path

import wx


class ManaBitmapCache:
    """Holds the per-factory bitmap, hires-bitmap, cost-composite, and PNG caches."""

    def __init__(self) -> None:
        self.bitmaps: dict[str, wx.Bitmap] = {}
        self.hires_bitmaps: dict[str, wx.Bitmap] = {}  # pre-downscale, render-scale resolution
        self.cost_bitmaps: dict[str, wx.Bitmap] = {}
        self.png_paths: dict[tuple[str, int], Path] = {}
        self.png_dir: Path | None = None
