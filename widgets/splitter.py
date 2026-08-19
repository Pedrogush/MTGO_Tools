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
    """

    def __init__(self, parent: wx.Window, *args, **kwargs) -> None:
        kwargs.setdefault("style", DEFAULT_SPLITTER_STYLE)
        super().__init__(parent, *args, **kwargs)
        # Required by wx.AutoBufferedPaintDC: without it wxMSW leaves the
        # backing store alone and a window that paints everything itself shows
        # whatever was last blitted there (phase 5's finding).
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*BORDER_SUBTLE))
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        """Fill the gutter and **do not skip**.

        Skipping would let ``wxSplitterWindow::OnPaint`` run ``DrawSash``
        afterwards and repaint the white band on top, which is the whole thing
        being avoided.
        """
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(*BORDER_SUBTLE)))
        dc.Clear()


__all__ = ["DEFAULT_SPLITTER_STYLE", "DarkSplitter"]
