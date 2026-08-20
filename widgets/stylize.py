"""The app's styling layer: one place that turns design tokens into wx widget state.

Every visual decision — which surface a widget sits on, which text level it is,
which button role it plays — is expressed here and nowhere else. The tokens
themselves live in :mod:`utils.constants.theme`.

Backwards compatibility
-----------------------
All four original entry points keep their original signatures, and every new
parameter defaults to reproducing today's rendering. The new machinery is opt-in
so that phase 0 can land without moving a single pixel:

* ``stylize_label(label)`` / ``stylize_label(label, True)`` behave exactly as
  before, including the blanket bold. Passing ``level=`` switches the label onto
  the type scale, where **only headings are bold** — that is the fix for the root
  cause that bold marked nothing. Phase 3 audited the explicit sites: 21 of them
  in 18 files at the time (not the 31/21 the plan carried -- phase 2 had already
  deleted four copy-pasted local ``_stylize_button`` helpers), and 19 are gone.
  The two that remain are mana-glyph rasterisation, not text hierarchy.
* ``stylize_button(button)`` still paints the saturated accent fill; ``kind=``
  selects secondary / ghost / danger / success variants.
* ``stylize_choice`` now themes the dropdown dark (phase 1, finding C1). See the
  comment there for why that needs more than two colour calls on wxMSW.

What wxMSW actually honours
---------------------------
Measured on wxWidgets 3.2.8 / wxPython 4.2.4 by screenshotting a probe frame,
not assumed. This table is the constraint every later phase inherits:

===================  ==================================================
widget               behaviour
===================  ==================================================
``wx.StaticText``    background + foreground honoured
``wx.TextCtrl``      background + foreground honoured **while enabled**. A
                     **disabled** one discards them: ``Enable(False)`` makes
                     wxMSW paint the client area ``#F0F0F0`` and nothing gets
                     it back -- setting the colour after ``Disable()``,
                     :func:`disable_native_theme` and Windows' own dark mode
                     were all measured and all leave the same near-white block.
                     ``SetEditable(False)`` *does* keep the dark fill, which is
                     what :meth:`widgets.input_frame.InputFrame.EnableInput`
                     uses to render a disabled field. Read-only is also the one
                     state wxMSW drops out of **tab order**:
                     ``CanAcceptFocusFromKeyboard()`` is ``False`` for a
                     ``wx.TE_READONLY`` field and for a disabled one. The border
                     is non-client area and unreachable -- see the ``client
                     edge`` row and :mod:`widgets.input_frame`
``wx.BoxSizer``      not a widget, but the row-overflow rule belongs with the
                     other silent failures. When a horizontal row's minimum
                     widths exceed the client, wxSizer does **not** shrink the
                     items proportionally and does not clip the row as a whole:
                     every item keeps its full minimum except the **last**, which
                     absorbs the entire deficit. Measured on the deck-workspace
                     header in pt-BR at the window's 1200px floor -- the row
                     wanted 551px in a 506px panel, the first seven controls
                     rendered at exactly their minimums, and the printing button
                     was painted 14px wide against a 59px minimum. So "does this
                     row fit" cannot be answered by looking at any control except
                     the last one, and a row of fixed-width controls needs one
                     deliberately flexible member (proportion 1 plus a floor)
                     rather than an ``AddStretchSpacer``, which yields nothing
                     back once the slack is gone.
                     The **vertical** case is worse, and phase 8 measured it on
                     the deck builder: when the fixed items alone exceed the
                     client, the proportional item's share goes *negative* and
                     is clamped to 0 -- so the one item that was meant to absorb
                     the slack disappears entirely -- and every item after it is
                     still laid out, below the pane's bottom edge, with no
                     scrollbar and no clipping to say so. The results list
                     rendered at exactly 0px and "Showing N cards." was simply
                     not on screen. There is no BoxSizer expression of "shrink
                     this one first"; the fix is a ``wxScrolled`` parent, which
                     lays out to ``max(client, virtual)``
``wx.Button``        background + foreground honoured. The border is a **2px
                     light-grey frame** (``#ADADAD`` outside, ``#E1E1E1``
                     inside) drawn by the theme, identical for every background
                     and unreachable from wx — but ``wx.BORDER_NONE`` deletes
                     it, and the flag can be set *after* construction with
                     ``SetWindowStyleFlag``. See
                     :func:`strip_native_button_frame`. A **disabled** button
                     keeps its background at full saturation; only the label
                     greys, so a disabled state has to repaint the fill
``wx.CheckBox``      label + surround honoured; the box **glyph** is drawn
                     by ``wxRendererNative`` from the light ``BUTTON``
                     theme class and is not reachable at all.
                     ``wx.lib.checkbox.GenCheckBox`` is **not** a way out: it
                     builds its bitmaps from the same
                     ``wxRendererNative.DrawCheckBox`` and renders the identical
                     white square. Replaced by the own-drawn
                     :class:`widgets.checkbox.DarkCheckBox`
``wx.SpinCtrl``      honoured on the edit field; the arrows are a separate
                     ``msctls_updown32`` HWND that stays light under every
                     theme tried, Windows dark mode included. **Two HWNDs, and
                     wx hands back the wrong one**: ``GetHandle()`` returns the
                     up-down, so ``wx.BORDER_NONE`` and
                     :func:`strip_native_client_edge` land on the arrows -- which
                     never had a client edge -- and the ``#FFFFFF`` hairline
                     around the *field* survives, unchanged, pixel for pixel.
                     The field is the up-down's **buddy**, reachable only via
                     ``UDM_GETBUDDY``; see
                     :func:`widgets.native_dark.strip_spin_buddy_client_edge`
``wx.Gauge``         **both silently ignored**, and Windows' own dark mode does
                     **not** reach it -- so unlike ``wx.Choice`` there is no OS
                     route. Measured across six variants: untouched, bg+fg,
                     ``DarkMode_Explorer``, ``DarkMode_Explorer::PROGRESS`` and
                     ``wx.BORDER_NONE`` all render the identical ``#E0E0E0``
                     trough with the Windows green fill. Dropping it out of
                     visual styles is the only thing that works, and then both
                     colours land -- see :func:`stylize_gauge`
``wx.Choice``        **both silently ignored** while the control is
                     visual-styled; dark via Windows' dark mode, or via
                     :func:`disable_native_theme` as a fallback
``wx.ComboBox``      same as ``wx.Choice``
``wx.ListCtrl``      rows honoured; the header is a native ``SysHeader32``
                     and ignores everything wx can set. ``SetHeaderAttr``
                     returns ``True`` and applies only the *foreground*,
                     which makes the white header worse, not better.
                     Dark only via Windows' own dark mode. The **selected row**
                     is OS-owned and ``SetItemBackgroundColour`` on it is
                     overpainted in every state: with focus it is the system
                     accent (``#0078D7``, 3.34:1 on ``SURFACE_PANEL``), without
                     focus it is ``#F0F0F0`` -- a near-white band, 13.2:1. Both
                     are measured under Windows dark mode; the review's
                     "~1.1:1 tint" was the pre-dark-mode rendering and no longer
                     describes it. Neither is reachable, so a list that needs
                     the app's selection token needs a different control -- see
                     :mod:`widgets.grids.data_grid`
``wx.grid.Grid``     cell and label colours honoured. The **selection** is only
                     half ours: with focus wxGrid fills with
                     ``SetSelectionBackground``, without focus it draws
                     ``COLOR_BTNSHADOW`` (``#A0A0A0``) and ignores the colour
                     entirely. A cell renderer that paints its own background
                     wins in both states, because wxGrid hands the whole cell
                     to the renderer -- that is how the deck table view has
                     always got a dark selection, and what
                     :mod:`widgets.grids.data_grid` generalises.
                     ``SetColLabelAlignment`` is **grid-wide** (so it cannot
                     right-align a numeric column's header alone) and
                     **overriding ``DrawColLabel`` from Python does nothing** --
                     a subclass counting its own calls records zero after a full
                     paint. Per-column header alignment therefore needs an
                     own-drawn header window. ``GetBestSize()`` is the grid's
                     **entire scrollable content** -- every column's width and
                     every row's height -- which is not a minimum in any useful
                     sense for a scrolling control and propagates straight up
                     through whatever contains it. Measured in phase 8: visiting
                     the deck workspace's table view once with a 60-card deck
                     took the *frame's* enforced minimum height from 882 to
                     **1461px**, after which the window could not be made
                     smaller again. Pin ``SetMinSize`` on the grid itself
``wx.Simplebook``    and every other ``wxBookCtrlBase``: its own best size is the
                     max over **all** its pages, hidden ones included, and it
                     asks each page for ``GetBestSize()`` -- never for
                     ``GetEffectiveMinSize()``. So a hidden page sets the book's
                     minimum, and ``SetMinSize`` **on a page does not bound the
                     book**; both were measured in phase 8 while chasing the
                     wx.grid row above. The floor has to go one level further
                     down, on a child of the page, because a window that owns a
                     sizer *does* take its best size from that sizer's CalcMin
                     and CalcMin does consult each item's effective minimum
``wx.ScrolledWindow``
                     reports ``1x1`` as its best size when it has no child
                     window (the deck grid and pile views, which draw
                     themselves), and its child's best size when it has one --
                     which is how the table view's grid escaped. With a sizer it
                     lays out to ``max(client, virtual)`` after ``FitInside``,
                     which is the one wx idiom that expresses "shrink this
                     region before the ones around it".
                     Four more, all measured in phase 8 while snapping the card
                     views to row boundaries. (1) At a **1px scroll rate** the
                     scrollbar's *arrow buttons* move one pixel, so on a view
                     whose rows are 232px they are effectively dead; they have
                     to be handled rather than left to wx. (2) A custom-drawn
                     one **takes focus when clicked** on wxMSW with no
                     ``SetFocus`` anywhere in the tree, so wx's keyboard
                     scrolling (Page/arrow/Home/End) is live on it whether or
                     not anything asked for it -- verified with real Win32
                     keystrokes. (3) **Physical scrolling does not strand
                     viewport-fixed chrome.** wx scrolls by blitting and
                     invalidating only the exposed strip, which should leave
                     anything painted relative to the *viewport* (an edge fade)
                     stale outside that strip. Measured on both card views at
                     scroll deltas from 3px to 232px: the scroll path renders
                     **byte-identical** to a full ``Refresh``, so wxMSW is
                     invalidating the whole client for these windows. Worth
                     re-measuring rather than assuming for any window that gains
                     children. (4) A synthetic ``WM_VSCROLL`` **cannot drive a
                     thumb drag**: wxMSW reads the position from
                     ``GetScrollInfo``, not from the message's ``HIWORD``, so
                     ``SB_THUMBPOSITION`` sent from another process scrolls to
                     wherever the real thumb happens to be (0). ``SB_LINE*`` and
                     ``SB_PAGE*`` do work. Automating a thumb drag needs real
                     mouse input
``wx.Bitmap`` alpha  a bitmap carrying an alpha channel (built via
                     ``wx.Image.SetAlpha``) is alpha-blended correctly by
                     ``wx.DC.DrawBitmap(bmp, x, y, True)`` **onto an
                     ``AutoBufferedPaintDC``** -- the working route for an
                     overlay gradient. ``wx.GraphicsContext.Create(dc)`` also
                     works but inherits whatever transform ``PrepareDC`` left on
                     the DC, so "draw this at the bottom of the client" becomes
                     a transform question rather than a measurement; the bitmap
                     needs no such reasoning and caches. Either way
                     ``SetBackgroundStyle(wx.BG_STYLE_PAINT)`` is the
                     precondition (see the ``wx.*BufferedPaintDC`` note): without
                     it wxMSW's erase-background pass owns the client and
                     everything drawn into the buffer is silently discarded
``wx.dataview``      ``DataViewListCtrl`` draws its own alternate-row bands from
                     the light theme, so half the rows come back light grey on a
                     dark surface. Not a way out of the ListCtrl selection
                     problem
``wx.html.HtmlWindow``
                     renders roughly HTML 3.2 and is **not** a viable chart
                     fallback: it ignores ``bgcolor`` on a ``<table>``,
                     collapses a cell with no text in it, and ignores ``height``
                     on ``<td>``. A bar chart emitted into it draws every label
                     and **no bars at all** -- verified by screenshot, which is
                     the only way this shows up. Own-draw instead (see
                     :mod:`widgets.charts.painter`)
``wx.html2.WebView`` needs the Edge WebView2 runtime; ``WebView.New`` raises (or
                     returns ``None``) without it, so every construction site
                     needs a fallback. It also takes a light 1px client edge
                     unless constructed with ``wx.BORDER_NONE``
``wx.ListBox``       rows honoured; it takes the same near-white sunken client
                     edge as ``wx.TextCtrl`` -- see the ``client edge`` row
``wx.Notebook``      both ignored, **and Windows' dark mode does not reach
                     it either** — migration to ``FlatNotebook`` is the
                     only fix (see :mod:`widgets.notebook`)
``FlatNotebook``     the generic replacement, and generic is not the same as
                     reachable. Three colours have no setter and no
                     ``SystemSettings`` route: the tab strip's bottom edge is a
                     **2px ``#FFFFFF``** band from ``DrawTabsLine``, whose
                     ``GetSingleLineBorderColour()`` is a hard-coded ``wx.WHITE``
                     for every style except ``FNB_FANCY_TABS``; the active tab's
                     outline and the inactive tabs' separators are
                     ``COLOR_BTNSHADOW``, set on the DC by ``DrawTabs``. A
                     renderer subclass installed on the notebook's own
                     ``FNBRendererMgr`` reaches all three. Separately,
                     ``DrawTabs`` strokes the strip's outline in the **tab
                     container's** background -- a different window from the
                     notebook, defaulting to ``#F0F0F0`` -- so
                     ``notebook._pages.SetBackgroundColour`` is required on top
                     of ``SetTabAreaColour``. Tab labels are measured and drawn
                     with ``SYS_DEFAULT_GUI_FONT`` in **three** methods --
                     ``CalcTabWidth``, ``CalcTabHeight`` and ``DrawTabs`` -- each
                     of which builds the font inside its own body, so there is
                     nothing to pass in and all three have to be overridden
                     together or the strip measures itself with one font and
                     draws with another. Phase 6b did that; see
                     :mod:`widgets.notebook`
``wx.Panel``         two traps, both found in phase 6c and both silent.
                     (1) ``wx.Panel``'s default style is ``wxTAB_TRAVERSAL``,
                     and a ``style=`` argument **replaces** it rather than
                     adding to it -- so ``wx.Panel(parent,
                     style=wx.BORDER_NONE)``, an idiom already in the tree, is a
                     traversal dead end. (2) ``AcceptsFocusFromKeyboard()``
                     answers "have I any focusable children" from the children's
                     ``AcceptsFocus``, which is ``True`` for a read-only or
                     disabled ``wx.TextCtrl`` even though their
                     ``CanAcceptFocusFromKeyboard`` is ``False``. A panel
                     wrapping one therefore becomes a **tab stop itself**: focus
                     lands on a bare panel with no visible indicator. Override
                     ``AcceptsFocusFromKeyboard`` to delegate to the child;
                     overriding ``AcceptsFocus`` as well is wrong and was
                     measured -- traversal then stops descending into the panel
                     at all and skips the child even when it is focusable
``wx.StaticBox``     ``SetForegroundColour`` recolours **only the label**;
                     ``SetBackgroundColour`` fills the interior. The etched
                     groove itself is drawn by the theme at **``#DCDCDC``**
                     (10.96:1 on ``SURFACE_PANEL``) and is not reachable at all,
                     and neither is the label's position on it. Every one of the
                     ten sites in the tree set both colours and every one still
                     had a near-white frame. ``wx.StaticBoxSizer`` does **not**
                     reparent what is added to it on this toolchain (probed on
                     4.2.4 / 3.2.8): a child parented to the box's parent keeps
                     that parent and still renders inside the box, which is why
                     the ten sites used three different conventions. Replaced by
                     :class:`widgets.section.SectionPanel`
client edge          ``wx.TextCtrl``, ``wx.ListBox`` and ``wx.dataview``'s
                     controls default to a sunken border Windows draws at
                     **``#FFFFFF``** with a ``#828790`` outer line, untouched by
                     process dark mode, by ``SetBackgroundColour`` or by
                     ``SetWindowTheme``. ``wx.BORDER_NONE`` deletes it, from the
                     constructor **and** post-construction via
                     ``SetWindowStyleFlag``, but on a composite it must be applied
                     to the window that owns the edge (``TreeListCtrl`` wraps a
                     ``DataViewCtrl``; the wrapper is not it). **Correction from
                     phase 6b:** phase 6 recorded that stripping a
                     ``wx.TextCtrl``'s edge leaves the dark-mode edit border
                     rather than nothing. Measured on the running builder, it
                     leaves **nothing** -- the field renders as ``SURFACE_ALT``
                     straight onto its parent, which on ``SURFACE_PANEL`` is
                     1.10:1. The edge itself is a ``#FFFFFF`` line over
                     ``#7A7A7A``, i.e. ~21:1, so removing it is still right.
                     **Phase 6c answered what replaces it**: an own-drawn
                     ``BORDER_STRONG`` ring painted by the field's parent, since
                     the boundary is the sole marker of the control and phase 0
                     puts that case at >= 3:1. See :mod:`widgets.input_frame`;
                     every ``wx.TextCtrl`` in the app is built through it and
                     ``tests/test_widget_audit.py`` fails on one that is not
``wx.SplitterWindow``
                     the **sash** is drawn by ``wxRendererNative`` and is
                     unreachable: ``SetBackgroundColour``,
                     :func:`disable_native_theme` and every ``SP_*`` flag
                     combination leave it light. With ``SP_3DSASH`` it is 7px of
                     ``#F0F0F0`` around a ``#FFFFFF`` centre line; without the
                     3-D flags it is 4px and still light.
                     ``SetSashInvisible(True)`` *is* dark and is a trap -- it
                     also sets ``GetSashSize()`` to 0, and the drag hit test
                     comes from that size, so the split silently stops being
                     draggable. Own-drawn via ``EVT_PAINT`` (uniquely safe on a
                     splitter: the panes are child windows, so the only pixels
                     the handler owns are the gutter). See
                     :mod:`widgets.splitter`
``wx.StatusBar``     background honoured, **foreground silently ignored**
                     — hence :mod:`widgets.status_bar`
``wx.StaticLine``    **neither honoured**, and a ``wx.LI_VERTICAL`` one draws in
                     the native *etched* colour, which on ``SURFACE_PANEL``
                     comes out near-white — brighter than any other chrome on
                     that surface. The two horizontal StaticLines already in the
                     tree read as dark and made this look safe; a vertical rule
                     beside text does not get lost the way a horizontal one
                     does. Use :func:`create_divider` (a 1px ``wx.Panel``,
                     whose background *is* honoured) for any rule that has to
                     match the theme
``wx.StaticText``    background + foreground honoured. Two traps:
                     ``wx.ST_ELLIPSIZE_*`` is only picked up from the
                     **constructor**, not from a later ``SetWindowStyleFlag``;
                     and without ``wx.ST_NO_AUTORESIZE`` a ``SetLabel``
                     **resizes the control to fit the new text**, which silently
                     defeats both ``wx.ALIGN_RIGHT`` (the box hugs the string,
                     so there is nothing to align within) and ellipsization
                     (a control that resized to its own text always fits). See
                     :func:`create_status_label`
``wx.ToggleButton``  background + foreground honoured; the *checked* state adds
                     a 1px ring in the **system** accent colour, which is a user
                     setting rather than ours. Unused: the app's toggles are
                     plain buttons re-stylized on state change
scrollbars           not reachable from wx at all; dark process-wide via
                     :func:`widgets.native_dark.enable_app_dark_mode`
===================  ==================================================

Anything marked "via Windows' own dark mode" goes through
:mod:`widgets.native_dark`, which is enabled once at startup.

What wx will **not** tell you
-----------------------------
``wx.Window.GetBackgroundColour()`` is not an oracle for "what is this widget
painted". A child that has never had one set reports the *system* default
(``#F0F0F0``) whatever its parent is, and ``InheritsBackgroundColour()`` returns
``False`` for it as well -- so there is no wx-level way to tell "explicitly
light" from "inherits a dark parent". Phase 6b tried to build a live-tree guard
on it and got 47 offenders, every one of them a widget that renders dark. Fonts
are the opposite: ``GetFont()`` *does* report the inherited value, which is why
:mod:`tests.ui.test_live_widget_audit` can check the type ladder on a running
window but not the palette.

What ``SetMinSize`` actually does (measured in phase 8)
------------------------------------------------------
``GetEffectiveMinSize()`` consults ``GetBestSize()`` **only for the components
of the min size left at ``wxDefaultCoord``**, per axis. So ``SetMinSize((-1,
240))`` pins the height and lets content set the width -- which is how the card
inspector's minimum width came to depend on which card was loaded -- while
``SetMinSize((300, 240))`` stops best size being consulted at all. If a widget's
content must not be allowed to set a dimension, that dimension has to carry a
real number, not -1.

What wxMSW does with **fonts and sizes** (measured in phase 3)
--------------------------------------------------------------
* A child inherits its parent's font **at construction time only**, at every
  depth and across every widget class the app uses -- ``StaticText``,
  ``Button``, ``TextCtrl``, ``Choice``, ``CheckBox``, ``ListCtrl``,
  ``SpinCtrl``, ``StaticBox``, ``ListBox`` all reported the parent's 10pt.
* A widget that already exists when its parent's font changes keeps the old
  size, **and so does a widget created afterwards** if there is an intermediate
  panel: the panel captured its own font at *its* construction, and new children
  inherit the panel, not the frame. So the call really does have to be the first
  thing after ``super().__init__()``, not merely "before the widget you care
  about".
* **Top-level windows never inherit.** ``wx.Frame``, ``wx.Dialog`` and
  ``wx.MiniFrame`` constructed with a 10pt parent all reported the 9pt system
  default. Hence one :func:`apply_base_font` per top-level window (18 of them).
* ``wx.BU_EXACTFIT`` is the *only* way past that floor, and it overshoots in
  the other direction: it sizes a button to its text extent plus roughly 2px, so
  the deck workspace's ``Grid``/``Table``/``Pile`` toggles measured 30x18. A
  compact button therefore needs its size stated explicitly on top of the flag;
  see :func:`size_compact_button`.
* ``wx.Button.GetBestSize()`` has a **hard floor of 75x23 at 9pt and 75x25 at
  10pt, whatever the label** -- it is the Win32 default button size, not a
  text measurement. Any button given an explicit size under that reports a
  best-size deficit even when its label fits comfortably, so "best size >
  current size" is necessary but not sufficient evidence of clipping on a
  button; look at the pixels too. Button chrome around a label measures ~24px
  horizontally, which is the number to size a labelled button by.
* Text the app paints itself with ``dc.SetFont()`` is invisible to font
  inheritance. :func:`type_font` exists for exactly those surfaces.

Own-drawn surfaces
------------------
Any window that paints itself with ``wx.BufferedPaintDC`` /
``wx.AutoBufferedPaintDC`` must also call
``SetBackgroundStyle(wx.BG_STYLE_PAINT)``. Without it wxMSW leaves the backing
store alone, so a panel that draws nothing shows whatever was last blitted into
that screen region -- observed in phase 5 as a deck-list row appearing inside the
archetype summary box.
"""

