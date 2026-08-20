"""A mechanical audit of every widget construction site in ``widgets/``.

Why this file exists
====================
Phases 1, 2 and 3 of the UI redesign (issue #962) each established a system --
dark native widgets, one button system, one type and spacing scale -- and each
was applied by **walking a list**. Every phase since has found sites those lists
missed, one at a time and always by screenshot:

* phase 3 found ``threshold_panel._stylize_remove_button`` hand-rolling ``#8B2323``
* phase 4 found ``Save art`` sitting on the wrong surface
* phase 6 found the two panel collapse toggles keeping wxMSW's 2px light frame --
  two 14:1 rules running the full height of the main window, missed for four
  phases of screenshots
* phase 6b found the mana search fields **painting their own** 2px ``#FEFEFE``
  frame, and a ``wx.Gauge`` rendering as an 866x20 white block

The lists were not the problem; *working from a list* was. This module replaces
the list with an enumeration: it parses every module under ``widgets/`` and
checks every construction site against the systems, so the next miss fails here
instead of waiting for someone to notice it in a capture.

The exceptions are the point
============================
A guard that is honest about its exceptions is worth more than a broad one that
people learn to ignore, so every site that legitimately opts out is named
individually below with the reason it opts out -- not silenced by loosening a
rule. Adding a name to an allowlist is a decision someone has to write down;
weakening a check is not.

Companions: ``test_section.py`` (no ``wx.StaticBox``), ``test_notebook.py`` (no
``wx.Notebook``), ``test_theme_contrast.py`` (WCAG pairs + no raw spacing
literals).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

WIDGETS = Path(__file__).resolve().parent.parent / "widgets"


# ---------------------------------------------------------------------------
# The systems, as sets of names
# ---------------------------------------------------------------------------

#: Controls whose *only* correct rendering comes from the button system. wxMSW
#: draws an uncoloured ``wx.Button`` in the **light** system face even under
#: process dark mode (phase 2), so "left alone" is not a neutral default here --
#: it is a light widget on a dark surface.
BUTTON_CLASSES = frozenset(
    {"wx.Button", "wx.BitmapButton", "wx.ToggleButton", "wx.BitmapToggleButton"}
)

#: Controls that wxMSW paints from a native theme, and that therefore need their
#: specific ``stylize_*`` -- setting colours on them by hand is a documented
#: no-op for most of this list. See ``docs/WXMSW_BEHAVIOUR.md``.
NATIVE_THEMED_CLASSES = frozenset(
    {
        "wx.Choice",
        "wx.ComboBox",
        "wx.SpinCtrl",
        "wx.SpinCtrlDouble",
        "wx.Gauge",
        "wx.ListCtrl",
        "wx.SearchCtrl",
    }
)

#: Controls that take the near-white sunken client edge Windows draws at
#: ``#FFFFFF`` and that no colour call reaches (phase 6). ``wx.SpinCtrl`` is not
#: here because there is no longer one in the tree at all -- see
#: :func:`test_no_bare_spin_control_survives_in_the_widget_tree`. Its field is a
#: ``wx.TextCtrl`` inside a :class:`widgets.spin_ctrl.DarkSpinCtrl`, so it is
#: covered by the ``wx.TextCtrl`` row above.
CLIENT_EDGE_CLASSES = frozenset({"wx.TextCtrl", "wx.ListBox", "wx.ListCtrl"})

#: Any callable that hands a widget to the styling layer. Local ``_stylize_*``
#: wrappers count -- they are thin delegates (see
#: ``widgets/frames/timer_alert/frame/styling.py``) and forcing every call site
#: to import the real one would be churn, not clarity.
_STYLING_CALL_RE = re.compile(r"^_?stylize_|^strip_native_|^apply_(type_level|dark_)|^size_compact")
_EXTRA_STYLING_CALLS = frozenset({"create_mana_button", "surface_colour", "apply_theme"})

#: The callables that actually remove the client edge. Deliberately a closed
#: list rather than a prefix match: "was this widget styled" and "did the white
#: hairline get taken off" are different questions, and phase 6 answered the
#: first at four sites while leaving the second unanswered everywhere else.
EDGE_STRIPPING_CALLS = frozenset(
    {
        "strip_native_client_edge",
        "stylize_textctrl",
        "stylize_spinctrl",
        "stylize_list_ctrl",
    }
)


# ---------------------------------------------------------------------------
# Allowlists -- every entry names one site and says why
# ---------------------------------------------------------------------------

#: ``file:line`` sites where a control reaches the styling layer through a path
#: this file's single-file name resolution cannot see.
ROUTED_ELSEWHERE: dict[str, str] = {
    "widgets/panels/card_table_panel/frame.py:182": (
        "The Grid/Table/Pile toggles are stashed in ``self._view_mode_buttons`` "
        "and re-stylized on every view change by "
        "``card_table_panel/toolbar.py::_refresh_view_mode_buttons`` -- they "
        "carry a selection state, so styling them at construction would be "
        "wrong, not merely redundant."
    ),
}

#: The only modules allowed to construct a bare ``wx.TextCtrl``. Every text
#: input in the app is a fill on ``SURFACE_ALT`` measuring **1.10:1** against
#: the panel around it once phase 6b took wxMSW's ``#FFFFFF`` client edge off,
#: and phase 0's rule is that a border which is the *sole marker* of a control
#: must be ``BORDER_STRONG`` (WCAG 1.4.11). wx cannot colour a ``wx.TextCtrl``'s
#: border at all, so the border is own-drawn by :mod:`widgets.input_frame` and a
#: field only gets one by being built through it.
TEXT_INPUT_FACTORIES: dict[str, str] = {
    "widgets/input_frame.py": (
        "The factory itself. ``create_text_input`` is the one place a "
        "``wx.TextCtrl`` is constructed, which is what makes this guard a "
        "closed question rather than a name-resolution one."
    ),
    "widgets/panels/mana_rich_text_ctrl/frame.py": (
        "One throwaway ``wx.TextCtrl`` built solely to read "
        "``GetBestSize().height`` so the mana field can match a real input's "
        "height, then ``Destroy()``d in the next statement. It is a ruler, not "
        "a widget, and it is never shown. The mana control's own frame is "
        "painted by ``widgets.input_frame.paint_input_border``."
    ),
}

#: Sites that must NOT go through the styling layer, and why.
DELIBERATELY_UNSTYLED: dict[str, str] = {
    "widgets/panels/mana_rich_text_ctrl/frame.py": (
        "One throwaway ``wx.TextCtrl`` built solely to read ``GetBestSize()."
        "height`` so the mana field can match a real input's height, then "
        "``Destroy()``d in the next statement. It is a ruler, not a widget."
    ),
}

#: Colour literals that are not theme tokens and are right not to be. Keyed by
#: the module they live in.
COLOUR_LITERAL_EXCEPTIONS: dict[str, str] = {
    "widgets/mana_icon_factory/bitmap_renderer.py": (
        "Mana-glyph rasterisation. The black/white glyph inks and the fully "
        "transparent ``wx.Colour(0, 0, 0, 0)`` clears are properties of the "
        "symbol being drawn -- the same class of thing as "
        "``MANA_GLYPH_FONT_SIZE_BASE``, which phase 3 kept off the type ladder "
        "because 13 is half of ``MANA_ICON_DEFAULT_SIZE``. A mana symbol does "
        "not change colour when the app's theme does."
    ),
    "widgets/mana_icon_factory/factory.py": "Mana-glyph rasterisation; see bitmap_renderer.",
    "widgets/mana_icon_factory/svg_renderer.py": (
        "Mana-glyph rasterisation: the SVG glyph ink and its outline, chosen "
        "against the symbol's own circle rather than against an app surface."
    ),
    "widgets/panels/deck_stats_panel/stats_constants.py": (
        "MTG colour identity (W/U/B/R/G/C) and card-type domain colours. These "
        "name things in the game, not things in the UI: a Mountain's swatch is "
        "red because Magic's red is red. See the open question in the phase 6b "
        "report about ``_TYPE_COLOURS`` and ``_HAND_COLOURS``, which are chart "
        "palettes rather than domain colours and do need a decision."
    ),
    "widgets/panels/deck_stats_panel/properties.py": (
        "The ``#828282`` fallback swatch for an unrecognised colour or card "
        "type; same domain palette as stats_constants."
    ),
    "widgets/panels/card_table_panel/grid_images.py": (
        "The placeholder card *template* draws a Magic card frame -- a coloured "
        "face from the card's own colour identity with black title text on it. "
        "That is card art the app is standing in for, not app chrome."
    ),
    "widgets/panels/card_image_display/bitmap_renderer.py": (
        "The flip-icon overlay: a semi-transparent disc and a yellow glyph. The "
        "alphas have no token (wx has no alpha compositing for widget colours, "
        "which is why every tint in theme.py is pre-composited) and the yellow "
        "is an affordance colour that would be a *visual* decision to change -- "
        "flagged in the phase 6b report rather than decided here. The mat, the "
        "border and the placeholder plate around it are on tokens."
    ),
    "widgets/stylize.py": (
        "``CHOICE_USES_NATIVE_THEME``'s legacy branch deliberately reproduces "
        "the pre-phase-1 rendering (system button face, black text) so the "
        "regression can be reproduced in one line. It is the *old* palette by "
        "definition."
    ),
}

#: Modules allowed to build a ``wx.Font`` or move a font off the ladder.
FONT_EXCEPTIONS: dict[str, str] = {
    "widgets/stylize.py": "Owns the ladder.",
    "widgets/notebook.py": "Owns the tab strip's font, and gets it from type_font().",
    "widgets/buttons/mana_button/button.py": (
        "Mana glyph rasterisation: the size is the icon's geometry, and the "
        "face is the bundled mana font, not the UI face."
    ),
    "widgets/mana_icon_factory/bitmap_renderer.py": "Mana glyph rasterisation.",
    "widgets/panels/card_image_display/bitmap_renderer.py": (
        "The flip glyph is sized as a fraction of the icon "
        "(``CARD_IMAGE_FLIP_ICON_TEXT_SCALE`` x ``flip_icon_size``) -- "
        "rasterisation geometry, not typography."
    ),
}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _dotted(node: ast.AST) -> str | None:
    """``wx.dataview.ListCtrl`` for an Attribute chain, else ``None``."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    return ".".join(reversed(parts))


