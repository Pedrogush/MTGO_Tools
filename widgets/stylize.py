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
* ``stylize_choice`` still hands the control to the OS. See the comment there.
"""

from __future__ import annotations

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

# Phase 1 flips this to False and wx.Choice is themed dark everywhere; see
# stylize_choice. Kept as a module flag rather than an inline branch so the change
# is one line and so a test can assert which mode is active.
CHOICE_USES_NATIVE_THEME = True

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


def stylize_choice(ctrl: wx.Choice) -> None:
    """Theme a dropdown.

    Phase 0 deliberately keeps the OS-native light theme this control has always
    had, so that phase 0 changes nothing on screen. Phase 1 (issue #962, C1) makes
    every dropdown dark by flipping ``CHOICE_USES_NATIVE_THEME`` to ``False`` —
    that one line, and ~30 call sites follow. wxMSW will still draw the dropdown
    arrow with the native theme; an own-drawn ``wx.ComboBox`` is the follow-up if
    that grates.
    """
    if CHOICE_USES_NATIVE_THEME:
        ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
        ctrl.SetForegroundColour(wx.Colour(0, 0, 0))
        return
    ctrl.SetBackgroundColour(_colour(SURFACE_ALT))
    ctrl.SetForegroundColour(_colour(TEXT_PRIMARY))


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
