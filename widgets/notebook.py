"""The app's one notebook widget.

wxMSW's ``wx.Notebook`` is a native tab control: it ignores
``SetBackgroundColour`` and ``SetForegroundColour`` entirely, so a dark app gets a
white tab strip with black text and there is no colour call that fixes it. The
only route to a dark notebook is a generic (fully wx-drawn) one, which is what
``wx.lib.agw.flatnotebook`` is — and what the deck workspace has always used.

Phase 1 (issue #962, C3 / §4.3) removes the last ``wx.Notebook`` in the tree, in
the card panel, which sat about 400px from a themed ``FlatNotebook``. This module
is the shared factory so the two cannot drift apart again.

Phase 6 (§4.4 / G2) adds :class:`_ThemedTabRenderer`, because "themed" turned out
to stop at the colours FlatNotebook exposes setters for. Measured on screen, the
plain renderer also draws three things that no setter reaches:

* a **2px pure-white line across the full width of the tab strip's bottom edge**
  (``#FFFFFF``, 15.0:1 on ``SURFACE_PANEL`` -- the loudest chrome left in the app
  after phase 2 retired ``wx.Button``'s frame). It comes from
  ``FNBRenderer.DrawTabsLine``, which fills two rectangles with
  ``PageContainer.GetSingleLineBorderColour()`` -- and that method returns a
  hard-coded ``wx.WHITE`` for every style except ``FNB_FANCY_TABS``, which phase 1
  removed for unrelated reasons;
* a ``#A0A0A0`` (``COLOR_BTNSHADOW``) outline around the **active tab**, and
* ``#A0A0A0`` vertical separators between the inactive tabs.

The last two come from ``DrawTabs`` setting the DC pen to ``COLOR_BTNSHADOW``
before it calls ``DrawTab``; ``PageContainer._colourBorder`` is settable but is
read only by the VC8 renderer, so it is not a way in. Subclassing the renderer
and installing it on the notebook's own ``FNBRendererMgr`` is -- and it is a
strictly smaller change than the own-drawn tab control the alternative implied,
because FlatNotebook keeps its geometry, hit-testing, scrolling and drag-and-drop.
"""

from __future__ import annotations

import wx
from wx.lib.agw import flatnotebook as fnb

from utils.constants.theme import (
    BORDER_SUBTLE,
    SELECTION_BORDER,
    SELECTION_FILL_ON_PANEL,
    SELECTION_TEXT,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

#: No close button, no navigation arrows, and — importantly — **not**
#: ``FNB_FANCY_TABS``. Fancy tabs draw the active tab as a light system gradient
#: and ignore ``SetActiveTabColour`` entirely, so the deck workspace has been
#: rendering a white tab on a dark strip ever since it set that colour. The plain
#: tab renderer honours it, which is the difference between "themed" and "themed
#: except for the one tab you are looking at".
#:
#: ``FNB_SMART_TABS`` is deliberately not in the default either — it adds a
#: Ctrl+Tab overlay that only makes sense for the multi-tab deck workspace, which
#: passes its own style.
DEFAULT_AGW_STYLE = fnb.FNB_NO_X_BUTTON | fnb.FNB_NO_NAV_BUTTONS


class _ThemedTabRenderer(fnb.FNBRendererDefault):
    """The plain renderer with every unreachable colour replaced by a token.

    Only the chrome is overridden. Tab geometry, sizing, the ``x`` button, the
    nav arrows, focus rectangles and every hit-test still come from
    ``FNBRendererDefault``, so the strip keeps behaving exactly as it did.

    The tab *labels* deliberately still come from ``wx.SYS_DEFAULT_GUI_FONT``
    (9pt) rather than the app's 10pt base: ``CalcTabWidth`` and ``CalcTabHeight``
    measure with that font, so moving the label onto the type ladder means moving
    the strip's own geometry with it. That is typography, not container chrome --
    noted for whichever phase owns the remaining type audit.
    """

    def DrawTabsLine(self, pageContainer, dc, selTabX1=-1, selTabX2=-1):  # noqa: N802
        """One hairline under the strip, instead of a white 2px band and a grey one.

        The base implementation draws two full-width rectangles in
        ``GetSingleLineBorderColour()`` (hard-coded ``wx.WHITE``) and one in
        ``COLOR_BTNSHADOW``, then paints over the left, top and right edges with
        the tab-area colour -- which is why only the bottom edge survives, and
        why it survives at full white.
        """
        rect = pageContainer.GetClientRect()
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(wx.Colour(*BORDER_SUBTLE)))
        dc.DrawLine(0, rect.height - 1, rect.width, rect.height - 1)

    def DrawTab(  # noqa: N802
        self, pageContainer, dc, posx, tabIdx, tabWidth, tabHeight, btnStatus
    ):
        """A flat filled block for the active tab; nothing at all for the rest.

        ``FNBRendererDefault`` draws the active tab as an angled polygon stroked
        in ``COLOR_BTNSHADOW`` with a hard-coded white line along its base, and
        separates inactive tabs with ``COLOR_BTNSHADOW`` verticals. All four of
        those colours are unreachable, so the whole method is replaced rather
        than wrapped -- there is no pen to swap that the white line would honour.
        """
        pc = pageContainer
        selected = tabIdx == pc.GetSelection()
        top = fnb.VERTICAL_BORDER_PADDING
        height = tabHeight - top

        if selected:
            dc.SetPen(wx.Pen(wx.Colour(*SELECTION_BORDER)))
            dc.SetBrush(wx.Brush(wx.Colour(*SELECTION_FILL_ON_PANEL)))
            dc.DrawRectangle(int(posx), int(top), int(tabWidth), int(height))
        else:
            dc.SetTextForeground(pc.GetParent().GetNonActiveTabTextColour())

        # Same text origin the base renderer uses, so a themed strip and an
        # unthemed one place their labels identically.
        text_offset = pc._pParent.GetPadding() + 2
        dc.DrawText(pc.GetPageText(tabIdx), int(posx + text_offset), int(top + 4))

        if pc.HasAGWFlag(fnb.FNB_X_ON_TAB) and selected:
            text_width, _ = dc.GetTextExtent(pc.GetPageText(tabIdx))
            self.DrawTabX(
                pc,
                dc,
                wx.Rect(int(posx + text_offset + text_width + 1), int(top + 4), 16, 16),
                tabIdx,
                btnStatus,
            )