def _callee(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_styling_call(name: str) -> bool:
    return bool(_STYLING_CALL_RE.match(name)) or name in _EXTRA_STYLING_CALLS


def _modules() -> list[Path]:
    return sorted(WIDGETS.rglob("*.py"))


def _rel(path: Path) -> str:
    return path.relative_to(WIDGETS.parent).as_posix()


def _styled_names(tree: ast.Module, *, via: frozenset[str] | None = None) -> set[str]:
    """Every expression in this module that is handed to the styling layer.

    Resolved to a fixpoint over two idioms, because both are load-bearing in the
    tree and treating either as an offender would be a false positive:

    * direct -- ``stylize_button(btn, ...)``;
    * loop -- ``for b in (up, down): stylize_button(b, ...)``, which reaches
      ``up`` and ``down`` through the loop variable.
    """
    styled: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (
            _callee(node) in via if via is not None else _is_styling_call(_callee(node))
        ):
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                styled.add(ast.unparse(arg))
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For)]
    changed = True
    while changed:
        changed = False
        for loop in loops:
            target = ast.unparse(loop.target)
            if target not in styled:
                continue
            for element in ast.walk(loop.iter):
                if isinstance(element, (ast.Name, ast.Attribute)):
                    text = ast.unparse(element)
                    if text not in styled:
                        styled.add(text)
                        changed = True
    return styled


