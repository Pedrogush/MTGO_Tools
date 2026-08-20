"""The clipped-edge fade for the deck card views (grid + pile).

The review's S5: "the last row of the card grid and the whole sideboard strip
are sliced in half by the pane edge with **no fade**, no partial-row suppression
and no scroll affordance". A partial row is the correct thing for a scrolling
pane to show -- it is how the pane says there is more -- but only if it reads as
*dissolving* past the edge rather than as a clipped render. That is this
module's whole job.

The bottom band is drawn **always**; the top band only when the view is scrolled
off its origin. The asymmetry is deliberate. The bottom edge of a scrolling pane
is where a row gets sliced, and a band whose colour *is* the pane background
costs nothing where there is no content under it -- scrolled fully down, or with
a deck shorter than the viewport, it composites background over background and
is invisible. Making it conditional bought no pixels and cost the property below.
The **top** band keeps its condition because that is where the affordance now
lives: no fade at the top means you are at the top.

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

Why the whole client must be invalidated whenever the viewport moves (#983)
---------------------------------------------------------------------------
The fade is the one thing these views paint against the *viewport* rather than
against the content, so it is the one thing that goes stale when the viewport
moves under it. Both ways of moving it strand a copy, for the same reason:
wxMSW keeps the pixels it can and invalidates only the strip it cannot, and a
``wx.PaintDC`` is clipped to that update region by ``BeginPaint``. Nothing a
paint handler draws can repair a pixel outside it -- which is why the fix is not
a different *drawing*, it is a wider update region.

* **Scrolling.** wx moves the viewport by blitting (``ScrollWindow``) and
  invalidating only the newly exposed strip. Logged from the pile view's own
  paint handler over a six-notch wheel burst::

      region=(0, 289, 912, 64)  client=(912, 353)  view_y=124
      region=(0, 289, 912, 64)  client=(912, 353)  view_y=188

  The bottom band of the previous frame lived at y 329..353; the blit carried it
  to y 265..289, i.e. *just above* the 64px strip wx asked to be repainted. One
  stale band per notch, 64px apart, and nothing washes them out -- they sat
  unchanged for the remaining 750ms of every capture. This is the half that the
  first attempt at #983 ruled out on a bad measurement (see the ``wx.Scrolled
  Window`` entry in ``docs/WXMSW_BEHAVIOUR.md``, corrected) and it is the half
  the reporter was looking at. :func:`require_whole_client_repaints` is what
  stops it.

* **A resize.** Same clipping, no blit needed: a pane that grows repaints only
  the strip it gained and leaves the previous paint's fade sitting un-erased in
  the retained pixels, once per mouse-move of a live sash drag. Both views
  therefore ``Refresh()`` unconditionally from their ``EVT_SIZE`` handler, which
  is measured to hold: every step of a 250px live sash sweep logs
  ``region=(0, 0, w, h)``.

If either mechanism is ever dropped, this fade is the first thing that smears.
Neither costs much: every paint already blits the *whole* viewport out of the
view's content canvas, so a wider update region widens only the copy that
reaches the screen.
"""

from __future__ import annotations

import wx

from utils.constants import CARD_VIEW_EDGE_FADE_PX

# Alpha ramp exponent. 1.0 is a linear ramp, which reads as a grey wash over the
# whole band; >1 keeps the fade close to the edge so the card under it stays
# legible until it is nearly gone.
_FADE_GAMMA = 1.8

_cache: dict[tuple[int, int, bool, tuple[int, int, int]], wx.Bitmap] = {}
_CACHE_MAX = 16


def require_whole_client_repaints(window: wx.ScrolledWindow) -> None:
    """Make every scroll of ``window`` invalidate all of it, not just the gap.

    ``SetDoubleBuffered(True)`` is ``WS_EX_COMPOSITED``, under which MSW stops
    preserving pixels across a scroll and hands the paint handler the whole
    client. The two more targeted-looking levers were measured on wxMSW 4.2 and
    do **not** work, which is the reason this one-liner gets a named function
    and a paragraph (probe kept in the #983 thread):

    * ``EnableScrolling(False, False)`` -- documented as replacing the blit with
      a refresh -- changes nothing. The update region stayed the 64px exposed
      strip. Another entry for the silent-no-op list.
    * Overriding ``ScrollWindow`` in the Python subclass is never called: wx
      scrolls from C++ without going back through the Python vtable.
    * ``Refresh()`` after each of *our* ``Scroll()`` calls does give a whole-
      client region, but only for the paths that go through our code. Driving
      the same window with ``ScrollLines`` -- the scrollbar arrows and the
      keyboard, which wx handles internally -- still produced ``(0, 243, 387,
      1)``: a 1px strip, and a stale band left behind.

    The cost is the one this window was avoiding deliberately: MSW now repaints
    the whole client per notch. It is affordable here because both views already
    render the whole viewport into the buffer on every paint regardless of the
    update region -- the scroll path was never actually culled, only its final
    blit was -- and because ``wx.AutoBufferedPaintDC`` degrades to a plain
    ``wx.PaintDC`` once the window is double-buffered, so nothing is buffered
    twice.
    """
    window.SetDoubleBuffered(True)


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
    """Composite the gradient mask over ``window``'s bottom edge, and its top.

    The bottom mask is unconditional; the top one is drawn only when the view is
    scrolled off its origin (see the module docstring for why they differ).

    ``dc`` is expected to have been through ``PrepareDC``, so drawing happens in
    logical coordinates -- the origin of the viewport is the current view start.
    Returns ``(top_drawn, bottom_drawn)`` so a test can assert what the view
    composited without reading pixels.
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

    top = view_y > 0
    if top:
        dc.DrawBitmap(_fade_bitmap(client_w, height, True, colour), view_x, view_y, True)
    dc.DrawBitmap(
        _fade_bitmap(client_w, height, False, colour),
        view_x,
        view_y + client_h - height,
        True,
    )
    return top, True