from __future__ import annotations

import ctypes
import os

import wx

from utils.constants.theme import (
    ACCENT_ON_PRIMARY,
    ACCENT_PRIMARY,
    BASE_FONT_POINT_SIZE,
    BORDER_SUBTLE,
    DANGER_FILL,
    DANGER_ON_FILL,
    DISABLED_FILL,
    DISABLED_ON_FILL,
    SELECTION_FILLS,
    SELECTION_TEXT,
    SUCCESS_FILL,
    SUCCESS_ON_FILL,
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    SURFACE_RAISED,
    TEXT_DISABLED,
    TEXT_PLACEHOLDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TYPE_BOLD_LEVELS,
    contrast_ratio,
    font_point_size,
)
from utils.constants.ui_layout import STATUS_LABEL_MIN_WIDTH
from widgets.checkbox import DarkCheckBox
from widgets.native_dark import (
    THEME_EXPLORER,
    THEME_INPUT,
    apply_dark_caption,
    apply_dark_list_header,
    apply_dark_native_headers,
    apply_dark_theme,
    is_app_dark_mode_enabled,
    strip_spin_buddy_client_edge,
)

# Phase 1 flipped this to False: wx.Choice is themed dark everywhere. Kept as a
# module flag rather than an inline branch so the behaviour is greppable and a test
# can assert which mode is active.
CHOICE_USES_NATIVE_THEME = False