def _constructions(tree: ast.Module, classes: frozenset[str]) -> list[tuple[int, str, str | None]]:
    """``(lineno, class, assigned name)`` for every construction of ``classes``."""
    assigned: dict[int, str] = {}
    for node in ast.walk(tree):
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Call):
            continue
        if isinstance(node, ast.Assign) and node.targets:
            assigned[id(value)] = ast.unparse(node.targets[0])
        elif isinstance(node, ast.AnnAssign):
            assigned[id(value)] = ast.unparse(node.target)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (name := _dotted(node.func)) in classes:
            out.append((node.lineno, name, assigned.get(id(node))))
    return out


def _unrouted(classes: frozenset[str], *, via: frozenset[str] | None = None) -> list[str]:
    """Every construction of ``classes`` that never reaches the styling layer.

    ``via`` narrows the accepted callables to a named set. Without it any
    ``stylize_*`` counts, which is right for "did this widget get themed at
    all"; with it the check can ask the sharper question "did it get *this*
    treatment", which is what the client edge needs -- ``stylize_scrollable`` on
    a ``wx.TextCtrl`` is styling, and does nothing about the white hairline.
    """
    offenders: list[str] = []
    for path in _modules():
        rel = _rel(path)
        if rel in DELIBERATELY_UNSTYLED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        styled = _styled_names(tree, via=via)
        for lineno, cls, target in _constructions(tree, classes):
            if f"{rel}:{lineno}" in ROUTED_ELSEWHERE:
                continue
            if target is None or target not in styled:
                offenders.append(f"{rel}:{lineno} {cls} ({target or 'not assigned'})")
    return offenders


