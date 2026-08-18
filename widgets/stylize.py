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
  cause that bold currently marks nothing (29 ``MakeBold`` sites app-wide).
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
``wx.Button``        background + foreground honoured, border is not
``wx.CheckBox``      label + surround honoured; the box **glyph** is drawn
                     by ``wxRendererNative`` from the light ``BUTTON``
                     theme class and is not reachable at all — see
                     :func:`stylize_checkbox`
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
                     Dark only via Windows' own dark mode.
``wx.Notebook``      both ignored, **and Windows' dark mode does not reach
                     it either** — migration to ``FlatNotebook`` is the
                     only fix (see :mod:`widgets.notebook`)
``wx.StatusBar``     background honoured, **foreground silently ignored**
                     — hence :mod:`widgets.status_bar`
scrollbars           not reachable from wx at all; dark process-wide via
                     :func:`widgets.native_dark.enable_app_dark_mode`
===================  ==================================================

Anything marked "via Windows' own dark mode" goes through
:mod:`widgets.native_dark`, which is enabled once at startup.
"""

from __future__ import annotations

import ctypes
import os

import wx

from utils.constants.theme import (
    ACCENT_ON_PRIMARY,
    ACCENT_PRIMARY,
    BASE_FONT_POINT_SIZE,
    BORDER_STRONG,
    DANGER_FILL,
    DANGER_ON_FILL,
    DISABLED_FILL,
    DISABLED_ON_FILL,
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
    font_point_size,
)
from widgets.native_dark import (
    THEME_EXPLORER,
    THEME_INPUT,
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

# kind -> (background, foreground, bold, border)
#
# The border token is carried but not applied: wx.Button on MSW draws its own
# frame and exposes no border colour. Phase 2 moves the outline kinds onto an
# own-drawn button and reads this column then; keeping it here means the palette
# decision lives with the rest of the button definition rather than in a panel.
_RGB = tuple[int, int, int]
_ButtonSpec = tuple[_RGB | None, _RGB, bool, _RGB | None]
_BUTTON_KINDS: dict[str, _ButtonSpec] = {
    # The one loud button. Reserved for the single most important action on a
    # surface; phase 2 drops the rest of the app off it.
    "primary": (ACCENT_PRIMARY, ACCENT_ON_PRIMARY, True, None),
    # The default for everything that is not the primary action.
    "secondary": (SURFACE_PANEL, TEXT_PRIMARY, False, BORDER_STRONG),
    # Chrome that must not compete with content: toolbars, view toggles.
    "ghost": (SURFACE_BASE, TEXT_SECONDARY, False, None),
    "danger": (DANGER_FILL, DANGER_ON_FILL, False, None),
    "success": (SUCCESS_FILL, SUCCESS_ON_FILL, False, None),
    # Applied by stylize_button(..., enabled=False); loses chroma, not just contrast.
    "disabled": (DISABLED_FILL, DISABLED_ON_FILL, False, None),
}


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
) -> None:
    """Theme a text input.

    :param multiline: legacy switch that bumps the point size by 1. Retained for
        the one call site that uses it; phase 3 replaces it with ``level=``.
    :param placeholder: sets the native hint text. The colour token is
        ``TEXT_PLACEHOLDER``; on wxMSW the native hint ignores it, which is why
        ``stylize_placeholder_label`` exists for the drawn-label idiom.
    """
    ctrl.SetBackgroundColour(_colour(SURFACE_ALT))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))
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
    ctrl: wx.CheckBox,
    *,
    surface: str = "base",
    tone: str = "primary",
) -> None:
    """Theme a checkbox's label and surround. The **box glyph stays white.**

    This is a partial fix and says so out loud rather than pretending otherwise.
    Measured: setting a colour on a ``wx.CheckBox`` makes wxMSW owner-draw it and
    hand the glyph to ``wxRendererNative``, which opens the standard light
    ``BUTTON`` theme class. Seven theme classes were tried against a checkbox with
    Windows dark mode active — ``DarkMode_Explorer``, ``DarkMode_CFD``,
    ``DarkMode``, ``DarkMode_Explorer::Button``, ``Explorer::Button``,
    ``DarkMode_ItemsView``, ``ItemsView`` — and the box is a solid white square in
    every one of them, checked and unchecked. Dropping the control out of visual
    styles does not help either: the classic checkbox fills its box with
    ``COLOR_WINDOW``, which is also white.

    So no ``apply_dark_theme`` call here: it would be exactly the kind of colour
    setting that silently does nothing. A dark checkbox needs an own-drawn
    control; that is a new component, not a styling call, and belongs with the
    phase-2 button system.

    What this *does* fix is the label, which was often unset and rendered in the
    system's near-black on the dark surface.
    """
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


def stylize_button(
    button: wx.Button,
    kind: str = "primary",
    *,
    enabled: bool = True,
    level: str | None = None,
) -> None:
    """Theme a button by the role it plays.

    :param kind: ``primary`` (the default, and today's only style: accent fill,
        near-black bold label), ``secondary``, ``ghost``, ``danger`` or ``success``.
    :param enabled: ``False`` paints the disabled tokens, which drop chroma rather
        than merely dimming the fill.
    :param level: optional type-scale level for the label.
    """
    if kind not in _BUTTON_KINDS:
        raise ValueError(f"unknown button kind {kind!r}; expected one of {sorted(_BUTTON_KINDS)}")
    background, foreground, bold, _border = _BUTTON_KINDS["disabled" if not enabled else kind]

    if background is not None:
        button.SetBackgroundColour(_colour(background))
    button.SetForegroundColour(_colour(foreground))

    if level is None:
        font = button.GetFont()
        if bold:
            font.MakeBold()
        button.SetFont(font)
    else:
        apply_type_level(button, level)
