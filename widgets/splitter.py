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

The 3-D flags are kept deliberately. They no longer draw anything, but
``SP_3DSASH`` is what sets ``GetSashSize()`` to 7, and the deck workspace's
saved sash position is stored in points that assume it. Dropping the flag would
silently move every user's split.

Why own-drawing the gutter was not enough
-----------------------------------------
The first fix bound ``EVT_PAINT`` and filled the gutter there. That is correct
at rest and wrong the moment anything moves, because **``EVT_PAINT`` is not the
only place wx paints the sash**: ``wxSplitterWindow::SizeWindows()`` ends by
drawing it **straight onto a ``wxClientDC``** -- an immediate, un-invalidated
write to the window surface that never becomes a ``WM_PAINT``.

The second fix chased that draw with a repaint after it, on the two paths that
were known at the time. Measured on the surface with a full-band scan, that
still left the native sash on screen for **100% of the band** (9,408 of 9,408
pixels) after every ``wxSplitterWindow::OnSize`` and every ``UpdateSize()`` --
i.e. on every window resize and every side-panel collapse -- because those run
``SizeWindows()`` *inline* and nothing repaints until the next idle round.

Chasing the draw is the wrong shape: it is a list of call sites, and the list
was wrong twice. What is used instead removes the possibility rather than the
symptom.

The gutter belongs to a child window
------------------------------------
``DarkSplitter`` puts a plain child window behind both panes, covering the whole
client area. A child window is **clipped out of its parent's ``wxClientDC``**,
so ``SizeWindows()``'s ``DrawSash`` physically cannot reach those pixels -- there
is no ordering to get right and no call site to enumerate.

Three details make it airtight rather than nearly so, each one measured:

* **Sized to the sash band, not the client area.** A full-client-area overlay
  was tried first and is wrong: ``Lower()`` does not stop a child painting over
  its siblings and neither does ``wx.CLIP_SIBLINGS``. Measured, it filled both
  panes with ``BORDER_SUBTLE`` and wiped the card views out -- while every
  gutter-only measurement still reported a clean pass, which is the same blind
  spot that let the previous fix ship.
* **A background colour, not a paint handler.** ``BG_STYLE_PAINT`` plus
  ``EVT_PAINT`` leaves a freshly moved overlay showing whatever was underneath
  until the handler runs -- measured as an ``#ABABAB`` strip. A plain background
  colour makes wxMSW *erase* with the right brush, and ``place()`` calls
  ``Update()`` so that erase happens before the next frame rather than at the
  next paint.
* **Placed before ``SizeWindows()`` wherever that is possible.** ``_on_size``
  runs ahead of ``wxSplitterWindow::OnSize`` and predicts where gravity is about
  to put the sash; ``OnInternalIdle`` places the overlay *before* calling
  ``super()``, because ``OnMouseEvent`` has already applied the new position and
  only defers the resize. Placing after as well is the backstop.

**This does not reach zero.** Measured on the deck workspace with a
``--method screen`` capture of a sash sweep plus repeated side-panel toggles:
**1 frame in 140**, reproducibly, still catches the native band mid-drag --
against **25 in 90** for the previous fix. The residue is a race inside a single
idle round: ``SizeWindows()`` draws before the overlay's ``Update()`` lands, and
the compositor occasionally samples between the two. Closing it properly means
the native ``DrawSash`` never running at all, which needs a hook this toolkit
does not expose to Python (see the table below for the two that looked like they
would and do not).

Dragging still goes through ``wxSplitterWindow``'s own ``OnMouseEvent``, but
only because the overlay **translates the coordinates** on the way. The overlay
is sized to the band, so it sits at ``(position, 0)`` and a click in the middle
of the sash reaches it as ``x = 3``. Forwarding that untranslated -- which is
what the first version of this overlay did -- tells the splitter the pointer is
3px from its left edge, ``SashHitTest`` says no, and **the sash stops being
draggable at all** while every pixel measurement in this module still passes.
Once the position is mapped back through screen coordinates, wx captures the
mouse, clamps against the minimum pane size and fires
``wxEVT_SPLITTER_SASH_POS_CHANGED`` exactly as before, so the deck workspace's
saved position keeps working with no code of ours in the path.

That is also why ``test_a_real_click_on_the_sash_starts_a_drag`` builds its
events the way wxMSW does -- position relative to the window the pointer is
over, not to the splitter. A test that hands the overlay splitter coordinates
is testing the bug, and passed straight through it.

Two routes that look like they should work do not, and both were measured
rather than read:

===================================  =========================================
route                                result
===================================  =========================================
``SetSashInvisible(True)`` plus a     **no effect.** ``GetSashSize()`` is not
  Python ``GetSashSize()`` override   virtual across the Python boundary: with
                                      the override returning 7, C++ still laid
                                      pane two out for a 0px sash