# ---------------------------------------------------------------------------
# The button system
# ---------------------------------------------------------------------------


def test_every_button_reaches_the_button_system() -> None:
    """Phase 2's system, enforced rather than re-walked.

    An uncoloured ``wx.Button`` on wxMSW is not "unstyled", it is **light**: it
    renders in the system button face even with process-wide dark mode on, and
    it keeps a 2px ``#ADADAD``/``#E1E1E1`` frame that measures ~14:1 on
    ``SURFACE_BASE``. Phase 6b's sweep found 24 such buttons across 11 files --
    three whole dialogs, the radar window's four, and four per row in the
    sideboard card selector, which on a 30-card sideboard is 120 light chips.
    """
    offenders = _unrouted(BUTTON_CLASSES)
    assert offenders == [], (
        "these buttons never reach stylize_button, so wxMSW draws them in the "
        "light system face with a 2px light frame:\n  " + "\n  ".join(offenders)
    )


def test_every_native_themed_control_reaches_its_stylizer() -> None:
    """Phase 1's system: nothing the OS paints is left to the OS.

    Each of these classes has a *specific* entry point because each needs a
    different mechanism -- ``wx.Choice`` and ``wx.Gauge`` need
    ``SetWindowTheme``/visual-style opt-out before any colour call lands at all,
    ``wx.ListCtrl``'s header needs the OS dark theme, ``wx.SpinCtrl`` needs its
    client edge stripped. Setting colours on them by hand is the documented
    silent no-op this codebase keeps producing.
    """
    offenders = _unrouted(NATIVE_THEMED_CLASSES)
    assert offenders == [], (
        "these controls are painted by a native theme and need their "
        "stylize_* helper; colour calls alone are a no-op on them:\n  " + "\n  ".join(offenders)
    )


