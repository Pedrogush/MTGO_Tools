"""The app's one container idiom: a titled card panel (§4.4 / G2).

What this replaces
------------------
Ten ``wx.StaticBox`` sites across six files. ``wx.StaticBox`` draws the Win95
etched-groove-with-inset-label: a 1px light groove around the region with the
title sitting *on* the groove, breaking it. Under the Windows dark mode phase 1
enabled, wxMSW draws that groove at **#DCDCDC** -- 10.96:1 against
``SURFACE_PANEL``, i.e. purely decorative chrome rendered brighter than most of
the app's body text, and second only to ``wx.Button``'s retired 2px frame as the
loudest thing on screen. Neither the groove colour nor the label's position is
reachable from wx: ``SetForegroundColour`` recolours the *label* and nothing
else, which is why every call site in the tree set it and every call site still
had a near-white frame.

The replacement is the modern card: a flat fill, a 1px subtle border, and a real
heading *above* the card rather than embedded in its edge. Three windows per
site instead of one, and no drawing code at all -- the border is a 1px-larger
panel behind the body panel, because ``wx.Panel``'s background colour is one of
the few things wxMSW honours unconditionally (see :mod:`widgets.stylize`). An
``EVT_PAINT`` border was the obvious alternative and was rejected: it needs
``SetBackgroundStyle(wx.BG_STYLE_PAINT)`` to be safe (phase 5's finding), it
interacts badly with the heavyweight children these sections hold
(``SplitterWindow``, ``WebView``, ``DataViewListCtrl``), and it would be the
ninth "colour call that silently does nothing" risk in a codebase that has
already produced eight.

Which border token
------------------
Every site uses :data:`BORDER_SUBTLE`. Phase 0 put it deliberately below 3:1 and
reserved :data:`BORDER_STRONG` for "a border that is the only affordance
identifying a control". A section card is not a control: it is a grouping
region whose identity comes from the heading above it, and whose extent is
carried by the fill wherever the fill differs from the surrounding surface.
WCAG 1.4.11 applies to boundaries required to *identify* a component, so a
decorative grouping edge is exactly the case ``BORDER_SUBTLE`` was defined for.
Using ``BORDER_STRONG`` here would have re-created the problem the phase is
fixing: ten bright rectangles competing with the content inside them.

Reparenting
-----------
Phase 6 expected ``wx.StaticBoxSizer``'s child reparenting to be the hard part of
this migration. **It is not, because on this toolchain it does not happen.**
Probed on wxPython 4.2.4 / wxWidgets 3.2.8 (msw): adding a window parented to the
box's *parent* to a ``wx.StaticBoxSizer`` leaves ``GetParent()`` untouched, before
and after ``Layout``, and the window still renders correctly inside the box. The
documented "children of a wxStaticBox should be created as children of the box"
guidance is a should, not an enforcement, and the tree proves it: of the ten
sites, some parented children to the ``StaticBox``, some to
``sizer.GetStaticBox()``, and the radar's two lists parented theirs to the
*frame* -- and all three rendered identically.

What that means for the migration is that it was mechanical but not blind:
because there was no single convention to rewrite, each site had to be read to
find out which window its children were actually hanging off.
:attr:`SectionPanel.body` exists so that there is one answer from here on, and it
is greppable.
"""

from __future__ import annotations

import wx

from utils.constants import BORDER_SUBTLE, SPACE_SM, SPACE_XS
from widgets.stylize import stylize_label, surface_colour

#: Width of the card's border, in pixels. One. The whole point is that it is a
#: hairline and not a groove.
SECTION_BORDER_WIDTH = 1


class SectionPanel(wx.Panel):
    """A titled card: heading, then a flat filled panel with a 1px border.

    Children go into :attr:`body` (as their ``parent``) and into :attr:`sizer`
    (as their layout slot)::

        section = SectionPanel(parent, title=self._t("app.label.card_panel"))
        self.card_panel = CardPanel(section.body, ...)
        section.sizer.Add(self.card_panel, 1, wx.EXPAND)

    :param title: the heading above the card. ``None`` draws no heading, for a
        region whose content already names it -- the deck workspace, whose
        notebook tab strip is the label.
    :param surface: the card's fill.
    :param outer_surface: the surface the *heading* sits on, i.e. whatever the
        parent's background is. Only matters because ``wx.StaticText`` paints its
        own background rather than letting the parent show through.
    :param padding: inset between the border and the content.
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        title: str | None = None,
        surface: str = "panel",
        outer_surface: str = "base",
        padding: int = SPACE_SM,
        orientation: int = wx.VERTICAL,
        heading_level: str = "heading",
        heading_gap: int = SPACE_XS,
        border_colour: tuple[int, int, int] = BORDER_SUBTLE,
    ) -> None:
        super().__init__(parent)
        self._surface = surface
        self.SetBackgroundColour(surface_colour(outer_surface))

        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        self.heading: wx.StaticText | None = None
        if title is not None:
            self.heading = wx.StaticText(self, label=title)
            stylize_label(self.heading, level=heading_level, surface=outer_surface, tone="primary")
            outer.Add(self.heading, 0, wx.BOTTOM, heading_gap)

        # The border is a panel painted in the border colour with the body panel
        # inset 1px inside it. No paint handler, no BG_STYLE_PAINT, nothing that
        # can silently not apply.
        self._frame = wx.Panel(self)
        self._frame.SetBackgroundColour(wx.Colour(*border_colour))
        outer.Add(self._frame, 1, wx.EXPAND)

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        self._frame.SetSizer(frame_sizer)

        self.body = wx.Panel(self._frame)
        self.body.SetBackgroundColour(surface_colour(surface))
        frame_sizer.Add(self.body, 1, wx.EXPAND | wx.ALL, SECTION_BORDER_WIDTH)

        self.sizer = wx.BoxSizer(orientation)
        self._padding = padding
        if padding:
            inner = wx.BoxSizer(wx.VERTICAL)
            inner.Add(self.sizer, 1, wx.EXPAND | wx.ALL, padding)
            self.body.SetSizer(inner)
        else:
            self.body.SetSizer(self.sizer)

    # -- convenience ----------------------------------------------------
    def add(self, window, proportion: int = 0, flag: int = 0, border: int = 0):
        """``self.sizer.Add`` — so a call site never has to say ``.sizer`` twice."""
        return self.sizer.Add(window, proportion, flag, border)

    def set_title(self, title: str) -> None:
        """Re-label the heading. No-op on a section built without one."""
        if self.heading is not None:
            self.heading.SetLabel(title)

    @property
    def surface(self) -> str:
        """The name of the card's fill surface, for children that need to match it."""
        return self._surface


__all__ = ["SECTION_BORDER_WIDTH", "SectionPanel"]