a ``wx.DelegateRendererNative``       **never called.** wxPython builds no
  subclass overriding                 director for it, so
  ``DrawSplitterSash``, installed     ``wxSplitterWindow::DrawSash`` keeps
  with ``wx.RendererNative.Set``      reaching the native renderer
===================================  =========================================

None of this is visible to a ``PrintWindow`` capture, which re-renders the
widget tree and so reports the pixels the paint handler *intends*. It has to be
read back with a ``ClientDC`` blit or grabbed off the screen, and it has to be
scanned across the **whole** band: the first round of this fix sampled a single
column and reported zero while ``OnSize`` was painting the band end to end.
"""

from __future__ import annotations

import wx

from utils.constants.theme import BORDER_SUBTLE

#: The default style for a splitter in this app: live drag, 3-D sash *metrics*
#: without the 3-D sash *paint*, and no XP theming (which the overlay makes moot
#: but which keeps the metrics stable across Windows versions).
DEFAULT_SPLITTER_STYLE = wx.SP_LIVE_UPDATE | wx.SP_3DSASH | wx.SP_NO_XP_THEME


class _SashOverlay(wx.Window):
    """The window that owns the sash gutter's pixels.

    Sized to the gutter and nothing more. A full-client-area overlay was tried
    first and is **wrong**: ``Lower()`` does not stop it painting over its
    siblings and neither does ``wx.CLIP_SIBLINGS`` -- measured, it filled both
    panes with ``BORDER_SUBTLE`` and wiped the card views out. Sizing it to the
    band makes that impossible by construction.

    Deliberately plain: no ``BG_STYLE_PAINT``, no ``EVT_PAINT``. The background
    colour is the whole mechanism, because it is what wxMSW *erases* with, and
    an erase covers a region no paint handler has reached yet -- which a
    freshly-moved overlay always has.
    """

    def __init__(self, parent: wx.SplitterWindow) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(*BORDER_SUBTLE))
        for event in (
            wx.EVT_LEFT_DOWN,
            wx.EVT_LEFT_UP,
            wx.EVT_LEFT_DCLICK,
            wx.EVT_MOTION,
        ):
            self.Bind(event, self._forward)

    def _forward(self, event: wx.MouseEvent) -> None:
        """Hand the event to the splitter's own ``OnMouseEvent``, **translated**.

        The translation is the whole of this method and it is not optional. A
        mouse event's position is in the coordinates of the window it was
        delivered to, and this overlay is at ``(position, 0)`` -- it is sized to
        the sash band, not to the client area. So a real click in the middle of
        a vertical sash arrives here as ``x = 3``, and forwarding that untouched
        tells ``wxSplitterWindow::OnMouseEvent`` the pointer is 3px from the
        left edge of the splitter. ``SashHitTest`` says no, no drag ever starts,
        and the sash becomes immovable -- with every pixel-colour measurement
        still passing, because the band is painted correctly the whole time.

        Not skipped, because the splitter is the one that should act on it --
        and once wx captures the mouse for a drag, the rest of the gesture goes
        straight to the splitter without passing through here at all.
        """
        splitter = self.GetParent()
        event.SetPosition(splitter.ScreenToClient(self.ClientToScreen(event.GetPosition())))
        event.SetEventObject(splitter)
        splitter.GetEventHandler().ProcessEvent(event)

    def place(
        self,
        splitter: wx.SplitterWindow,
        size: wx.Size | None = None,
        position: int | None = None,
    ) -> None:
        """Cover the sash band and force the erase **now**.

        ``Update()`` rather than letting the move's invalidation settle on its
        own: the whole point is to be on the surface before the next frame is
        presented, and a deferred paint is exactly the gap the native band was
        being caught in.
        """
        if not splitter.IsSplit():
            self.Hide()
            return
        client = size or splitter.GetClientSize()
        if position is None:
            position = splitter.GetSashPosition()
        sash = splitter.GetSashSize()
        if sash <= 0:
            self.Hide()
            return
        if splitter.GetSplitMode() == wx.SPLIT_VERTICAL:
            rect = (position, 0, sash, client.height)
            cursor = wx.CURSOR_SIZEWE
        else:
            rect = (0, position, client.width, sash)
            cursor = wx.CURSOR_SIZENS
        if tuple(self.GetRect()) != rect:
            self.SetSize(*rect)
        self.SetCursor(wx.Cursor(cursor))
        self.Show()
        self.Raise()
        self.Update()


class DarkSplitter(wx.SplitterWindow):
    """A ``wx.SplitterWindow`` whose sash is ``BORDER_SUBTLE`` instead of white.

    ``BORDER_SUBTLE``, not ``BORDER_STRONG``: a sash is a boundary between two
    regions that are each identified by their own content, so WCAG 1.4.11 does
    not apply -- the same call phase 6 made for all ten section cards. The drag
    affordance is the cursor change, which is set on the overlay because that is
    the window the pointer is actually over.

    The colour comes from :class:`_SashOverlay`, a child window sized to the
    sash band (see the module docstring). ``EVT_PAINT`` is still bound and still
    does not skip, which keeps ``wxSplitterWindow::OnPaint`` from running
    ``DrawSash`` -- belt to the overlay's braces, and what covers the moment
    before the overlay is first placed.
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
        self._overlay = _SashOverlay(self)
        self._last_client = wx.Size(0, 0)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        # A notebook tab switch shows the page without resizing it, so EVT_SIZE
        # never fires and the overlay would sit wherever it was last placed
        # while SizeWindows() repaints the native band -- measured as the one
        # frame that survived closing every other path.
        self.Bind(wx.EVT_SHOW, self._on_show)

    # ------------------------------------------------------------------ overlay ------------------------------------------------------------------
    def _place_overlay(self, size: wx.Size | None = None, position: int | None = None) -> None:
        if self._overlay:
            self._overlay.place(self, size, position)

    def SplitHorizontally(self, window1, window2, sashPosition=0) -> bool:
        split = super().SplitHorizontally(window1, window2, sashPosition)
        self._place_overlay()
        return split

    def SplitVertically(self, window1, window2, sashPosition=0) -> bool:
        split = super().SplitVertically(window1, window2, sashPosition)
        self._place_overlay()
        return split

    def Replace(self, winOld, winNew) -> bool:
        replaced = super().Replace(winOld, winNew)
        self._place_overlay()
        return replaced

    def _on_size(self, event: wx.SizeEvent) -> None:
        """Cover the band at the new width, then let wx's own ``OnSize`` run.

        ``event.GetSize()`` rather than ``GetClientSize()``: this handler runs
        *before* ``wxSplitterWindow::OnSize`` (the dynamic table is consulted
        first), which is the only way to be on the surface before that handler's
        inline ``SizeWindows()`` draws the native band. Skipping matters -- it is
        what applies sash gravity and re-clamps against the minimum pane size.
        """
        self._place_overlay(event.GetSize(), self._predicted_position(event.GetSize()))
        self._last_client = wx.Size(*event.GetSize())
        event.Skip()

    def _predicted_position(self, new_client: wx.Size) -> int:
        """Where ``wxSplitterWindow::OnSize`` is about to put the sash.

        It applies gravity before its inline ``SizeWindows()``, so an overlay
        placed at the *current* position is already stale by the time the native
        band is drawn -- measured as 7 of 140 screen frames still showing white
        during side-panel toggles. This mirrors that arithmetic so the overlay
        can be in the right place *first*; ``OnInternalIdle`` still corrects it
        afterwards, so a wrong guess costs a frame of white rather than
        correctness.

        Being a hand-written mirror of wx internals, it drifts silently the
        moment wx changes them -- and nothing else in the app would ever report
        it. ``test_the_gravity_prediction_matches_wx`` pins it against wx's own
        answer (not against a recomputation of this same formula, which would
        pass while both were wrong).
        """
        vertical = self.GetSplitMode() == wx.SPLIT_VERTICAL
        size = new_client.width if vertical else new_client.height
        old = self._last_client.width if vertical else self._last_client.height
        position = self.GetSashPosition()
        if old:
            delta = int((size - old) * self.GetSashGravity())
            if delta:
                position = max(self.GetMinimumPaneSize(), position + delta)
        if position >= size - 5:
            position = max(10, size - 40)
        return position

    def _on_show(self, event: wx.ShowEvent) -> None:
        if event.IsShown():
            self._place_overlay()
        event.Skip()

    def OnInternalIdle(self) -> None:
        """Re-place the overlay after a live drag's deferred ``SizeWindows()``.

        ``OnMouseEvent`` only sets ``m_needUpdating``; the resize -- and the
        native sash draw that ends it -- happen here, so this is the one hook
        that runs after them. It is also the backstop for the sash moving under
        gravity during a resize, which :meth:`_on_size` cannot predict.
        """
        # BEFORE as well as after. ``OnMouseEvent`` has already applied the new
        # sash position by the time idle runs -- it only defers the *resize* --
        # so the overlay can be moved into place before ``SizeWindows()`` draws,
        # which clips the native band instead of racing to cover it.
        self._place_overlay()
        super().OnInternalIdle()
        self._place_overlay()

    def SetSashPosition(self, position: int, redraw: bool = True) -> None:
        """Move the sash, then cover the band ``SizeWindows()`` just drew into."""
        super().SetSashPosition(position, redraw)
        if redraw:
            self._place_overlay()

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        """Fill the client and **do not skip**.

        Skipping would let ``wxSplitterWindow::OnPaint`` run ``DrawSash``
        afterwards. With the overlay in place this handler owns almost no pixels
        -- the panes and the overlay cover the client area between them -- so it
        is insurance, not the mechanism.
        """
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(self._sash_brush)
        dc.Clear()


__all__ = ["DEFAULT_SPLITTER_STYLE", "DarkSplitter"]