#: ``SetWindowTheme(hwnd, L" ", L" ")`` — the documented uxtheme call that opts a
#: single control out of visual styles. A control that is not visual-styled falls
#: back to the classic drawing path, which *does* consult ``WM_CTLCOLOR*`` and so
#: honours the colours wx sets on it. This is the whole mechanism behind dark
#: dropdowns; see :func:`disable_native_theme`.
_UXTHEME_DISABLE = " "

_SURFACE_COLOURS = {
    "base": SURFACE_BASE,
    "panel": SURFACE_PANEL,
    "alt": SURFACE_ALT,
    "raised": SURFACE_RAISED,
}

_TEXT_COLOURS = {
    "primary": TEXT_PRIMARY,
    "secondary": TEXT_SECONDARY,
    "placeholder": TEXT_PLACEHOLDER,
    "disabled": TEXT_DISABLED,
}

# kind -> (background, foreground, bold)
#
# There is no border column. wxMSW gives a coloured wx.Button a **2px light-grey
# double frame** (#ADADAD outside, #E1E1E1 inside) drawn by the theme, identical
# whatever background is set, and no wx call changes its colour. The only control
# available is removing it, with wx.BORDER_NONE — which
# :func:`stylize_button` applies to every kind. See the module docstring.
#
# Every fill is therefore load-bearing: with no outline, the fill is the whole
# affordance. The neutrals step down base -> ghost -> secondary so that "how light
# is this chip" is the hierarchy.
_RGB = tuple[int, int, int]
_ButtonSpec = tuple[_RGB, _RGB, bool]
_BUTTON_KINDS: dict[str, _ButtonSpec] = {
    # The one loud button: saturated accent. At most one per surface. Everything
    # phase 2 took *off* primary is here because it was primary by default, not
    # by decision.
    "primary": (ACCENT_PRIMARY, ACCENT_ON_PRIMARY, True),
    # The default for everything that is not the primary action.
    "secondary": (SURFACE_RAISED, TEXT_PRIMARY, False),
    # Chrome that must not compete with content: the toolbar, view toggles, the
    # inspector pager, the settings button.
    "ghost": (SURFACE_ALT, TEXT_SECONDARY, False),
    "danger": (DANGER_FILL, DANGER_ON_FILL, False),
    "success": (SUCCESS_FILL, SUCCESS_ON_FILL, False),
    # A button that carries an on/off state (the Grid/Table/Pile toggles). The
    # unselected face is deliberately identical to ``ghost``: an unselected toggle
    # *is* a quiet chrome button. ``selected=True`` swaps it for the selection
    # idiom, which is the same token the deck rows, the card views and the active
    # notebook tab use.
    "toggle": (SURFACE_ALT, TEXT_SECONDARY, False),
    # No chip at all until pointed at: the menu-bar titles. A menu bar is the one
    # place where a *row* of chips would be wrong -- the affordance is the row's
    # position at the top of the window, not each title's fill -- so this is the
    # single kind that opts out of the neutral ladder and paints its own surface.
    # widgets.menu_bar swaps it for "ghost" on hover and while its menu is open.
    "flat": (SURFACE_BASE, TEXT_SECONDARY, False),
    # Applied by stylize_button(..., enabled=False); loses chroma, not just
    # contrast. wxMSW greys a disabled button's *label* and leaves the background
    # it was given at full saturation, so a disabled primary stays bright blue
    # unless the background is repainted here (issue #962, C-b).
    "disabled": (DISABLED_FILL, DISABLED_ON_FILL, False),
}