def test_every_client_edge_control_is_handled() -> None:
    """Phase 6's finding, applied to the whole tree.

    ``wx.TextCtrl`` and ``wx.ListBox`` default to a sunken border Windows draws
    at ``#FFFFFF``, untouched by dark mode, by ``SetBackgroundColour`` or by
    ``SetWindowTheme``. It has to be either stripped or left on deliberately.
    """
    offenders = _unrouted(CLIENT_EDGE_CLASSES, via=EDGE_STRIPPING_CALLS)
    assert offenders == [], (
        "these controls keep wxMSW's #FFFFFF sunken client edge; call "
        "strip_native_client_edge (or a stylize_* that does):\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# One text input
# ---------------------------------------------------------------------------


def test_no_bare_text_input_survives_in_the_widget_tree() -> None:
    """The fifth guard of this shape, after ``wx.StaticBox``, ``wx.Notebook``,
    ``wx.StaticLine`` and ``wx.SplitterWindow`` -- and the one with the sharpest
    edge, because the thing it is guarding *cannot be seen* by looking at a
    ``wx.TextCtrl``.

    A field constructed directly is not "unbordered pending styling": it is a
    ``SURFACE_ALT`` rectangle at **1.10:1** on ``SURFACE_PANEL`` with nothing
    marking where it begins, and no call any later phase can add will fix it,
    because wx exposes no way to colour a ``wx.TextCtrl``'s border. The border
    has to be painted by a parent, so it has to exist *before* the control does
    -- which is why this guard is on the construction site rather than on a
    styling call the way :func:`test_every_client_edge_control_is_handled` is.

    Use :func:`widgets.input_frame.create_text_input`; keep the returned frame's
    ``.ctrl`` for value, binding and focus calls exactly as before, and hand the
    frame to the sizer.
    """
    offenders = [
        _rel(path)
        for path in _modules()
        if "wx.TextCtrl(" in path.read_text(encoding="utf-8")
        and _rel(path) not in TEXT_INPUT_FACTORIES
    ]
    assert offenders == [], (
        "a bare wx.TextCtrl has no border wx can colour, so it renders as a "
        "1.10:1 fill with nothing marking the field; build it with "
        f"widgets.input_frame.create_text_input. Found in: {offenders}"
    )


@pytest.mark.parametrize("name", sorted(TEXT_INPUT_FACTORIES))
def test_every_text_input_factory_exception_still_builds_one(name: str) -> None:
    """An allowlist entry that has outlived its construction silences the guard."""
    path = WIDGETS.parent / name
    assert path.exists(), f"{name} no longer exists"
    assert "wx.TextCtrl(" in path.read_text(encoding="utf-8"), (
        f"{name} no longer constructs a wx.TextCtrl, so its exception is now "
        "covering whatever gets written there next"
    )


# ---------------------------------------------------------------------------
# One separator idiom
# ---------------------------------------------------------------------------


def test_no_static_line_survives_in_the_widget_tree() -> None:
    """``wx.StaticLine`` honours neither colour and draws near-white (phase 4).

    Mirrors the ``wx.StaticBox`` and ``wx.Notebook`` guards. The trap here is
    that a *horizontal* StaticLine on a dark surface reads as dark enough to
    pass a glance, which is why three of them survived phase 4's own C4 fix --
    that fix replaced the one vertical rule it was looking at and left the
    horizontals alone. :func:`widgets.stylize.create_divider` is a 1px
    ``wx.Panel``, whose background *is* honoured.
    """
    offenders = [
        _rel(path) for path in _modules() if "wx.StaticLine(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "wx.StaticLine ignores SetForegroundColour and SetBackgroundColour and "
        f"draws in the native etched colour; use create_divider. Found in: {offenders}"
    )


def test_no_bare_splitter_survives_in_the_widget_tree() -> None:
    """``wx.SplitterWindow``'s sash is white and no colour call reaches it.

    The fourth guard of this shape, after ``wx.StaticBox``, ``wx.Notebook`` and
    ``wx.StaticLine``, and the one that cost the most to find: the deck
    workspace's sash is a **6px ``#F0F0F0``/``#FFFFFF`` band ~1585px wide**,
    bigger than any single piece of chrome the earlier phases removed. It sits
    inside the card-art rectangle every light-pixel census excludes, which is
    exactly why six phases of screenshots walked past it.

    :class:`widgets.splitter.DarkSplitter` own-draws the gutter. Note what is
    *not* the fix: ``SetSashInvisible(True)`` does make it dark, and it also
    sets ``GetSashSize()`` to 0, which stops the split being draggable.
    """
    offenders = [
        _rel(path)
        for path in _modules()
        if "wx.SplitterWindow(" in path.read_text(encoding="utf-8")
        and _rel(path) != "widgets/splitter.py"
    ]
    assert offenders == [], (
        "wx.SplitterWindow draws a near-white 3-D sash that SetBackgroundColour, "
        "disable_native_theme and every SP_* flag combination leave alone; use "
        f"widgets.splitter.DarkSplitter. Found in: {offenders}"
    )


# ---------------------------------------------------------------------------
# One spin control
# ---------------------------------------------------------------------------

#: Every class that is, or wraps, a Win32 ``msctls_updown32``. ``wx.SpinButton``
#: is the bare arrows; ``wx.SpinCtrl`` and ``wx.SpinCtrlDouble`` pair one with an
#: ``Edit``. All three render the same light arrow blocks.
SPIN_CLASSES = ("wx.SpinCtrl(", "wx.SpinCtrlDouble(", "wx.SpinButton(")


def test_no_bare_spin_control_survives_in_the_widget_tree() -> None:
    """The sixth guard of this shape, and the one where the fix is *not* styling.

    A wxMSW ``wx.SpinCtrl`` is two HWNDs. The colours wx forwards reach the
    ``Edit``; the ``msctls_updown32`` arrows beside it are a separate window
    that stays light under **every** route wx or uxtheme offers -- measured
    twice, once in phase 1 and once as an eight-variant probe in phase 9b
    (``DarkMode_CFD``, ``DarkMode_Explorer``, ``DarkMode_Explorer::SPIN``,
    ``DarkMode::SPIN``, ``DarkMode_CFD::SPIN``, ``ItemsView``, no visual style,
    untouched), all with ``AllowDarkModeForWindow`` and ``WM_THEMECHANGED``.
    Pixel-identical light arrows in all eight.

    So, unlike :func:`test_every_native_themed_control_reaches_its_stylizer`,
    there is no ``stylize_*`` call that fixes this one and no allowlist entry
    that could be right: the control has to be
    :class:`widgets.spin_ctrl.DarkSpinCtrl`. Note the shape of the failure this
    guards against -- ``strip_native_client_edge`` on a ``wx.SpinCtrl`` was a
    **silent no-op** for a whole phase because ``GetHandle()`` hands back the
    arrows rather than the field.
    """
    offenders = [
        f"{_rel(path)} ({cls.rstrip('(')})"
        for path in _modules()
        for cls in SPIN_CLASSES
        if cls in path.read_text(encoding="utf-8") and _rel(path) != "widgets/spin_ctrl.py"
    ]
    assert offenders == [], (
        "a wx.SpinCtrl's arrows are a separate msctls_updown32 HWND that no "
        "colour, theme class or style flag reaches -- they render #ECECEC on "
        "every dark surface. Use widgets.spin_ctrl.DarkSpinCtrl. "
        f"Found in: {offenders}"
    )


# ---------------------------------------------------------------------------
# One palette
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def _is_rgb_tuple(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Tuple)
        and len(node.elts) in (3, 4)
        and all(
            isinstance(e, ast.Constant) and isinstance(e.value, int) and 0 <= e.value <= 255
            for e in node.elts
        )
    )


