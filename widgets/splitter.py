"""The app's one splitter, because wxMSW's sash is not a colour you can set.

Found by phase 6b's mechanical sweep, not by any list: the deck workspace's
mainboard/sideboard splitter draws its sash as a **6px band of ``#F0F0F0`` with
a ``#FFFFFF`` centre line**, ~1585px wide on a maximised main window. That is
roughly 9,500 near-white pixels sitting between the card grid and the sideboard
strip -- larger than the ``wx.StaticBox`` groove phase 6 called the
second-loudest chrome in the app, and larger than the two collapse-toggle rails
phase 6 fixed. It survived six phases of screenshots because it looks like a
deliberate divider until you sample it, and because every light-pixel census so
far excluded the card-art rectangle it sits inside.

What was measured
-----------------
Six variants, wxWidgets 3.2.8 / wxPython 4.2.4, process dark mode on:

===================================  =========================================
variant                              result
===================================  =========================================
``SP_3DSASH | SP_NO_XP_THEME``       7px sash: ``#F0F0F0`` band, ``#FFFFFF``
  (what the tree had)                centre, ``#A0A0A0``/``#696969`` shadow
no 3-D flags                         4px sash, still light
``SetBackgroundColour``              **ignored** for the sash
``disable_native_theme``             **ignored** -- unlike ``wx.Choice`` and
                                     ``wx.Gauge``, dropping out of visual
                                     styles changes nothing here
``SP_THIN_SASH``                     thinner, still light
``SetSashInvisible(True)``           dark -- **and unusable**: it drops
                                     ``GetSashSize()`` to **0**, and the sash
                                     hit test is derived from that size, so the
                                     split stops being draggable. The deck
                                     workspace's splitter exists *to* be dragged
                                     (#781), so this trades one defect for a
                                     worse one
===================================  =========================================

So the sash is own-drawn, which is the same answer phase 3b reached for the menu
bar and phase 6 reached for the FlatNotebook tab strip: subclass the one paint
path and leave every other behaviour alone. ``EVT_PAINT`` on a splitter is
uniquely safe -- the two panes are child windows that paint themselves, so the
only pixels the splitter's own paint handler ever owns *are* the sash gutter.

The 3-D flags are kept deliberately. They no longer draw anything (the paint
handler does not skip), but ``SP_3DSASH`` is what sets ``GetSashSize()`` to 7,
and the deck workspace's saved sash position is stored in points that assume it.
Dropping the flag would silently move every user's split.

``EVT_PAINT`` alone is not enough: ``SizeWindows()`` repaints the sash
------------------------------------------------------------------------
The paint handler above is correct at rest and was wrong for the whole duration
of a live drag, which is the one moment the user is looking straight at the
sash. ``wxSplitterWindow::SizeWindows()`` ends by drawing the sash **straight
onto a ``wxClientDC``** -- an immediate, un-invalidated write to the window
surface that never becomes a ``WM_PAINT`` and so never reaches ``EVT_PAINT``.

Traced on the surface itself (a ``ClientDC`` blit after each step -- a
``PrintWindow`` capture re-renders the tree and shows the *intended* pixels, so
it hides this defect completely), one step of a live drag runs:

1. ``OnMouseEvent(MOTION)`` moves the panes; the gutter is briefly unpainted,
2. ``EVT_PAINT`` runs and fills it with ``BORDER_SUBTLE``,
3. **then** ``OnInternalIdle`` runs ``SizeWindows()``, which paints the native
   ``#F0F0F0``/``#FFFFFF``/``#A0A0A0``/``#696969`` band over the top.

The own-drawn colour loses every step because it is painted *first*. Measured on
the deck workspace: **14 of 15 drag steps** left the native light sash on screen,
and a ``--method screen`` video of a real sweep caught it in 9 of 43 frames --
i.e. the divider strobes between ``#39424E`` and near-white at mouse-move
cadence, which in a dark theme is both the brightest thing on screen and a large
flickering area.

Neither obvious escape works, and both were measured rather than read:

===================================  =========================================
route                                result
===================================  =========================================
``SetSashInvisible(True)`` plus a     **no effect.** ``GetSashSize()`` is not
  Python ``GetSashSize()`` override   virtual across the Python boundary: with
                                      the override returning 7, C++ still laid
                                      pane two out for a 0px sash. The
                                      documented trap is not escapable this way
a ``wx.DelegateRendererNative``       **never called.** wxPython builds no
  subclass overriding                 director for it, so
  ``DrawSplitterSash``, installed     ``wxSplitterWindow::DrawSash`` keeps
  with ``wx.RendererNative.Set``      reaching the native renderer
===================================  =========================================

What is left is to repaint the gutter *after* ``SizeWindows()`` on each path
that reaches it. ``OnInternalIdle`` *is* dispatched into Python and is the only
hook that runs after a live drag's deferred ``SizeWindows()``; a programmatic
move runs it inline, so ``SetSashPosition`` is overridden for that one.
"""

from __future__ import annotations

import wx

