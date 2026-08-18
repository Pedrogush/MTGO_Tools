"""Design tokens for the app's dark theme — surfaces, text, semantics, type and spacing.

This module is the single source of truth for the design system introduced by the
UI redesign (issue #962, phase 0). It is deliberately dependency-free: it imports
nothing from ``wx`` and nothing from the rest of ``utils.constants``, so that

* it can be imported (and unit-tested) off-Windows where ``wx`` is unavailable, and
* ``utils.constants.colors`` / ``utils.constants.ui_layout`` can re-export from it
  without an import cycle.

Colours are ``(r, g, b)`` int triples, matching the convention the codebase already
uses with ``wx.Colour(*TOKEN)``. Every foreground/background pairing that the app
actually uses is asserted against WCAG 2.x AA in ``tests/test_theme_contrast.py``;
if you add or change a token here, add or update the pair there too.

Naming convention
-----------------
``SURFACE_*``   background levels, dark to light
``TEXT_*``      foregrounds intended to sit on a ``SURFACE_*``
``*_FILL``      a solid block of colour (button face, badge); pair with ``*_ON_FILL``
``*_ON_FILL``   the foreground that must be used on the matching ``*_FILL``
``*_TEXT``      the semantic colour used *as* a foreground on a ``SURFACE_*``
``*_SURFACE``   a low-alpha semantic tint composited over a ``SURFACE_*``
"""

from __future__ import annotations

RGB = tuple[int, int, int]


def from_hex(value: str) -> RGB:
    """``"#RRGGBB"`` -> ``(r, g, b)``."""
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


_hex = from_hex  # the token definitions below read better with the short name


def mix(fg: RGB, bg: RGB, alpha: float) -> RGB:
    """Composite ``fg`` over opaque ``bg`` at ``alpha`` and return an opaque colour.

    wx has no reliable cross-platform alpha for widget backgrounds, so every
    "N% tint" token in this module is pre-composited against the surface it is
    designed to sit on. Use this helper when a phase needs the same tint over a
    different surface rather than inventing a new hex value.
    """
    return tuple(round(fg[i] * alpha + bg[i] * (1.0 - alpha)) for i in range(3))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Surfaces
# ---------------------------------------------------------------------------
# Four levels, dark to light. The first three keep the exact values of the old
# ad-hoc DARK_BG / DARK_PANEL / DARK_ALT trio: phase 0 renames and documents the
# scale, it does not re-tone the app. SURFACE_RAISED is new and is the lightest
# surface any token in this module is verified against, so a token that clears AA
# on SURFACE_RAISED clears it everywhere.
SURFACE_BASE = _hex("#14161B")  # app/window background (was DARK_BG)
SURFACE_PANEL = _hex("#22272E")  # panels and cards sitting on the base (was DARK_PANEL)
SURFACE_ALT = _hex("#282E36")  # input fields, list rows, wells (was DARK_ALT)
SURFACE_RAISED = _hex("#2F3641")  # popovers, hovered rows, elements above a panel

#: Every surface a foreground token may legitimately land on. The contrast test
#: walks this when a pair does not name one specific surface.
SURFACES: dict[str, RGB] = {
    "base": SURFACE_BASE,
    "panel": SURFACE_PANEL,
    "alt": SURFACE_ALT,
    "raised": SURFACE_RAISED,
}

# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------
# Measured against the worst case (SURFACE_RAISED); ratios in the comments are
# raised/alt/panel/base.
TEXT_PRIMARY = _hex("#ECECEC")  # 10.31 / 11.59 / 12.72 / 15.32  (was LIGHT_TEXT)
TEXT_SECONDARY = _hex("#B9BFCA")  # 6.59 / 7.41 / 8.13 / 9.80    (was SUBDUED_TEXT)
TEXT_PLACEHOLDER = _hex("#96A0AE")  # 4.60 / 5.17 / 5.68 / 6.84
TEXT_DISABLED = _hex("#7A8291")  # 3.15 / 3.54 / 3.88 / 4.68