def _is_colour_literal_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or _dotted(node.func) not in {
        "wx.Colour",
        "wx.Brush",
        "wx.Pen",
    }:
        return False
    if not node.args:
        return False
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return bool(_HEX_RE.match(first.value))
    return len(node.args) >= 3 and all(
        isinstance(a, ast.Constant) and isinstance(a.value, int) for a in node.args
    )


def _docstring_ids(tree: ast.Module) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and ast.get_docstring(node):
                ids.add(id(node.body[0].value))
    return ids


_COLOUR_SETTER_RE = re.compile(
    r"^Set(Own)?(Foreground|Background|Text|Selection|Item|Label)?"
    r"(Colour|Foreground|Background|Brush|Pen)$"
)


def test_no_colour_literal_reaches_a_widget_outside_the_allowlist() -> None:
    """Phase 0's single source of truth, enforced.

    Three shapes, because the sweep found all three in the tree and a check for
    only the obvious one would have missed the worst offender:

    * ``wx.Colour(20, 22, 27)`` -- Match History carried a byte-for-byte copy of
      five surface and text tokens as module constants;
    * a bare ``(220, 80, 80)`` handed to ``SetForegroundColour`` -- the deck
      notes delete glyph, invisible to any grep for ``wx.Colour``;
    * a ``"#RRGGBB"`` string -- the ``wx.html.HtmlWindow`` surfaces, which take
      their colours as markup and so had drifted to near-matches
      (``#E6EDF3`` for ``TEXT_PRIMARY``, ``#A8B2BD`` for ``TEXT_SECONDARY``,
      ``#7AA2F7`` for ``ACCENT_TEXT``) that no contrast test could see.

    Docstrings are exempt: several of them quote the hex of something wxMSW
    draws that we cannot reach, next to the code that works around it. Phase 9
    moved the biggest such collection out to ``docs/WXMSW_BEHAVIOUR.md``, but
    the exemption stays -- the per-site notes that remain are the reason it
    existed.
    """
    offenders: list[str] = []
    for path in _modules():
        rel = _rel(path)
        if rel in COLOUR_LITERAL_EXCEPTIONS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_ids(tree)
        for node in ast.walk(tree):
            if _is_colour_literal_call(node):
                offenders.append(f"{rel}:{node.lineno} {ast.unparse(node)[:60]}")
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and _HEX_RE.search(node.value)
            ):
                offenders.append(f"{rel}:{node.lineno} {node.value[:60]!r}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and _COLOUR_SETTER_RE.match(node.func.attr)
            ):
                for arg in node.args:
                    if _is_rgb_tuple(arg):
                        offenders.append(
                            f"{rel}:{node.lineno} {node.func.attr}({ast.unparse(arg)})"
                        )
    assert offenders == [], (
        "every colour in widgets/ comes from utils.constants.theme. If one of "
        "these genuinely should not, add it to COLOUR_LITERAL_EXCEPTIONS with "
        "the reason:\n  " + "\n  ".join(offenders)
    )