from utils.constants.theme import BORDER_SUBTLE

#: The default style for a splitter in this app: live drag, 3-D sash *metrics*
#: without the 3-D sash *paint*, and no XP theming (which the paint handler
#: makes moot but which keeps the metrics stable across Windows versions).
DEFAULT_SPLITTER_STYLE = wx.SP_LIVE_UPDATE | wx.SP_3DSASH | wx.SP_NO_XP_THEME


class DarkSplitter(wx.SplitterWindow):
    """A ``wx.SplitterWindow`` whose sash is ``BORDER_SUBTLE`` instead of white.

    ``BORDER_SUBTLE``, not ``BORDER_STRONG``: a sash is a boundary between two
    regions that are each identified by their own content, so WCAG 1.4.11 does
    not apply -- the same call phase 6 made for all ten section cards. The drag
    affordance is the cursor change, which wx still provides because the sash
    keeps its size.

    The colour is applied on **three** paths, because wx paints the sash on
    three and only one of them is an event (see the module docstring):

    * ``EVT_PAINT`` -- exposure, hot-tracking, and every ordinary repaint,
    * ``OnInternalIdle`` -- immediately after a live drag's deferred
      ``SizeWindows()`` has drawn the native sash onto a ``wxClientDC``,
    * ``SetSashPosition`` -- the same, for a programmatic move and for a
      resize, both of which run ``SizeWindows()`` inline.
    """

    def __init__(self, parent: wx.Window, *args, **kwargs) -> None:
        kwargs.setdefault("style", DEFAULT_SPLITTER_STYLE)
        super().__init__(parent, *args, **kwargs)
        self._sash_brush = wx.Brush(wx.Colour(*BORDER_SUBTLE))
        # Required by wx.AutoBufferedPaintDC: without it wxMSW leaves the
        # backing store alone and a window that paints everything itself shows
        # whatever was last blitted there (phase 5's finding).
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*BORDER_SUBTLE))
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _gutter_rect(self) -> wx.Rect:
        """The sash band, in client coordinates.

        ``GetSashSize()`` rather than a literal 7: it is what ``SizeWindows()``
        itself lays the panes out with, so this rect is exactly the strip
        neither pane covers.
        """
        size = self.GetClientSize()
        position = self.GetSashPosition()
        sash = self.GetSashSize()
        if self.GetSplitMode() == wx.SPLIT_VERTICAL:
            return wx.Rect(position, 0, sash, size.height)
        return wx.Rect(0, position, size.width, sash)

    def _fill_gutter(self, dc: wx.DC, rect: wx.Rect) -> None:
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetBrush(self._sash_brush)
        dc.DrawRectangle(rect)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        """Fill the gutter and **do not skip**.

        Skipping would let ``wxSplitterWindow::OnPaint`` run ``DrawSash``
        afterwards and repaint the white band on top, which is the whole thing
        being avoided.
        """
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(self._sash_brush)
        dc.Clear()

    def OnInternalIdle(self) -> None:
        """Repaint the gutter after ``SizeWindows()`` has drawn the native sash.

        ``super()`` first, and that ordering is the entire point: a live drag's
        ``SizeWindows()`` runs inside it (``OnMouseEvent`` only sets
        ``m_needUpdating``), and the ``wxClientDC`` it draws the native sash
        with never raises a paint event. Painting here is the same immediate
        write to the same surface, one call later, so the light band is
        overwritten within a single idle round rather than surviving until the
        next unrelated repaint.

        This also covers ``wxSplitterWindow::OnSize``, whose inline
        ``SizeWindows()`` is followed by an idle round before anything is
        presented.
        """
        super().OnInternalIdle()
        self._repaint_gutter_now()

    def SetSashPosition(self, position: int, redraw: bool = True) -> None:
        """Move the sash, then undo the native sash ``SizeWindows()`` just drew.

        The idle repaint above is not enough on its own: a *programmatic* move
        runs ``SizeWindows()`` inline, and the two panes then repaint their
        (image-heavy) content before the event loop reaches idle -- a gap a
        screen capture of the deck workspace caught the light band in 4 times
        in 55 frames. This closes it at the call.
        """
        super().SetSashPosition(position, redraw)
        if redraw:
            self._repaint_gutter_now()

    def _repaint_gutter_now(self) -> None:
        """Fill the gutter, unconditionally.

        A "has anything changed?" guard was tried and measured: it skipped 4 of
        150 idle rounds *while the native sash was on the surface*, because
        ``SizeWindows()`` can redraw at a position already filled with no
        ``EVT_PAINT`` in between -- and 4 skips is exactly the residue a screen
        capture still caught. There is no cheap way to detect that from Python,
        so the guard cost correctness and bought nothing: an idle app was
        measured at fewer than 2.5 idle rounds per second, and the work here is
        one solid fill of a 7px band.
        """
        if not self.IsSplit():
            return
        self._fill_gutter(wx.ClientDC(self), self._gutter_rect())


__all__ = ["DEFAULT_SPLITTER_STYLE", "DarkSplitter"]