#: The label and weight a control wears while it is the selected one; the fill
#: comes from ``SELECTION_FILLS`` for whichever surface it sits on. Fill + label
#: rather than fill + 2px border, because wx.Button cannot draw a border — so the
#: accent label is what carries the >= 4.5:1 the border would have.
_SELECTED_FG = SELECTION_TEXT
_SELECTED_BOLD = True

#: Neutral fills, darkest to lightest.
_NEUTRAL_LADDER: tuple[_RGB, ...] = (SURFACE_BASE, SURFACE_PANEL, SURFACE_ALT, SURFACE_RAISED)

#: Kinds whose fill is deliberately *not* stepped up to stay visible on its
#: background. Only ``flat``, whose whole point is to be invisible at rest.
_UNSTEPPED_KINDS = frozenset({"flat"})

#: How much lighter than its background a neutral chip has to be before it reads
#: as a button at all. Measured off the surface scale: SURFACE_ALT on
#: SURFACE_PANEL is 1.10:1 and disappears; on SURFACE_BASE it is 1.32:1 and
#: reads. 1.15 is the line between those two, and it is what makes the Grid /
#: Table / Pile toggles visible on the card-table panel while leaving the toolbar
#: (which sits on SURFACE_BASE) exactly as designed.
#:
#: This is not a WCAG threshold. A button whose *only* identifier is its fill
#: would need 3:1, which no pair of adjacent dark surfaces can reach; these
#: buttons are identified by their label, and the fill only has to say "this is a
#: control". Where a fill *is* the only signal — the checkbox box — the token is
#: BORDER_STRONG at 3.54:1.
_MIN_CHIP_CONTRAST = 1.15


def _neutral_fill(preferred: _RGB, surface: str) -> _RGB:
    """Step ``preferred`` up the neutral ladder until it is visible on ``surface``."""
    if preferred not in _NEUTRAL_LADDER:
        return preferred
    background = _SURFACE_COLOURS[surface]
    index = _NEUTRAL_LADDER.index(preferred)
    while (
        index < len(_NEUTRAL_LADDER) - 1
        and contrast_ratio(_NEUTRAL_LADDER[index], background) < _MIN_CHIP_CONTRAST
    ):
        index += 1
    return _NEUTRAL_LADDER[index]


def _colour(rgb: _RGB) -> wx.Colour:
    return wx.Colour(*rgb)


def base_point_size() -> int:
    """The app's declared base font size, in whole points.

    Deliberately the *declared* base rather than whatever the window currently
    reports. The type scale must produce the same sizes whether or not
    :func:`apply_base_font` has been wired into a given window yet, so that
    rolling the base font out cannot silently change what a ``level=`` call
    renders.
    """
    return BASE_FONT_POINT_SIZE


def system_point_size() -> int:
    """The platform's default UI font size, for diagnostics and comparison."""
    return int(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT).GetPointSize())


def theme_font() -> wx.Font:
    """The platform UI font at the app's declared base size."""
    font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(BASE_FONT_POINT_SIZE)
    return font