def test_every_colour_literal_exception_names_a_real_module() -> None:
    """An allowlist that has outlived its file silently stops guarding anything."""
    missing = [rel for rel in COLOUR_LITERAL_EXCEPTIONS if not (WIDGETS.parent / rel).exists()]
    assert missing == [], f"stale COLOUR_LITERAL_EXCEPTIONS entries: {missing}"


# ---------------------------------------------------------------------------
# One type ladder
# ---------------------------------------------------------------------------


def test_no_font_is_built_or_resized_outside_the_ladder() -> None:
    """Phase 3's system: a font's size comes from ``type_font``/``apply_type_level``.

    Catches the three ways the tree had got around it:

    * ``wx.Font(12, ...)`` -- the card-image placeholder, a hard-coded 12pt that
      no phase reached because ``dc.SetFont()`` text is invisible to font
      inheritance;
    * ``wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)`` followed by
      ``SetFont`` -- the mana rich-text control, which asked the *platform* for
      a font and so put itself back to 9pt after phase 3 had raised the base to
      10pt on all 18 top-level windows;
    * ``font.Bold()`` / ``MakeBold()`` -- five labels that were headings in
      everything but size, so they read a full ladder step below the headings
      beside them.
    """
    offenders: list[str] = []
    for path in _modules():
        rel = _rel(path)
        if rel in FONT_EXCEPTIONS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            dotted = _dotted(node.func)
            if dotted in {"wx.Font", "wx.FontInfo"}:
                offenders.append(f"{rel}:{node.lineno} {ast.unparse(node)[:70]}")
            elif dotted == "wx.SystemSettings.GetFont":
                offenders.append(f"{rel}:{node.lineno} SystemSettings.GetFont")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {
                "MakeBold",
                "SetPointSize",
                "SetPixelSize",
                "MakeLarger",
                "MakeSmaller",
            }:
                offenders.append(f"{rel}:{node.lineno} .{node.func.attr}()")
    assert offenders == [], (
        "font size and weight come from widgets.stylize's type ladder "
        "(type_font / apply_type_level). If a site is rasterisation geometry "
        "rather than typography, add its module to FONT_EXCEPTIONS with the "
        "reason:\n  " + "\n  ".join(offenders)
    )