# The near-black used for text sitting *on* a saturated fill. Every *_FILL token
# below is light enough to carry it at >= 4.5:1.
TEXT_ON_FILL = _hex("#0C0E12")

# ---------------------------------------------------------------------------
# Accent and semantics
# ---------------------------------------------------------------------------
# ACCENT_PRIMARY keeps the app's existing blue. What changes is that it now has
# one job (primary action) and a documented partner set, instead of also being
# the selection, the toggle, the emphasis and the unselected-row border.
ACCENT_PRIMARY = _hex("#3B82F6")
ACCENT_ON_PRIMARY = TEXT_ON_FILL  # 5.25:1 on ACCENT_PRIMARY (white would be 3.68)
# ACCENT_PRIMARY as a *foreground* only reaches 3.31:1 on SURFACE_RAISED, i.e. it
# is large-text/non-text only. Use ACCENT_TEXT whenever the accent has to be read
# as body copy on a dark surface.
ACCENT_TEXT = _hex("#6BA5FF")  # 4.90 / 5.51 / 6.05 / 7.28

SUCCESS_FILL = _hex("#3FB27F")
SUCCESS_ON_FILL = TEXT_ON_FILL  # 7.25:1
SUCCESS_TEXT = _hex("#4ADE9B")  # 7.08 / 7.96 / 8.74 / 10.53
SUCCESS_SURFACE = mix(SUCCESS_FILL, SURFACE_ALT, 0.20)  # #2D4845

WARNING_FILL = _hex("#E0A83C")
WARNING_ON_FILL = TEXT_ON_FILL  # 9.05:1
WARNING_TEXT = _hex("#F0B84E")  # 6.77 / 7.61 / 8.35 / 10.06
WARNING_SURFACE = mix(WARNING_FILL, SURFACE_ALT, 0.20)  # #4D4637

DANGER_FILL = _hex("#E8705F")
DANGER_ON_FILL = TEXT_ON_FILL  # 6.36:1
DANGER_TEXT = _hex("#FF8A80")  # 5.33 / 6.00 / 6.58 / 7.93
DANGER_SURFACE = mix(DANGER_FILL, SURFACE_ALT, 0.20)  # #4E3B3E

# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
# One selection idiom for the whole app: a low-alpha accent fill plus a 2px accent
# border. wx cannot composite, so the fill is pre-mixed per surface.
SELECTION_ALPHA = 0.16
SELECTION_FILL_ON_BASE = mix(ACCENT_PRIMARY, SURFACE_BASE, SELECTION_ALPHA)  # #1A273E
SELECTION_FILL_ON_PANEL = mix(ACCENT_PRIMARY, SURFACE_PANEL, SELECTION_ALPHA)  # #26364E
SELECTION_FILL_ON_ALT = mix(ACCENT_PRIMARY, SURFACE_ALT, SELECTION_ALPHA)  # #2B3B55
SELECTION_FILL_ON_RAISED = mix(ACCENT_PRIMARY, SURFACE_RAISED, SELECTION_ALPHA)  # #31425E
#: The 2px border that marks the selected item. >= 3:1 against all four surfaces,
#: so selection reads as presence-vs-absence rather than fill-vs-stroke.
SELECTION_BORDER = ACCENT_PRIMARY
SELECTION_BORDER_WIDTH = 2

#: The label colour for a control that is *selected* rather than filled: the
#: view-mode toggles, the active notebook tab, a selected row's emphasis text.
#: ACCENT_PRIMARY itself only reaches 3.72:1 as text on SURFACE_ALT, so anything
#: that has to be *read* as accent uses ACCENT_TEXT. 4.54:1 on the tightest
#: selection fill (SELECTION_FILL_ON_ALT), 4.91:1 on panel.
SELECTION_TEXT = ACCENT_TEXT