def apply_base_font(window: wx.Window) -> None:
    """Put ``window`` and its future children on the app's base font.

    Two wx behaviours make the placement of this call load-bearing, both
    verified against wxMSW rather than assumed:

    * A child inherits its parent's font **at construction time**. Widgets that
      already exist when this is called keep the old size. So this must run
      immediately after ``super().__init__()`` and *before* any child is built.
    * Top-level windows do **not** inherit from their parent, even when one is
      passed. Every ``wx.Frame`` / ``wx.Dialog`` / ``wx.MiniFrame`` therefore
      needs its own call; a single call on the main frame does not reach the
      Radar, Timer Alert, Top Cards, Match History or Metagame windows.

    Inheritance does cover every non-top-level widget class the app uses,
    including ``wx.Choice`` and ``wx.ListCtrl``, so one call per top-level window
    is sufficient — there is no per-widget work.
    """
    window.SetFont(theme_font())


def init_top_level_window(window: wx.Window) -> None:
    """Everything a new ``wx.Frame`` / ``wx.Dialog`` / ``wx.MiniFrame`` needs first.

    One call rather than two at each of the app's top-level windows, because both
    halves have the same constraint — they must run immediately after
    ``super().__init__()``, before any child is built and before ``Show()`` — and
    because a window that gets one and not the other is a bug that is invisible
    until someone screenshots it:

    * :func:`apply_base_font`, since top-level windows never inherit a font.
    * :func:`widgets.native_dark.apply_dark_caption`, since Windows' process-wide
      dark mode does not reach the title bar. Phase 1 enabled dark mode and
      everything *inside* the windows went dark; the captions stayed ``#FFFFFF``
      for two more phases because nothing was measuring them.
    """
    apply_base_font(window)
    apply_dark_caption(window)
    clamp_to_display(window)


def clamp_to_display(window: wx.Window) -> None:
    """Shrink *window* to the usable area of the display it is on, if it exceeds it.

    Phase 8. ``AppFrame`` has clamped its own restored size to
    ``wx.Display.GetClientArea()`` since before this redesign -- and maximizes
    instead when its preferred size does not fit -- but none of the other
    seventeen top-level windows did. Their sizes are constructor literals, and
    ``TOP_CARDS_FRAME_SIZE`` is **1400 x 740**: on the 1366x768 laptop the app
    says it targets, that window opens 34px wider than the whole screen and
    ~20px taller than the area the taskbar leaves, with its right-hand columns
    and its status row off the display and no way to reach them but dragging the
    window left.

    Called from :func:`init_top_level_window`, i.e. immediately after the
    constructor has applied its size. A window that sizes itself *later* -- the
    timer alert, which measures its own content -- calls this again afterwards.
    It only ever shrinks; a window that already fits is left exactly as it is,
    and a maximized or full-screen window is skipped, since its size legitimately
    exceeds the client area by the maximized frame border and resizing it here
    would silently un-maximize it.
    """
    try:
        if window.IsMaximized() or window.IsFullScreen():
            return
    except AttributeError:
        pass
    try:
        index = wx.Display.GetFromWindow(window)
        if index == wx.NOT_FOUND:
            index = 0
        area = wx.Display(index).GetClientArea()
    except (RuntimeError, AssertionError):
        return
    size = window.GetSize()
    width = min(size.GetWidth(), area.width)
    height = min(size.GetHeight(), area.height)
    if width == size.GetWidth() and height == size.GetHeight():
        return
    # The floor has to come down with the window, or wx will not honour the new
    # size at all -- a minimum wider than the display is exactly the state this
    # function exists to get out of.
    min_size = window.GetMinSize()
    window.SetMinSize(
        wx.Size(
            min(min_size.GetWidth(), width) if min_size.GetWidth() > 0 else min_size.GetWidth(),
            min(min_size.GetHeight(), height) if min_size.GetHeight() > 0 else min_size.GetHeight(),
        )
    )
    window.SetSize(wx.Size(width, height))


def type_font(
    level: str = "body",
    *,
    base: wx.Font | None = None,
    bold: bool | None = None,
) -> wx.Font:
    """A ``wx.Font`` at ``level`` on the type scale, for **own-drawn** text.

    Font inheritance reaches every real widget, but it cannot reach text a
    control paints itself with ``dc.SetFont()`` — the deck rows, the card grid,
    the pile view. Those used to hard-code point sizes (9, 10, 11), which is why
    the own-drawn surfaces were the only places in the app whose type did not
    move when the base font did. They call this instead.

    :param base: the face to derive from; defaults to the app's UI face.
    :param bold: override the level's default weight. Glyph runs (``+``/``-``/
        ``x`` chips) set this ``True`` because bold is buying legibility at 10pt
        on top of card art, not marking a heading.
    """
    font = wx.Font(base) if base is not None else theme_font()
    font.SetPointSize(font_point_size(base_point_size(), level))
    if bold is None:
        bold = level in TYPE_BOLD_LEVELS
    font.SetWeight(wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL)
    return font


def apply_type_level(window: wx.Window, level: str, *, base_pt: int | None = None) -> None:
    """Put ``window``'s font on the type scale at ``level``.

    Bold is applied for — and only for — the levels in ``TYPE_BOLD_LEVELS``.
    """
    font = window.GetFont()
    font.SetPointSize(font_point_size(base_pt if base_pt is not None else base_point_size(), level))
    font.SetWeight(wx.FONTWEIGHT_BOLD if level in TYPE_BOLD_LEVELS else wx.FONTWEIGHT_NORMAL)
    window.SetFont(font)


def stylize_label(
    label: wx.StaticText,
    subtle: bool = False,
    *,
    level: str | None = None,
    surface: str = "auto",
    tone: str | None = None,
) -> None:
    """Theme a static label.

    :param subtle: legacy switch. ``True`` picks secondary text on the panel
        surface and no bold; ``False`` picks primary text on the base surface and
        bold. Preserved verbatim so existing call sites do not move.
    :param level: type-scale level (``display``/``title``/``heading``/``body``/
        ``caption``). When given, the font comes from the scale and bold is applied
        only to headings. When omitted the legacy bold-unless-subtle rule applies —
        phase 3 replaces every call site's reliance on that with an explicit level.
    :param tone: override the foreground: ``primary``/``secondary``/``placeholder``/
        ``disabled``.
    :param surface: which surface the label sits on; ``auto`` keeps the legacy
        pairing (panel when subtle, base otherwise).
    """
    if surface == "auto":
        surface = "panel" if subtle else "base"
    if tone is None:
        tone = "secondary" if subtle else "primary"

    label.SetForegroundColour(_colour(_TEXT_COLOURS[tone]))
    label.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))

    if level is None:
        # Legacy path: bold everything that is not subtle. This is root cause 3 and
        # is exactly what `level` exists to retire; it stays the default only so
        # that phase 0 is a no-op on screen.
        font = label.GetFont()
        if not subtle:
            font.MakeBold()
        label.SetFont(font)
    else:
        apply_type_level(label, level)


def stylize_placeholder_label(label: wx.StaticText, *, surface: str = "alt") -> None:
    """Theme a hand-rolled placeholder/hint label drawn over an input.

    wxMSW gives no control over ``wx.TextCtrl.SetHint``'s colour, so the app draws
    its own hint labels (e.g. the mana rich-text control). This is the supported
    way to colour one.
    """
    label.SetForegroundColour(_colour(TEXT_PLACEHOLDER))
    label.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))


