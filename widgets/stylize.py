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
``wx.TextCtrl``      background + foreground honoured
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
                     theme tried, Windows dark mode included
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
                     own-drawn header window
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
``wx.Notebook``      both ignored, **and Windows' dark mode does not reach
                     it either** — migration to ``FlatNotebook`` is the
                     only fix (see :mod:`widgets.notebook`)
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
) -> None:
    """Theme a text input.

    :param multiline: legacy switch that bumped the point size by 1 -- an
        off-ladder step of 1.11x, below the perceptual floor. Superseded by
        ``level=``; kept only so a caller that passes it does not change size.
    :param level: type-scale level for the field's text.
    :param placeholder: sets the native hint text. The colour token is
        ``TEXT_PLACEHOLDER``; on wxMSW the native hint ignores it, which is why
        ``stylize_placeholder_label`` exists for the drawn-label idiom.
    """
    ctrl.SetBackgroundColour(_colour(SURFACE_ALT))
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
    """
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))


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


def stylize_list_ctrl(ctrl: wx.ListCtrl, *, surface: str = "alt") -> None:
    """Theme a report-view list.

    Rows honour the wx colours. The header does not — it is a native
    ``SysHeader32`` that ignores everything wx can set, so it is handed to the OS
    dark theme instead (see :func:`widgets.native_dark.apply_dark_list_header`).
    Without OS dark mode the header stays white and there is no wx-level fix;
    ``SetHeaderAttr`` is deliberately *not* used as a consolation prize because it
    applies the foreground only, which is strictly worse than leaving it alone.
    """
    ctrl.SetBackgroundColour(_colour(_SURFACE_COLOURS[surface]))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))
    # Also darkens the list's own scrollbars, since it themes the control itself.
    apply_dark_list_header(ctrl)


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