#: Selection fills keyed by the surface they sit on, for phases that need to pick
#: one dynamically.
SELECTION_FILLS: dict[str, RGB] = {
    "base": SELECTION_FILL_ON_BASE,
    "panel": SELECTION_FILL_ON_PANEL,
    "alt": SELECTION_FILL_ON_ALT,
    "raised": SELECTION_FILL_ON_RAISED,
}

# ---------------------------------------------------------------------------
# Focus
# ---------------------------------------------------------------------------
# FOCUS_RING is only 1.82:1 against ACCENT_PRIMARY, so a focus ring must be drawn
# *outside* the control on the surrounding surface (>= 6:1 there). For a ring that
# has to sit inside a filled control, use FOCUS_RING_ON_FILL.
FOCUS_RING = _hex("#8AB8FF")  # 6.02 / 6.77 / 7.43 / 8.95
FOCUS_RING_ON_FILL = TEXT_ON_FILL  # 5.25:1 inside ACCENT_PRIMARY
FOCUS_RING_WIDTH = 2

# ---------------------------------------------------------------------------
# Borders
# ---------------------------------------------------------------------------
# BORDER_SUBTLE is decorative (card outlines, dividers) and is deliberately below
# 3:1 — WCAG 1.4.11 applies to boundaries that are *required* to identify a
# control, not to ornament. Any border that is the only thing marking a control
# must use BORDER_STRONG.
BORDER_SUBTLE = _hex("#39424E")
BORDER_STRONG = _hex("#7A8291")  # 3.15 / 3.54 / 3.88 / 4.68

# ---------------------------------------------------------------------------
# Disabled
# ---------------------------------------------------------------------------
# Disabled controls lose chroma, not just contrast: a disabled primary button
# becomes DISABLED_FILL, never a dimmed blue.
DISABLED_FILL = _hex("#333A45")
DISABLED_ON_FILL = _hex("#96A0AE")  # 4.33:1 on DISABLED_FILL
DISABLED_TEXT = TEXT_DISABLED
DISABLED_BORDER = _hex("#414B58")

# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------
# The app's primary feedback channel ("Loaded 976 decks…", "Deck ready…").
# wxMSW's wxStatusBar honours SetBackgroundColour and silently ignores
# SetForegroundColour, so the frame's LIGHT_TEXT call never landed and the strip
# measured 1.40:1 — the worst ratio in the app. widgets.status_bar owns an
# own-drawn replacement; these are the colours it paints with.
#
# TEXT_SECONDARY rather than TEXT_PRIMARY because a status strip is ambient
# information that should not compete with the content above it; at 8.13:1 it
# clears AA with room to spare either way.
STATUS_BAR_BG = SURFACE_PANEL
STATUS_BAR_FG = TEXT_SECONDARY

# ---------------------------------------------------------------------------
# Categorical chart palette
# ---------------------------------------------------------------------------
# Constraints every member satisfies (all machine-checked in the contrast test):
#   * >= 3:1 against the chart background (SURFACE_BASE) — non-text boundary,
#   * carries a label at >= 4.5:1 with either CHART_LABEL_INK or CHART_LABEL_PAPER
#     (use :func:`chart_label_ink` to pick),
#   * >= 12 CIEDE2000 from every other member under normal vision *and* under
#     simulated deuteranopia and protanopia. The set measures 14.7; the outgoing
#     11-pastel palette measured 2.3.
#
# Why seven hues plus a neutral rather than the eleven the old palette had: a
# neutral "Other" swatch is only compatible with a palette whose members all keep
# some chroma under simulated CVD. Searching for eleven mutually distinct colours
# does succeed (min 14.6 gated on deuteranopia, protanopia *and* tritanopia), but
# every such solution leans on low-chroma members that collapse onto grey for a
# dichromat, which means no neutral can be added and the aggregate bucket has to
# borrow a hue. Eight with a real neutral is the better trade, especially since the
# planned replacement for the metagame pie is a sorted bar chart where length and
# position carry the data and colour is secondary.
#
# The order is prefix-optimised — the first k members are more mutually distinct
# than an arbitrary k-subset would be — so ``chart_palette(k)`` is the right way
# to take a slice.
CHART_CATEGORICAL: tuple[RGB, ...] = (
    _hex("#8FCBF0"),  # light blue
    _hex("#2C6FB5"),  # deep blue
    _hex("#DB9A2E"),  # amber
    _hex("#2FC08D"),  # green
    _hex("#F7F08A"),  # yellow
    _hex("#C0492E"),  # vermillion
    _hex("#4B989B"),  # teal
)
#: The aggregate "Other"/remainder slice. Neutral by design so it reads as "not a
#: category"; held to the same mutual-distance threshold as the seven hues.
CHART_OTHER = _hex("#DCE0E6")
#: Everything the distinctness guarantee covers: the seven hues plus Other.
CHART_ALL: tuple[RGB, ...] = CHART_CATEGORICAL + (CHART_OTHER,)