def stylize_textctrl(
    ctrl: wx.TextCtrl,
    multiline: bool = False,
    *,
    placeholder: str | None = None,
    level: str | None = None,
    surface: str = "alt",
) -> None:
    """Theme a text input.

    :param multiline: legacy switch that bumped the point size by 1 -- an
        off-ladder step of 1.11x, below the perceptual floor. Superseded by
        ``level=``; kept only so a caller that passes it does not change size.
    :param level: type-scale level for the field's text.
    :param surface: which surface the field's own fill comes from. ``alt`` is
        the input well and is what almost every field wants; the feedback
        dialog's notes box sits on a panel that is already ``alt``'s neighbour.
    :param placeholder: sets the native hint text. The colour token is
        ``TEXT_PLACEHOLDER``; on wxMSW the native hint ignores it, which is why
        ``stylize_placeholder_label`` exists for the drawn-label idiom.

    Phase 6b moved :func:`strip_native_client_edge` in here. Phase 6 found the
    ``#FFFFFF`` sunken edge and fixed the four sites it was looking at, one call
    site at a time -- which left the styling function itself silent about the
    edge, so the next text field written after it got the white hairline back.
    A ``wx.TextCtrl`` never wants that edge, and what is left behind is
    **nothing** -- phase 6 recorded a dark-mode edit border from an isolated
    probe and phase 6b measured five real fields that had none.

    This function is therefore no longer the whole of theming a text input.
    Phase 6c owns the boundary that replaces the stripped edge, and it cannot
    live on the control: build fields with
    :func:`widgets.input_frame.create_text_input`, which calls this and then
    paints a ``BORDER_STRONG`` ring around it from the parent.
    """
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))
    if level is not None:
        apply_type_level(ctrl, level)
    else:
        font = ctrl.GetFont()
        if multiline:
            font.SetPointSize(font.GetPointSize() + 1)
        ctrl.SetFont(font)
    if placeholder is not None:
        ctrl.SetHint(placeholder)
    strip_native_client_edge(ctrl)


def disable_native_theme(window: wx.Window) -> bool:
    """Opt ``window`` out of Windows visual styles. Returns whether it took effect.

    Why this exists: wxMSW's ``wx.Choice`` (a Win32 ``COMBOBOX``) ignores both
    ``SetBackgroundColour`` and ``SetForegroundColour`` while the control is
    visual-styled — the theme engine paints the control and never consults
    ``WM_CTLCOLORLISTBOX``. Measured, not assumed: nine construction orders
    (colour-before-selection, colour-after-layout, background only, foreground
    only, ``wx.ComboBox`` with ``wx.CB_READONLY``) all render the same light grey.

    ``SetWindowTheme(hwnd, L" ", L" ")`` is the documented uxtheme call for
    disabling theming on one control. The control then draws through the classic
    path, which *does* honour the wx colours — including the drop-down list, which
    inherits them too. The visible cost is that the drop-down arrow becomes a small
    classic 3-D button rather than a flat chevron.

    A no-op (returning ``False``) off Windows, or if uxtheme is unavailable, so
    call sites never need to branch on the platform.
    """
    if os.name != "nt":
        return False
    try:
        handle = window.GetHandle()
    except Exception:  # pragma: no cover - defensive; wx always has a handle here
        return False
    if not handle:
        return False
    try:
        ctypes.windll.uxtheme.SetWindowTheme(  # type: ignore[attr-defined]
            ctypes.c_void_p(handle), _UXTHEME_DISABLE, _UXTHEME_DISABLE
        )
    except Exception:  # pragma: no cover - depends on the Windows build
        return False
    return True


def stylize_choice(ctrl: wx.Choice, *, surface: str = "alt") -> None:
    """Theme a dropdown dark (issue #962, C1).

    Two things are needed, and the second is the one that actually matters:
    the colours, and :func:`disable_native_theme` to make wxMSW use them at all.
    Setting the colours alone leaves the control exactly as light as it was —
    which is why the phase-0 note that this was "one line" turned out to be wrong.

    ``CHOICE_USES_NATIVE_THEME`` restores the pre-phase-1 rendering (system button
    face + black text). It exists so the regression can be reproduced in one line
    if the classic drop-down arrow is judged worse than a light control.
    """
    if CHOICE_USES_NATIVE_THEME:
        ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
        ctrl.SetForegroundColour(wx.Colour(0, 0, 0))
        return
    if not apply_dark_theme(ctrl, THEME_INPUT):
        # No OS dark mode (pre-1809 Windows, or the ordinals moved): drop the
        # control out of visual styles so the classic path picks up the colours
        # below. Costs a small 3-D arrow button instead of a flat chevron.
        disable_native_theme(ctrl)
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))


def stylize_combobox(ctrl: wx.ComboBox, *, surface: str = "alt") -> None:
    """Theme an editable/read-only combo box.

    Identical constraints to :func:`stylize_choice` — a ``wx.ComboBox`` is the
    same Win32 ``COMBOBOX``, and ignores both colours while visual-styled. Kept as
    its own entry point rather than overloading ``stylize_choice`` so the type
    hints stay honest at the call sites.
    """
    if not apply_dark_theme(ctrl, THEME_INPUT):
        disable_native_theme(ctrl)
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))


def stylize_checkbox(
    ctrl: wx.CheckBox | DarkCheckBox,
    *,
    surface: str = "base",
    tone: str = "primary",
) -> None:
    """Theme a checkbox.

    For a :class:`widgets.checkbox.DarkCheckBox` — which is what every call site
    in the app now builds — this sets the surface and label tone and the control
    paints itself, box glyph included.

    A plain ``wx.CheckBox`` is still accepted so that third-party or dialog code
    keeps working, but it gets the phase-1 partial fix only: **the box glyph stays
    white.** wxMSW hands the glyph to ``wxRendererNative``, which opens the light
    ``BUTTON`` theme class; seven theme classes and the no-visual-style path were
    measured and every one of them is a solid white square. That is why
    ``DarkCheckBox`` exists — see its module docstring for the full list of what
    was ruled out, including ``wx.lib.checkbox.GenCheckBox``, which draws the same
    renderer's bitmaps.
    """
    if isinstance(ctrl, DarkCheckBox):
        ctrl.apply_theme(surface=surface, tone=tone)
        return
    ctrl.SetForegroundColour(_colour(_TEXT_COLOURS[tone]))
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))


def stylize_spinctrl(ctrl: wx.SpinCtrl, *, surface: str = "alt") -> None:
    """Theme a spin control's edit field. The **arrow buttons stay light.**

    ``wx.SpinCtrl`` on MSW is two HWNDs: an ``Edit`` and an ``msctls_updown32``,
    with ``GetHandle()`` returning the *up-down*, not the edit. wx forwards the
    colours to the edit, which is why the field goes dark. The arrows were tried
    against ``DarkMode_CFD`` under Windows dark mode and against no visual style
    at all, and render light grey in both — so nothing is set on them here rather
    than setting something that does nothing.

    Still worth doing: unstyled, the whole control is a solid white block. The
    opponent tracker's calculator had four of them stacked on the darkest panel
    in the app.

    Phase 6b added the third call, and had to find a different mechanism for it.
    The edit field takes the same near-white sunken client edge as
    ``wx.TextCtrl``, so all six spin controls in the app were a white hairline
    box around a dark field -- but
    :func:`strip_native_client_edge` **does nothing here**: wx applies the style
    flag to ``GetHandle()``, which on a ``wx.SpinCtrl`` is the arrows, not the
    field. :func:`widgets.native_dark.strip_spin_buddy_client_edge` goes through
    ``UDM_GETBUDDY`` to the ``Edit`` that actually owns the edge. Verified by
    screenshot both times -- the first version looked right in the diff and was
    pixel-identical on screen.
    """
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))
    strip_spin_buddy_client_edge(ctrl)