def test_bold_only_comes_from_the_ladder_or_a_selection_state() -> None:
    """``.Bold()`` is allowed only where it marks the *selected* item.

    Phase 2 made bold part of the selection idiom (``_SELECTED_BOLD``) and phase
    3 restricted it otherwise to headings, so a ``.Bold()`` that is not inside
    an ``if isSelected`` branch is a label deciding its own weight.
    """
    offenders: list[str] = []
    for path in _modules():
        rel = _rel(path)
        if rel in FONT_EXCEPTIONS:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        selected_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and "selected" in ast.unparse(node.test).lower():
                selected_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Bold"
                and node.lineno not in selected_lines
            ):
                offenders.append(f"{rel}:{node.lineno} {ast.unparse(node)[:70]}")
    assert offenders == [], (
        "bold marks headings (via apply_type_level) and selected items; "
        "nothing else:\n  " + "\n  ".join(offenders)
    )


def test_no_call_site_uses_the_deprecated_multiline_font_bump() -> None:
    """``stylize_textctrl(..., multiline=True)`` is an off-ladder 1.11x step.

    It predates the type scale: it adds one point to the field's font, a ratio
    of 1.11 -- below the ~1.2 perceptual floor that made phase 3 a phase, and
    the exact defect the ladder replaced. The parameter survives only so that a
    caller that already passed it does not move; ``level=`` is the replacement.
    Phase 6b nearly re-introduced it at three sites while routing hand-coloured
    fields through the styling layer, and caught it on screen rather than in the
    diff -- the Timer Alert status box came back a point larger.
    """
    offenders: list[str] = []
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _callee(node) == "stylize_textctrl"):
                continue
            positional_multiline = len(node.args) > 1
            keyword_multiline = any(
                kw.arg == "multiline" and getattr(kw.value, "value", None) is True
                for kw in node.keywords
            )
            if positional_multiline or keyword_multiline:
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert (
        offenders == []
    ), "pass level= instead; multiline= is a pre-type-scale 1-point bump:\n  " + "\n  ".join(
        offenders
    )


# ---------------------------------------------------------------------------
# The sweep's own coverage
# ---------------------------------------------------------------------------


def test_the_sweep_actually_sees_the_tree() -> None:
    """A guard whose enumeration silently returns nothing passes forever.

    Phase 6b's own first draft resolved variable names inside one function scope
    and reported 37 false offenders; the failure mode in the other direction --
    an enumeration that finds no sites at all -- would have been invisible. So
    the counts are pinned loosely: enough to catch the sweep breaking, loose
    enough not to fail on every button added.
    """
    modules = _modules()
    assert len(modules) > 150, f"only {len(modules)} modules under widgets/"
    buttons = sum(
        len(_constructions(ast.parse(p.read_text(encoding="utf-8")), BUTTON_CLASSES))
        for p in modules
    )
    assert buttons > 50, f"the sweep found only {buttons} button constructions"


@pytest.mark.parametrize("name", sorted(ROUTED_ELSEWHERE))
def test_routed_elsewhere_entries_still_point_at_a_construction(name: str) -> None:
    """A ``file:line`` allowlist rots the moment the file is edited above it."""
    rel, lineno = name.rsplit(":", 1)
    path = WIDGETS.parent / rel
    assert path.exists(), f"{rel} no longer exists"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = {ln for ln, _cls, _t in _constructions(tree, BUTTON_CLASSES | NATIVE_THEMED_CLASSES)}
    assert int(lineno) in lines, (
        f"{name} no longer names a widget construction -- the line moved, so "
        "the allowlist is silencing something else now"
    )