CHART_LABEL_INK = TEXT_ON_FILL
CHART_LABEL_PAPER = _hex("#FFFFFF")
#: Minimum CIEDE2000 between any two palette members, under normal vision and
#: under simulated deuteranopia and protanopia. 12 sits well above the ~2.3 the
#: outgoing pastel palette scored and above the ~10 usually quoted as "reads as a
#: different colour at a glance" for large filled areas; this palette measures 14.7.
CHART_MIN_DELTA_E = 12.0
#: Report-only floor for tritanopia (~0.01% prevalence). Gating on it as well is
#: possible but costs the neutral "Other" swatch; this palette measures 8.0.
CHART_MIN_DELTA_E_TRITAN = 6.0


def _relative_luminance(rgb: RGB) -> float:
    """WCAG 2.x relative luminance. Duplicated (not imported) by the contrast test."""

    def channel(value: int) -> float:
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    """WCAG 2.x contrast ratio between two opaque colours (1.0 to 21.0)."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def chart_label_ink(fill: RGB) -> RGB:
    """Return whichever label colour reads better on ``fill``."""
    if contrast_ratio(CHART_LABEL_INK, fill) >= contrast_ratio(CHART_LABEL_PAPER, fill):
        return CHART_LABEL_INK
    return CHART_LABEL_PAPER


def chart_palette(count: int) -> list[RGB]:
    """Return ``count`` categorical colours.

    Slices the prefix-optimised palette; beyond ``len(CHART_CATEGORICAL)`` it wraps,
    which means colour alone no longer identifies a category — pair it with labels,
    ordering or a second channel.
    """
    if count <= 0:
        return []
    palette = list(CHART_CATEGORICAL)
    if count <= len(palette):
        return palette[:count]
    return [palette[i % len(palette)] for i in range(count)]


def to_hex(rgb: RGB) -> str:
    """``(r, g, b)`` -> ``"#RRGGBB"``, for the matplotlib/HTML renderers."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


# ---------------------------------------------------------------------------
# Type scale
# ---------------------------------------------------------------------------
# Five levels on an integer point ladder, every adjacent step >= 1.2x.
#
# The ladder is *derived*, not tabulated: each step up is the smallest integer
# >= 1.2x its predecessor, each step down the largest integer <= its predecessor
# / 1.2. Computed in exact integer arithmetic (1.2 == 6/5) because the float form
# bites — 10 * 1.2 evaluates to 12.000000000000002, whose ceil is 13, not 12.
#
# Worked ladders:
#     base  9 -> 7 / 9 / 11 / 14 / 17   (1.286 / 1.222 / 1.273 / 1.214)
#     base 10 -> 8 / 10 / 12 / 15 / 18  (1.250 / 1.200 / 1.250 / 1.200)
#     base 11 -> 9 / 11 / 14 / 17 / 21  (1.222 / 1.273 / 1.214 / 1.235)
#
# Note that a 9pt base *does* carry a conforming integer ladder — the arithmetic
# was never the problem. What rules 9pt out is that its caption lands at 7pt
# (~9.3px at 96dpi), below anything the platform itself ships. 10pt puts the
# caption at 8pt (~10.7px), a size Windows does use for secondary text, while
# growing body text only 11%. See BASE_FONT_POINT_SIZE.
TYPE_RATIO = 1.2
_RATIO_NUM, _RATIO_DEN = 6, 5  # exact 1.2, for integer-only ladder arithmetic