def stylize_gauge(gauge: wx.Gauge, *, surface: str = "alt") -> None:
    """Theme a progress bar. Same mechanism as :func:`stylize_choice`, same reason.

    Measured with a six-variant probe (wxWidgets 3.2.8 / wxPython 4.2.4, process
    dark mode on): a visual-styled ``wx.Gauge`` renders a **``#E0E0E0`` trough
    with the Windows green fill** and ignores ``SetBackgroundColour`` and
    ``SetForegroundColour`` completely. Windows' own dark mode does not reach it
    either -- unlike ``wx.Choice`` and ``wx.ListCtrl``'s header -- and neither
    ``DarkMode_Explorer`` nor ``DarkMode_Explorer::PROGRESS`` changes a pixel.
    ``wx.BORDER_NONE`` changes nothing either.

    :func:`disable_native_theme` is the only route: off the visual-styles path
    the classic gauge honours both colours, giving a ``SURFACE_ALT`` trough with
    an ``ACCENT_PRIMARY`` fill. The radar window's gauge was an 866x20 block of
    near-white -- the loudest single control left in the app once phase 6 had
    retired the ``StaticBox`` groove.

    Accent, not ``SUCCESS_FILL``: a progress bar is not reporting success, and
    the accent's second register (see :func:`stylize_button`) is exactly
    "this is the thing currently happening".
    """
    disable_native_theme(gauge)
    gauge.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    gauge.SetForegroundColour(_colour(ACCENT_PRIMARY))


def stylize_scrollable(window: wx.Window, *, surface: str | None = None) -> None:
    """Give a scrolling container dark scrollbars, and optionally a themed canvas.

    Scrollbars are the one piece of chrome wx offers no control over whatsoever —
    there is no ``SetScrollbarColour`` and no style flag. Windows' own dark mode
    draws them dark, but **per window**: the process-wide switch alone is not
    enough, the scrolling window has to be put on a dark theme class as well. That
    is the whole reason this function exists, and it is why the app gets dark
    scrollbars without owning a custom scrollbar control — the review costed that
    at effort L with permanent maintenance, and this is a one-line call per site.

    :param surface: also paint the canvas background. Omit for windows that draw
        their own (the card grid and pile views paint every pixel themselves).
    """
    apply_dark_theme(window, THEME_EXPLORER)
    # wx.dataview's generic controls keep a native SysHeader32 child that theming
    # the wrapper does not reach; without this the match-history and radar tables
    # keep a white header strip.
    apply_dark_native_headers(window)
    if surface is not None:
        window.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))


def strip_native_client_edge(window: wx.Window) -> None:
    """Remove the near-white 1px sunken client edge wxMSW gives list and text controls.

    ``wx.ListBox``, ``wx.TextCtrl`` and ``wx.dataview``'s controls default to a
    sunken border that Windows draws at **#FFFFFF** with a #828790 outer line --
    13.7:1 on ``SURFACE_ALT``, and untouched by Windows' own dark mode, by
    ``SetBackgroundColour``, or by ``SetWindowTheme``. Phase 6 measured it on all
    three: it is the same near-white hairline the ``wx.StaticBox`` groove was, one
    layer further in, and once a section card puts a 1px ``BORDER_SUBTLE`` edge
    around one of these controls the result is a double border in which the wrong
    one dominates.

    ``wx.BORDER_NONE`` removes it, from the constructor **and** post-construction
    via ``SetWindowStyleFlag`` -- verified by probe on ``DataViewListCtrl``,
    ``ListBox`` and ``TextCtrl``. Post-construction is what this helper uses, so a
    call site does not have to thread a style flag through a constructor it may
    not own.

    Two things it does not do:

    * on a ``wx.TextCtrl`` the white edge is **removed, not replaced**. Phase 6
      recorded the opposite -- that the dark-mode edit border took its place --
      from an isolated probe; phase 6b measured the five fields in the running
      deck builder and every one of them renders as bare ``SURFACE_ALT`` on its
      parent afterwards, at 1.10:1 on ``SURFACE_PANEL``. Removing a 21:1
      hairline is still unambiguously right, and phase 6c supplied the boundary
      that replaces it: :mod:`widgets.input_frame` paints a ``BORDER_STRONG``
      ring from the field's **parent**, because wx gives no way to colour a
      ``wx.TextCtrl``'s own border;
    * on a composite it has to be applied to the window that owns the edge.
      ``wx.dataview.TreeListCtrl`` wraps a ``DataViewCtrl``; calling this on the
      wrapper alone changes nothing on screen.
    """
    style = window.GetWindowStyleFlag()
    window.SetWindowStyleFlag((style & ~wx.BORDER_MASK) | wx.BORDER_NONE)
    window.Refresh()


def stylize_list_ctrl(ctrl: wx.ListCtrl, *, surface: str = "alt") -> None:
    """Theme a report-view list.

    Rows honour the wx colours. The header does not — it is a native
    ``SysHeader32`` that ignores everything wx can set, so it is handed to the OS
    dark theme instead (see :func:`widgets.native_dark.apply_dark_list_header`).
    Without OS dark mode the header stays white and there is no wx-level fix;
    ``SetHeaderAttr`` is deliberately *not* used as a consolation prize because it
    applies the foreground only, which is strictly worse than leaving it alone.

    Phase 6b added the client-edge strip here for the same reason it added it to
    :func:`stylize_textctrl`: the deck builder's results list is constructed with
    ``style=0`` and was framed in a **pure ``#FFFFFF`` 1px rectangle, 553x555**,
    on the main window's left panel whenever the builder is open. Phase 6 found
    the mechanism and fixed the four sites in front of it; the fix belongs in the
    styling function, not at the call sites, or the next list written gets the
    hairline back.
    """
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))
    # Also darkens the list's own scrollbars, since it themes the control itself.
    apply_dark_list_header(ctrl)
    strip_native_client_edge(ctrl)


def native_dark_mode_active() -> bool:
    """Whether native controls are being drawn by Windows' dark theme."""
    return is_app_dark_mode_enabled()


#: Attributes stashed on a button so a later ``Enable``/``Disable`` can repaint it
#: in the kind it was originally given. Instance attributes rather than a registry
#: so they die with the widget.
_BUTTON_KIND_ATTR = "_mtgo_button_kind"
_BUTTON_STATE_ATTR = "_mtgo_button_enabled"
_BUTTON_WATCHED_ATTR = "_mtgo_button_watched"


def _watch_enabled_state(button: wx.Button) -> None:
    """Repaint ``button`` when something calls ``Enable``/``Disable`` on it.

    wxMSW greys a disabled button's *label* and leaves the background exactly as
    saturated as it was, so a disabled primary stays bright blue (issue #962,
    C-b). ``Enable``/``Disable`` are C++ methods with no event and no Python hook,
    and the app calls them from ~20 places on buttons it does not own, so the
    repaint has to be driven from the button itself.

    ``EVT_UPDATE_UI`` is wx's own mechanism for exactly this — it already fires on
    every window each idle cycle whether or not a handler is bound, so this adds
    an attribute comparison and no new events.
    """
    if getattr(button, _BUTTON_WATCHED_ATTR, False):
        return
    setattr(button, _BUTTON_WATCHED_ATTR, True)

    def on_update(event: wx.UpdateUIEvent) -> None:
        event.Skip()
        current = bool(button.IsThisEnabled())
        if current == getattr(button, _BUTTON_STATE_ATTR, None):
            return
        kind, selected, surface, level = getattr(
            button, _BUTTON_KIND_ATTR, ("secondary", False, "base", None)
        )
        stylize_button(
            button, kind, enabled=current, selected=selected, surface=surface, level=level
        )

    button.Bind(wx.EVT_UPDATE_UI, on_update)


def strip_native_button_frame(button: wx.Button) -> None:
    """Remove wxMSW's light-grey 2px frame from a button.

    Measured (wxWidgets 3.2.8 / wxPython 4.2.4, Windows dark mode on): a
    ``wx.Button`` that has had ``SetBackgroundColour`` called on it is drawn with
    a two-pixel light frame — ``#ADADAD`` outside, ``#E1E1E1`` inside — whatever
    the background is. It is the same frame on ``SURFACE_BASE``, on
    ``SURFACE_RAISED`` and on ``ACCENT_PRIMARY``, so it is not derived from the
    face colour, and nothing wx exposes changes it. Against ``SURFACE_BASE`` it
    measures ~14:1, which made it the brightest chrome in the app: the toolbar's
    six buttons were a blue fill *inside a white outline*.

    ``wx.BORDER_NONE`` removes it, and — verified rather than assumed —
    ``SetWindowStyleFlag`` applies it **after construction**, so this is a
    styling call and not a change to 26 constructor sites.
    """
    style = button.GetWindowStyleFlag()
    if style & wx.BORDER_NONE:
        return
    button.SetWindowStyleFlag(style | wx.BORDER_NONE)
    button.Refresh()