def stylize_notebook(notebook: fnb.FlatNotebook) -> None:
    """Paint a ``FlatNotebook`` with the app's tokens.

    The active tab uses the **selection** token, not a saturated accent fill.
    Phase 1 dropped ``FNB_FANCY_TABS``, which made ``SetActiveTabColour`` take
    effect for the first time and turned the active tab into a solid
    ``ACCENT_PRIMARY`` block in two places. Phase 2 owns the accent budget and
    made that call: an active tab is a *selected item among peers* — exactly what
    the deck rows, the card views and the Grid/Table/Pile toggles are — so it gets
    the one selection idiom rather than a private one. Giving it the saturated
    fill would also have put the loudest colour in the app immediately above the
    card art it competes with.

    ``SELECTION_TEXT`` on ``SELECTION_FILL_ON_PANEL`` measures 4.91:1; the plain
    tab renderer bolds the active label, so the state survives without colour.
    """
    notebook.SetTabAreaColour(wx.Colour(*SURFACE_PANEL))
    notebook.SetActiveTabColour(wx.Colour(*SELECTION_FILL_ON_PANEL))
    notebook.SetNonActiveTabTextColour(wx.Colour(*TEXT_SECONDARY))
    notebook.SetActiveTabTextColour(wx.Colour(*SELECTION_TEXT))
    notebook.SetBackgroundColour(wx.Colour(*SURFACE_BASE))
    notebook.SetForegroundColour(wx.Colour(*TEXT_PRIMARY))
    # The *tab container* is a separate window from the notebook, and
    # ``FNBRenderer.DrawTabs`` strokes a 1px rectangle around the whole strip in
    # ``PageContainer.GetBackgroundColour()``. Left at the wx default that is
    # ``#F0F0F0`` -- so a themed notebook still came framed in a near-white
    # hairline wherever the container did not happen to inherit a dark parent.
    # ``SetTabAreaColour`` does not reach it: it sets ``_tabAreaColour``, which
    # is the *brush*, not the pen.
    notebook._pages.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))
    install_themed_renderer(notebook)


def install_themed_renderer(notebook: fnb.FlatNotebook) -> _ThemedTabRenderer:
    """Swap the plain renderer for the themed one on this notebook only.

    ``FNBRendererMgr`` is constructed per ``PageContainer``, so replacing the
    ``-1`` (default) entry is scoped to one notebook and leaves the library's
    module state alone. Nothing this renderer overrides caches geometry, so
    installing it after construction is safe -- ``CalcTabHeight``'s cache and the
    strip's size hint both belong to methods that are *not* overridden.
    """
    renderer = _ThemedTabRenderer()
    notebook._pages._mgr._renderers[-1] = renderer
    return renderer


def make_flat_notebook(
    parent: wx.Window,
    *,
    agw_style: int | None = None,
) -> fnb.FlatNotebook:
    """Build a themed ``FlatNotebook``. The only notebook constructor in the app."""
    notebook = fnb.FlatNotebook(
        parent,
        agwStyle=DEFAULT_AGW_STYLE if agw_style is None else agw_style,
    )
    stylize_notebook(notebook)
    return notebook


__all__ = [
    "DEFAULT_AGW_STYLE",
    "install_themed_renderer",
    "make_flat_notebook",
    "stylize_notebook",
]