#: The app's declared base font size, in points. The platform default is 9pt
#: (Segoe UI on Windows); the app overrides it so the type scale has room for a
#: legible caption step. Applied to a window tree by
#: :func:`widgets.stylize.apply_base_font`.
BASE_FONT_POINT_SIZE = 10

#: Level name -> position relative to body. Ordering only; the sizes come from
#: :func:`type_ladder`.
TYPE_STEPS: dict[str, int] = {
    "display": 3,  # one number per screen, e.g. the archetype headline
    "title": 2,  # window/panel titles
    "heading": 1,  # section headings
    "body": 0,  # default
    "caption": -1,  # metadata, timestamps, hints
}

#: Levels that carry bold weight. Bold is a hierarchy signal; when everything is
#: bold, nothing is. Phase 3 audits the 31 existing MakeBold sites against this.
TYPE_BOLD_LEVELS: frozenset[str] = frozenset({"heading", "title", "display"})

#: WCAG's "large text" cutoff: >= 18pt regular or >= 14pt bold. Derived rather
#: than hard-coded so a base-size change updates it — at a 10pt base ``title``
#: (15pt bold) and ``display`` (18pt bold) clear it, everything else does not.
LARGE_TEXT_MIN_PT_REGULAR = 18
LARGE_TEXT_MIN_PT_BOLD = 14


def _step_up(size: int) -> int:
    """Smallest integer >= ``size`` * 1.2, in exact integer arithmetic."""
    return -(-size * _RATIO_NUM // _RATIO_DEN)


def _step_down(size: int) -> int:
    """Largest integer <= ``size`` / 1.2, in exact integer arithmetic."""
    return max(1, size * _RATIO_DEN // _RATIO_NUM)


def type_ladder(base_pt: int = BASE_FONT_POINT_SIZE) -> dict[str, int]:
    """The whole integer ladder for ``base_pt``, keyed by level name.

    Guaranteed by construction to have every adjacent step at >= 1.2x.
    """
    base = int(base_pt)
    if base < 1:
        raise ValueError(f"base font size must be >= 1pt, got {base_pt!r}")
    ladder = {"body": base}
    size = base
    for level in ("heading", "title", "display"):
        size = _step_up(size)
        ladder[level] = size
    ladder["caption"] = _step_down(base)
    return ladder


def font_point_size(base_pt: int = BASE_FONT_POINT_SIZE, level: str = "body") -> int:
    """Whole-point size for ``level``, derived from the base font size."""
    if level not in TYPE_STEPS:
        known = sorted(TYPE_STEPS)
        raise ValueError(f"unknown type level {level!r}; expected one of {known}")
    return type_ladder(base_pt)[level]


def is_large_text(base_pt: int = BASE_FONT_POINT_SIZE, level: str = "body") -> bool:
    """Whether ``level`` qualifies for WCAG's 3:1 large-text threshold."""
    size = font_point_size(base_pt, level)
    minimum = LARGE_TEXT_MIN_PT_BOLD if level in TYPE_BOLD_LEVELS else LARGE_TEXT_MIN_PT_REGULAR
    return size >= minimum


# ---------------------------------------------------------------------------
# Spacing scale
# ---------------------------------------------------------------------------
# A 4px geometric-ish grid. These are additive: phase 0 introduces them, phase 3
# migrates the ~50 sizer sites and the legacy PADDING_* constants onto them. Do
# not change the PADDING_* values before that migration — they are load-bearing
# for the current layout.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32
SPACE_GRID = 4  # every spacing value should be a multiple of this