def stylize_button(
    button: wx.Button,
    kind: str = "primary",
    *,
    enabled: bool = True,
    selected: bool = False,
    surface: str = "base",
    level: str | None = None,
) -> None:
    """Theme a button by the role it plays.

    :param kind: ``primary`` (accent fill, near-black bold label — at most one per
        surface), ``secondary`` (the default for everything else), ``ghost``
        (chrome that must not compete: view toggles, pager), ``flat`` (no chip at
        all until hovered — the menu-bar titles), ``toggle`` (a button carrying an
        on/off state), ``danger`` or ``success``.
    :param enabled: ``False`` paints the disabled tokens, which drop chroma rather
        than merely dimming the fill. Pass it whenever the call site also calls
        ``Disable()`` — wxMSW greys the *label* by itself and leaves the
        background exactly as saturated as it was.
    :param selected: for ``kind="toggle"``, whether this is the chosen one. Paints
        the app's single selection idiom (accent tint + accent label).
    :param surface: which surface the button sits on. Neutral fills are relative,
        not absolute: a ghost chip is "one visible step above my background", so
        the same kind that reads on ``SURFACE_BASE`` does not vanish on a panel.
        Selection tints are pre-composited per surface for the same reason.
    :param level: optional type-scale level for the label.
    """
    if kind not in _BUTTON_KINDS:
        raise ValueError(f"unknown button kind {kind!r}; expected one of {sorted(_BUTTON_KINDS)}")
    # A call site may Disable() before *or* after styling; honour both.
    enabled = enabled and bool(button.IsThisEnabled())
    setattr(button, _BUTTON_KIND_ATTR, (kind, selected, surface, level))
    setattr(button, _BUTTON_STATE_ATTR, enabled)
    _watch_enabled_state(button)
    if not enabled:
        background, foreground, bold = _BUTTON_KINDS["disabled"]
    elif selected:
        background, foreground, bold = SELECTION_FILLS[surface], _SELECTED_FG, _SELECTED_BOLD
    else:
        background, foreground, bold = _BUTTON_KINDS[kind]
        if kind not in _UNSTEPPED_KINDS:
            background = _neutral_fill(background, surface)

    strip_native_button_frame(button)
    button.SetBackgroundColour(_colour(background))
    button.SetForegroundColour(_colour(foreground))

    if level is None:
        font = button.GetFont()
        # Restyling a button must be able to take bold *off* again — the view-mode
        # toggles are re-stylized on every switch, so a one-way MakeBold() would
        # leave every button that had ever been selected permanently bold.
        font.SetWeight(wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL)
        button.SetFont(font)
    else:
        apply_type_level(button, level)


def size_compact_button(button: wx.Button, *, pad_x: int, height: int) -> None:
    """Give a ``wx.BU_EXACTFIT`` button a real hit target (F4).

    ``wx.Button.GetBestSize()`` floors at 75x23 / 75x25 whatever the label (see
    the module docstring), and ``wx.BU_EXACTFIT`` is the only way past that --
    but it hands back the *opposite* problem, because it sizes to the text
    extent plus ~2px. The deck workspace's ``Grid``/``Table``/``Pile`` toggles
    measured 30x18 that way, under every pointer-target guideline there is.

    Dropping ``BU_EXACTFIT`` is not the fix: four 75px chips plus ``Art`` would
    not fit the deck workspace header at the window's minimum width. So the size
    is stated explicitly instead -- the label's own extent plus ``pad_x`` either
    side, at ``height``. ``SetMinSize`` is enough: with ``BU_EXACTFIT`` the best
    size is the smaller of the two, so the minimum is what the sizer honours.

    The extent is measured against the **bold** face whatever the button's
    current weight, so a toggle that bolds on selection keeps one width and the
    row never jitters as the selection moves.
    """
    font = button.GetFont()
    if font.GetWeight() != wx.FONTWEIGHT_BOLD:
        font = font.Bold()
    dc = wx.ScreenDC()
    dc.SetFont(font)
    text_w, _text_h = dc.GetTextExtent(button.GetLabel())
    button.SetMinSize((text_w + pad_x * 2, height))


def create_status_label(parent: wx.Window, text: str = "") -> wx.StaticText:
    """A toolbar's right-hand status label, built so it cannot clip (F8).

    Match History, Metagame Analysis and Top Cards each had the same bug: a
    right-hand ``wx.StaticText`` added at proportion 0 after an
    ``AddStretchSpacer(1)``. The spacer absorbed the slack, the label then asked
    for its full natural width on top of it, and anything longer than the leftover
    ran off the window edge mid-word -- "Failed to", "Loade", "To".

    Three things fix it together, and none of them works alone:

    * ``wx.ST_ELLIPSIZE_END`` has to be passed to the **constructor** -- wxMSW
      does not pick it up from a later ``SetWindowStyleFlag``.
    * the label has to be added at **proportion 1**, in place of the stretch
      spacer, so the sizer hands it a bounded box to ellipsise inside. At
      proportion 0 it keeps asking for its best size and nothing ever tells it
      that it does not fit.
    * ``wx.ST_NO_AUTORESIZE`` is required for ``wx.ALIGN_RIGHT`` to be visible at
      all, and this one was measured after the first attempt shipped
      left-aligned. Without it, ``SetLabel`` **resizes the control to the new
      text** -- so the box hugs the string, the alignment inside that box has
      nothing to align against, and the label renders flush left at whatever x
      the last layout left it. A probe frame right-aligned correctly while the
      real toolbars did not, and the difference was entirely that the real ones
      call ``SetLabel`` afterwards. It also means ellipsization never fires,
      because an auto-resized control always fits its own text.
    """
    label = wx.StaticText(
        parent,
        label=text,
        style=wx.ST_ELLIPSIZE_END | wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE,
    )
    label.SetForegroundColour(_colour(TEXT_SECONDARY))
    label.SetMinSize((STATUS_LABEL_MIN_WIDTH, -1))
    return label


def create_divider(parent: wx.Window, *, vertical: bool, length: int | None = None) -> wx.Window:
    """A 1px themed rule (C4).

    ``wx.StaticLine`` is **not** usable here, and this was measured rather than
    assumed: a ``wx.LI_VERTICAL`` StaticLine on ``SURFACE_PANEL`` draws in the
    native etched colour and ignores both ``SetBackgroundColour`` and
    ``SetForegroundColour``, so it came out as a near-white 1px bar -- brighter
    than any other chrome in the deck workspace header, and a clear regression on
    the ``wx.StaticText(label="|")`` it replaced. (The two *horizontal*
    StaticLines already in the tree read as dark, which is what made the trap
    convincing; they sit on a darker surface and are 1px of a low-contrast etch
    that the eye loses. A vertical one next to text does not get lost.)

    ``wx.Panel`` backgrounds *are* honoured, so the rule is one.

    ``length=None`` leaves the long axis free, for a rule added with
    ``wx.EXPAND`` that should span whatever its sizer gives it.
    """
    thin = -1 if length is None else length
    size = (1, thin) if vertical else (thin, 1)
    rule = wx.Panel(parent, size=size)
    rule.SetMinSize(size)
    if length is not None:
        rule.SetMaxSize(size)
    else:
        rule.SetMaxSize((1, -1) if vertical else (-1, 1))
    rule.SetBackgroundColour(_colour(BORDER_SUBTLE))
    return rule


def surface_colour(surface: str) -> wx.Colour:
    """The background colour of a named surface (``base``/``panel``/``alt``/``raised``)."""
    return _colour(_SURFACE_COLOURS[surface])
