"""The clipped-edge fade for the deck card views (grid + pile).

The review's S5: "the last row of the card grid and the whole sideboard strip
are sliced in half by the pane edge with **no fade**, no partial-row suppression
and no scroll affordance". A partial row is the correct thing for a scrolling
pane to show -- it is how the pane says there is more -- but only if it reads as
*dissolving* past the edge rather than as a clipped render. That is this
module's whole job, and it is drawn on an edge **only when there is content past
it**, so it doubles as the missing scroll affordance: no fade at the top means
you are at the top.

Why a pre-rendered alpha bitmap and not a gradient brush
--------------------------------------------------------
Both views paint through ``wx.AutoBufferedPaintDC``. A ``wx.GraphicsContext``
built over one inherits the DC's device origin (``PrepareDC`` has already
shifted it by the scroll position), so a gradient drawn "at the bottom of the
client" needs the transform reasoned about rather than measured -- exactly the
shape of failure this codebase has eleven documented instances of. A
``wx.Bitmap`` carrying an alpha channel and blitted with ``DrawBitmap(...,
True)`` needs no transform reasoning, is honoured by wxMSW on a buffered DC, and
costs one small blit. The bitmaps are cached per width so a scroll rebuilds
nothing.

``SetBackgroundStyle(wx.BG_STYLE_PAINT)`` is mandatory for any of this to appear
(phase 5): without it wxMSW's own erase-background pass owns the client area and
the buffered DC's contents are discarded. Both views already set it -- if either
ever stops, this fade is the first thing that silently vanishes.

Why a resize must invalidate the **whole** client (#983)
--------------------------------------------------------
The fade is the one thing these views paint against the *viewport* rather than
against the content, so it is the one thing that goes stale when the viewport
moves under it. wxMSW invalidates only the **newly exposed** strip of a resized
window (no ``wxFULL_REPAINT_ON_RESIZE``, and a `wx.PaintDC` is clipped to the
update region by ``BeginPaint``), so a pane that grows repaints the new strip --
drawing the fade against the new bottom edge -- and leaves the previous paint's
fade sitting in the middle of the retained pixels, un-erased. Dragging the
mainboard/sideboard sash live does that once per mouse-move, so the band the
bottom edge sweeps past accumulates one 24px fade per step and the card rows
come out smeared with dark stripes.

Scrolling does not have this problem -- measured, see the ``wx.ScrolledWindow``
entry in ``docs/WXMSW_BEHAVIOUR.md``: wxMSW invalidates the whole client for
these windows on a scroll, so the scroll path is byte-identical to a full
``Refresh``. A **resize** is not, which is why both views call ``Refresh()``
unconditionally from their ``EVT_SIZE`` handler. If either ever stops, this
fade is the first thing that smears.
"""

from __future__ import annotations

import wx

from utils.constants import CARD_VIEW_EDGE_FADE_PX
from widgets.panels.card_table_panel import scroll_snap

# Alpha ramp exponent. 1.0 is a linear ramp, which reads as a grey wash over the
# whole band; >1 keeps the fade close to the edge so the card under it stays
# legible until it is nearly gone.
_FADE_GAMMA = 1.8

_cache: dict[tuple[int, int, bool, tuple[int, int, int]], wx.Bitmap] = {}
_CACHE_MAX = 16


def _fade_bitmap(width: int, height: int, top: bool, colour: tuple[int, int, int]) -> wx.Bitmap:
    key = (width, height, top, colour)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    image = wx.Image(width, height)
    image.SetRGB(wx.Rect(0, 0, width, height), *colour)
    alpha = bytearray(width * height)
    span = max(1, height - 1)
    for y in range(height):
        # Opaque against the pane edge, transparent where the content is whole.
        fraction = (span - y) / span if top else y / span
        value = int(round(255 * (fraction**_FADE_GAMMA)))
        alpha[y * width : (y + 1) * width] = bytes([value]) * width
    image.SetAlpha(bytes(alpha))
    bitmap = wx.Bitmap(image)
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[key] = bitmap
    return bitmap


def draw_edge_fades(
    window: wx.ScrolledWindow, dc: wx.DC, colour: tuple[int, int, int]
) -> tuple[bool, bool]:
    """Fade whichever of ``window``'s vertical edges has content beyond it.

    ``dc`` is expected to have been through ``PrepareDC``, so drawing happens in
    logical coordinates -- the origin of the viewport is the current view start.
    Returns ``(top_drawn, bottom_drawn)`` so a test can assert which edges the
    view believes are clipped without reading pixels.
    """
    ppu_x, ppu_y = window.GetScrollPixelsPerUnit()
    if ppu_y <= 0:
        return False, False
    view_x, view_y = window.GetViewStart()
    view_x *= max(1, ppu_x)
    view_y *= ppu_y
    client_w, client_h = window.GetClientSize()
    if client_w <= 0 or client_h <= 0:
        return False, False
    height = min(CARD_VIEW_EDGE_FADE_PX, client_h // 2)
    if height <= 1:
        return False, False
    content_h = scroll_snap.content_height(window)

    top = view_y > 0
    bottom = view_y + client_h < content_h
    if top:
        dc.DrawBitmap(_fade_bitmap(client_w, height, True, colour), view_x, view_y, True)
    if bottom:
        dc.DrawBitmap(
            _fade_bitmap(client_w, height, False, colour),
            view_x,
            view_y + client_h - height,
            True,
        )
    return top, bottom
