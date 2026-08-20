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

Why moving the viewport used to smear it (#983)
-----------------------------------------------
The fade is the one thing these views paint against the *viewport* rather than
against the content, so it is the one thing that goes stale when the viewport
moves under it. Everything else scrolls or resizes with the pixels and stays
correct; a band does not, and wxMSW keeps whatever pixels it can.

Three separate mechanisms move a viewport here, and each needed its own answer.
None of them is a *drawing* problem, which is why two earlier attempts that
changed how the band was composited did not fix it:

1. **wx's own scroll blit reaching the screen.** ``Scroll()`` goes through
   ``wxScrollHelper::DoScroll``, which calls ``::ScrollWindow()`` -- a
   screen-to-screen copy that carries the previous frame's band to a new
   position and invalidates only the strip it could not cover. Answered by
   :func:`scroll_snap.scroll_viewport`, which every gesture that moves the
   origin goes through.
2. **A repaint clipped to less than the whole client.** Whatever region wx does
   hand a paint handler, the handler cannot repair a band outside it, because
   ``BeginPaint`` clips the ``wx.PaintDC`` before the handler runs. Answered by
   :func:`begin_viewport_paint`.
3. **MSW preserving bits across a resize.** MSW copies the old pixels into the
   new geometry and invalidates only what the copy could not cover, and
   ``WM_PAINT`` is the lowest-priority message there is -- so during a live sash
   drag the copy is on screen long before the repaint is dispatched. Answered by
   ``wx.FULL_REPAINT_ON_RESIZE`` plus a **synchronous** repaint from each view's
   ``EVT_SIZE`` handler, which puts the correct frame into the redirection
   surface before DWM can composite the copy.

   That only works if the repaint is affordable, and for the grid it was not:
   ``_recompute_layout`` dropped the cached full-content canvas on every resize,
   so each mouse-move of a drag asked for a ~180-210ms rebuild of every card
   against a ~3ms ordinary paint. The view could not keep up and simply stopped
   repainting for the gesture, which is the real reason the drag showed a solid
   dark wash rather than separate stripes. The grid now recomputes only when the
   **width** changes, which is the only thing its layout depends on.

Measured mid-gesture against the screen's own pixels, with the band temporarily
rendered opaque and colour-coded per zone and edge so a stranded one could be
counted: before, the combined gesture the reporter describes -- scrolling up and
down *while* dragging the sash -- stranded bands in 20% of frames, three deep at
exactly the 60px notch spacing, and they were still there seven frames (~380ms)
after the gesture ended. After, 835 frames across wheel-only, sash-only and
combined gestures, in both views and both panes, hold exactly the bands the
current viewport calls for and no others.
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


def viewport_key(window: wx.ScrolledWindow) -> tuple[int, int, int, int]:
    """The state the fade is anchored to: where the viewport is, and how big.

    Two paints that agree on this tuple compose the fade in the same place, so
    the second one cannot strand the first one's band. Any change to it is a
    move of the viewport under a fade that is already on screen.
    """
    view_x, view_y = window.GetViewStart()
    return (view_x, view_y, *window.GetClientSize())


def begin_viewport_paint(window: wx.ScrolledWindow) -> bool:
    """Call first in an ``EVT_PAINT`` handler; returns "repaint everything".

    Guarantees that a paint which follows a viewport move is clipped to the
    whole client, not to the strip wx decided was enough. That is the property
    the edge fade needs and the one thing a paint handler cannot otherwise have:
    ``BeginPaint`` clips the ``wx.PaintDC`` to the update region *before* the
    handler runs, so no choice of compositing -- alpha mask, ``wx.GCDC``,
    unconditional band -- can reach a stale pixel outside it.

    It works by invalidating from inside ``WM_PAINT`` and *before* the
    ``PaintDC`` is constructed. ``Refresh()`` is ``::RedrawWindow(RDW_INVALIDATE)``,
    which only adds to the window's pending update region; ``BeginPaint`` then
    takes that region as the DC's clip. So the widening lands on the paint that
    is starting rather than on a later one, and it cannot recurse, because
    ``BeginPaint`` validates the whole region it just took. Measured on a bare
    ``wx.ScrolledWindow`` scrolled 64px against a 264px client, reading
    ``GetClipBox`` off the ``PaintDC``'s own HDC::

        no widening: update=(0, 200, 185, 64)  clip=(0, 200, 185, 64)
        widened:     update=(0, 200, 185, 64)  clip=(0,   0, 185, 264)

    Widening is limited to the paints that can actually strand a band -- the
    ones where :func:`viewport_key` changed since the last paint -- so the
    per-card ``RefreshRect`` the async image pipeline fires stays the targeted
    repaint it was built to be.

    Returns ``True`` when the caller must render its whole viewport rather than
    culling to the update region. ``wxWindowMSW`` snapshots ``m_updateRegion``
    *before* dispatching the paint event, so ``GetUpdateRegion()`` still reports
    the narrow strip after the clip has been widened, and a cull that believed
    it would leave the widening with nothing to draw.

    Levers that look right and are not, so nobody spends the afternoon again:

    * ``EnableScrolling(False, False)`` is documented as replacing the blit with
      a refresh and does nothing for the wheel. ``wxScrollHelper::DoScroll``
      never consults the flag (wx 3.2 ``src/generic/scrlwing.cpp``); only
      ``HandleOnScroll`` and ``AdjustScrollbars`` do. The earlier attempt at
      #983 recorded this as a silent no-op, which is the symptom, not the cause.
    * Overriding ``ScrollWindow`` in the Python subclass is never called: wx
      scrolls from C++ without going back through the Python vtable.
    * ``SetDoubleBuffered(True)`` (``WS_EX_COMPOSITED``) measured clean for the
      previous attempt and the reporter still saw the bands. It is documented as
      unsupported for top-level windows since Windows 8 and is observed to be
      ignored depending on DWM state, driver and window hierarchy. Nothing here
      may rest on it, which is the whole reason this fix uses only calls whose
      effect is visible in the same process that makes them.
    """
    key = viewport_key(window)
    if getattr(window, "_fade_viewport", None) == key:
        return False
    window._fade_viewport = key  # type: ignore[attr-defined]
    box = window.GetUpdateRegion().GetBox()
    if box.GetWidth() < key[2] or box.GetHeight() < key[3]:
        window.Refresh(False)
    return True


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
