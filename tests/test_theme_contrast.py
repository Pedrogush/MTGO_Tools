"""WCAG contrast and colour-vision regression guard for the design tokens.

This is the acceptance test for the UI redesign (issue #962): every
foreground/background pairing the app actually renders is listed in
``CONTRAST_PAIRS`` and held to a WCAG 2.x AA threshold, and the categorical chart
palette is held to a minimum perceptual distance under simulated colour-vision
deficiency. Later phases add rows; they must not lower thresholds.

The colour maths here is deliberately re-implemented rather than imported from
``utils.constants.theme`` — a bug in the production helper must not be able to
hide behind itself. ``test_production_contrast_helper_agrees`` pins the two
implementations together.

Thresholds
----------
* **4.5:1** — WCAG 2.2 SC 1.4.3, text below the large-text cutoff. At the app's 9pt
  base font *every* type-scale level is below that cutoff, so all text is held to
  4.5:1; see ``theme.is_large_text``.
* **3:1** — SC 1.4.11 for non-text UI boundaries (selection borders, focus rings,
  control outlines, chart fills against the chart background), and the floor this
  project adopts for disabled states. WCAG exempts disabled controls entirely;
  holding them to 3:1 is a deliberate tightening, since "disabled" in this app is
  frequently the state a user is trying to read.
"""

from __future__ import annotations

import itertools
import math

import pytest

from utils.constants import colors
from utils.constants import theme as T

RGB = tuple[int, int, int]

BODY_TEXT = 4.5
NON_TEXT = 3.0


# ---------------------------------------------------------------------------
# WCAG 2.x relative luminance and contrast ratio
# ---------------------------------------------------------------------------
def relative_luminance(rgb: RGB) -> float:
    """WCAG 2.x relative luminance of an 8-bit sRGB colour."""

    def channel(value: int) -> float:
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    """WCAG 2.x contrast ratio, in ``[1.0, 21.0]``."""
    lighter, darker = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_contrast_ratio_reference_values() -> None:
    assert contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert contrast_ratio((0, 0, 0), (0, 0, 0)) == pytest.approx(1.0)
    # WCAG's own worked example: #808080 on #FFFFFF.
    assert contrast_ratio((128, 128, 128), (255, 255, 255)) == pytest.approx(3.95, abs=0.01)


def test_production_contrast_helper_agrees() -> None:
    """theme.contrast_ratio must match this module's independent implementation."""
    samples = [
        T.TEXT_PRIMARY,
        T.TEXT_PLACEHOLDER,
        T.ACCENT_PRIMARY,
        T.SURFACE_BASE,
        T.SURFACE_RAISED,
        (0, 0, 0),
        (255, 255, 255),
    ]
    for a, b in itertools.combinations(samples, 2):
        assert T.contrast_ratio(a, b) == pytest.approx(contrast_ratio(a, b))


# ---------------------------------------------------------------------------
# The pair table
# ---------------------------------------------------------------------------
def _on_every_surface(
    name: str, fg: RGB, minimum: float, reason: str
) -> list[tuple[str, RGB, RGB, float, str]]:
    """A foreground that may land on any surface is checked against all of them."""
    return [
        (f"{name} on SURFACE_{surface.upper()}", fg, bg, minimum, reason)
        for surface, bg in T.SURFACES.items()
    ]


#: (id, foreground, background, minimum ratio, why this pairing exists)
CONTRAST_PAIRS: list[tuple[str, RGB, RGB, float, str]] = [
    *_on_every_surface("TEXT_PRIMARY", T.TEXT_PRIMARY, BODY_TEXT, "default label colour"),
    *_on_every_surface("TEXT_SECONDARY", T.TEXT_SECONDARY, BODY_TEXT, "subtle labels, captions"),
    *_on_every_surface(
        "TEXT_PLACEHOLDER", T.TEXT_PLACEHOLDER, BODY_TEXT, "input hints; was 1.89:1"
    ),
    *_on_every_surface("TEXT_DISABLED", T.TEXT_DISABLED, NON_TEXT, "disabled labels; was 2.90:1"),
    *_on_every_surface("ACCENT_TEXT", T.ACCENT_TEXT, BODY_TEXT, "accent used as body copy"),
    *_on_every_surface("SUCCESS_TEXT", T.SUCCESS_TEXT, BODY_TEXT, "success message text"),
    *_on_every_surface("WARNING_TEXT", T.WARNING_TEXT, BODY_TEXT, "inline warning labels"),
    *_on_every_surface("DANGER_TEXT", T.DANGER_TEXT, BODY_TEXT, "error message text"),
    (
        "STATUS_BAR_FG on STATUS_BAR_BG",
        T.STATUS_BAR_FG,
        T.STATUS_BAR_BG,
        BODY_TEXT,
        "the app's primary feedback channel; measured 1.40:1 before phase 1",
    ),
    # Foreground-on-fill pairs: each *_FILL ships with the only foreground allowed on it.
    (
        "ACCENT_ON_PRIMARY on ACCENT_PRIMARY",
        T.ACCENT_ON_PRIMARY,
        T.ACCENT_PRIMARY,
        BODY_TEXT,
        "primary button label",
    ),
    (
        "SUCCESS_ON_FILL on SUCCESS_FILL",
        T.SUCCESS_ON_FILL,
        T.SUCCESS_FILL,
        BODY_TEXT,
        "success button label",
    ),
    (
        "WARNING_ON_FILL on WARNING_FILL",
        T.WARNING_ON_FILL,
        T.WARNING_FILL,
        BODY_TEXT,
        "warning badge label",
    ),
    (
        "DANGER_ON_FILL on DANGER_FILL",
        T.DANGER_ON_FILL,
        T.DANGER_FILL,
        BODY_TEXT,
        "destructive button label",
    ),
    (
        "DISABLED_ON_FILL on DISABLED_FILL",
        T.DISABLED_ON_FILL,
        T.DISABLED_FILL,
        NON_TEXT,
        "disabled button label",
    ),
    # Semantic tints carry ordinary body text.
    (
        "TEXT_PRIMARY on SUCCESS_SURFACE",
        T.TEXT_PRIMARY,
        T.SUCCESS_SURFACE,
        BODY_TEXT,
        "flex-slot highlighted rows",
    ),
    (
        "TEXT_SECONDARY on SUCCESS_SURFACE",
        T.TEXT_SECONDARY,
        T.SUCCESS_SURFACE,
        BODY_TEXT,
        "secondary text on a success tint",
    ),
    (
        "TEXT_PRIMARY on WARNING_SURFACE",
        T.TEXT_PRIMARY,
        T.WARNING_SURFACE,
        BODY_TEXT,
        "warning banner body",
    ),
    (
        "TEXT_PRIMARY on DANGER_SURFACE",
        T.TEXT_PRIMARY,
        T.DANGER_SURFACE,
        BODY_TEXT,
        "error banner body",
    ),
    # Non-text boundaries.
    *[
        (
            f"SELECTION_BORDER on SURFACE_{surface.upper()}",
            T.SELECTION_BORDER,
            bg,
            NON_TEXT,
            "2px border marking the selected item",
        )
        for surface, bg in T.SURFACES.items()
    ],
    *[
        (
            f"FOCUS_RING on SURFACE_{surface.upper()}",
            T.FOCUS_RING,
            bg,
            NON_TEXT,
            "keyboard focus ring drawn outside the control",
        )
        for surface, bg in T.SURFACES.items()
    ],
    (
        "FOCUS_RING_ON_FILL on ACCENT_PRIMARY",
        T.FOCUS_RING_ON_FILL,
        T.ACCENT_PRIMARY,
        NON_TEXT,
        "focus ring drawn inside a filled control",
    ),
    *_on_every_surface(
        "BORDER_STRONG", T.BORDER_STRONG, NON_TEXT, "outline that is the only control boundary"
    ),
    *_on_every_surface(
        "ACCENT_PRIMARY (as fill)", T.ACCENT_PRIMARY, NON_TEXT, "primary button against its surface"
    ),
    *_on_every_surface(
        "DISABLED_FILL", T.DISABLED_FILL, 1.0, "disabled fill is intentionally low-contrast chrome"
    ),
]

# Selection fills must still carry text.
CONTRAST_PAIRS += [
    (
        f"TEXT_PRIMARY on SELECTION_FILL_ON_{surface.upper()}",
        T.TEXT_PRIMARY,
        fill,
        BODY_TEXT,
        "label inside a selected row",
    )
    for surface, fill in T.SELECTION_FILLS.items()
] + [
    (
        f"TEXT_SECONDARY on SELECTION_FILL_ON_{surface.upper()}",
        T.TEXT_SECONDARY,
        fill,
        BODY_TEXT,
        "secondary label inside a selected row",
    )
    for surface, fill in T.SELECTION_FILLS.items()
]

# Legacy constants that are still live call sites. They are listed by their old
# name so a phase that repoints an alias sees the pair move with it.
CONTRAST_PAIRS += [
    (
        "HINT_TEXT on DARK_ALT (mana_rich_text_ctrl hint)",
        colors.HINT_TEXT,
        colors.DARK_ALT,
        BODY_TEXT,
        "widgets/panels/mana_rich_text_ctrl/frame.py:119; measured 1.89:1 before phase 0",
    ),
    (
        "WARNING_LABEL_COLOR on DARK_PANEL",
        colors.WARNING_LABEL_COLOR,
        colors.DARK_PANEL,
        BODY_TEXT,
        "sideboard guide inline warning label",
    ),
    (
        "LIGHT_TEXT on FLEX_SLOT_HIGHLIGHT_COLOR",
        colors.LIGHT_TEXT,
        colors.FLEX_SLOT_HIGHLIGHT_COLOR,
        BODY_TEXT,
        "sideboard card selector flex-slot rows",
    ),
]

# ---------------------------------------------------------------------------
# Phase 2: the button system and the one selection idiom
# ---------------------------------------------------------------------------
# Every pairing stylize_button can produce, plus the selection token as it is
# actually painted. wxMSW cannot draw a border on a wx.Button, so a selected
# toggle is identified by its *label* colour rather than by an outline -- which
# means that label has to clear AA as body text, not as a non-text boundary.
CONTRAST_PAIRS += [
    (
        "SELECTION_TEXT on SELECTION_FILL_ON_ALT",
        T.SELECTION_TEXT,
        T.SELECTION_FILL_ON_ALT,
        BODY_TEXT,
        "selected Grid/Table/Pile toggle: fill + accent label, no border available",
    ),
    (
        "SELECTION_TEXT on SELECTION_FILL_ON_PANEL",
        T.SELECTION_TEXT,
        T.SELECTION_FILL_ON_PANEL,
        BODY_TEXT,
        "active FlatNotebook tab",
    ),
    (
        "TEXT_SECONDARY on SURFACE_ALT (ghost button)",
        T.TEXT_SECONDARY,
        T.SURFACE_ALT,
        BODY_TEXT,
        "toolbar / view-toggle / pager buttons, kind='ghost'",
    ),
    (
        "TEXT_PRIMARY on SURFACE_RAISED (secondary button)",
        T.TEXT_PRIMARY,
        T.SURFACE_RAISED,
        BODY_TEXT,
        "kind='secondary' (the default for non-primary buttons) and the "
        "per-card + - x chips drawn over card art",
    ),
    (
        "ACCENT_ON_PRIMARY on ACCENT_PRIMARY (checked DarkCheckBox)",
        T.ACCENT_ON_PRIMARY,
        T.ACCENT_PRIMARY,
        NON_TEXT,
        "the tick inside a checked box",
    ),
    (
        "BORDER_STRONG on SURFACE_ALT (unchecked DarkCheckBox)",
        T.BORDER_STRONG,
        T.SURFACE_ALT,
        NON_TEXT,
        "the box edge is the only thing marking an unchecked checkbox",
    ),
]

#: Pairs that cannot be fixed inside the current phase because the fix is a design
#: decision belonging to a later one. id -> reason. Never widen a threshold instead
#: of adding a row here.
#:
#: Phase 0's single entry (DECK_CARD_ACTION_BUTTON_FG on PIN_BUTTON_COLOR) is gone:
#: phase 2 deleted PIN_BUTTON_COLOR and made the Pin button a secondary one.
KNOWN_FAILURES: dict[str, str] = {}


@pytest.mark.parametrize(
    ("pair_id", "fg", "bg", "minimum", "reason"),
    CONTRAST_PAIRS,
    ids=[p[0] for p in CONTRAST_PAIRS],
)
def test_token_pair_meets_wcag_aa(
    pair_id: str, fg: RGB, bg: RGB, minimum: float, reason: str
) -> None:
    ratio = contrast_ratio(fg, bg)
    if pair_id in KNOWN_FAILURES:
        pytest.xfail(KNOWN_FAILURES[pair_id])
    assert ratio >= minimum, (
        f"{pair_id} measures {ratio:.2f}:1, needs {minimum}:1 ({reason}). "
        f"fg={T.to_hex(fg)} bg={T.to_hex(bg)}"
    )


def test_known_failures_are_all_real_pairs() -> None:
    """A stale entry in KNOWN_FAILURES would silently stop guarding anything."""
    ids = {p[0] for p in CONTRAST_PAIRS}
    assert set(KNOWN_FAILURES) <= ids


def test_pair_ids_are_unique() -> None:
    ids = [p[0] for p in CONTRAST_PAIRS]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Colour-vision-deficiency simulation and CIEDE2000
# ---------------------------------------------------------------------------
# Viénot, Brettel & Mollon (1999) dichromat simulation: convert to linear RGB,
# project onto the LMS plane the missing cone type collapses to, convert back.
_LMS_FROM_LINEAR = (
    (0.31399022, 0.63951294, 0.04649755),
    (0.15537241, 0.75789446, 0.08670142),
    (0.01775239, 0.10944209, 0.87256922),
)
_LINEAR_FROM_LMS = (
    (5.47221206, -4.6419601, 0.16963708),
    (-1.1252419, 2.29317094, -0.1678952),
    (0.02980165, -0.19318073, 1.16364789),
)
_DICHROMAT_PROJECTION = {
    "protanopia": ((0.0, 1.05118294, -0.05116099), (0, 1, 0), (0, 0, 1)),
    "deuteranopia": ((1, 0, 0), (0.9513092, 0.0, 0.04264542), (0, 0, 1)),
    "tritanopia": ((1, 0, 0), (0, 1, 0), (-0.86744736, 1.86727089, 0.0)),
}

#: The deficiencies the palette is gated on. Tritanopia is reported by
#: ``test_chart_palette_tritanopia_is_measured`` but not gated: it affects ~0.01%
#: of people and gating on it costs the palette a usable hue.
GATED_DEFICIENCIES = ("deuteranopia", "protanopia")


def _apply(matrix: tuple[tuple[float, ...], ...], vector: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(sum(matrix[i][j] * vector[j] for j in range(3)) for i in range(3))


def _to_linear(value: int) -> float:
    srgb = value / 255.0
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def _from_linear(value: float) -> int:
    value = min(1.0, max(0.0, value))
    encoded = 12.92 * value if value <= 0.0031308 else 1.055 * (value ** (1 / 2.4)) - 0.055
    return min(255, max(0, round(encoded * 255)))


def simulate_deficiency(rgb: RGB, kind: str) -> RGB:
    """Simulate ``rgb`` as seen with the given dichromacy."""
    linear = tuple(_to_linear(c) for c in rgb)
    lms = _apply(_LMS_FROM_LINEAR, linear)
    projected = _apply(_DICHROMAT_PROJECTION[kind], lms)
    return tuple(_from_linear(c) for c in _apply(_LINEAR_FROM_LMS, projected))  # type: ignore[return-value]


def _to_lab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in rgb)
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e_2000(rgb_a: RGB, rgb_b: RGB) -> float:
    """CIEDE2000 colour difference between two sRGB colours."""
    l1, a1, b1 = _to_lab(rgb_a)
    l2, a2, b2 = _to_lab(rgb_b)
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7))) if c_bar > 0 else 0.5
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    delta_lp = l2 - l1
    delta_cp = c2p - c1p
    if c1p * c2p == 0:
        delta_hp = 0.0
    else:
        delta_hp = h2p - h1p
        if delta_hp > 180:
            delta_hp -= 360
        elif delta_hp < -180:
            delta_hp += 360
    delta_capital_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(delta_hp) / 2)

    l_bar = (l1 + l2) / 2
    c_bar_p = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar_p = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar_p = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_bar_p = (h1p + h2p + 360) / 2
    else:
        h_bar_p = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(h_bar_p - 30))
        + 0.24 * math.cos(math.radians(2 * h_bar_p))
        + 0.32 * math.cos(math.radians(3 * h_bar_p + 6))
        - 0.20 * math.cos(math.radians(4 * h_bar_p - 63))
    )
    s_l = 1 + (0.015 * (l_bar - 50) ** 2) / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_p
    s_h = 1 + 0.015 * c_bar_p * t
    r_t = -math.sin(math.radians(2 * 30 * math.exp(-(((h_bar_p - 275) / 25) ** 2)))) * (
        2 * math.sqrt(c_bar_p**7 / (c_bar_p**7 + 25**7)) if c_bar_p > 0 else 0.0
    )

    return math.sqrt(
        (delta_lp / s_l) ** 2
        + (delta_cp / s_c) ** 2
        + (delta_capital_hp / s_h) ** 2
        + r_t * (delta_cp / s_c) * (delta_capital_hp / s_h)
    )


def test_delta_e_reference_values() -> None:
    assert delta_e_2000((255, 255, 255), (255, 255, 255)) == pytest.approx(0.0)
    # Sharma et al. CIEDE2000 test data, converted: white vs black is a large,
    # lightness-dominated difference.
    assert delta_e_2000((255, 255, 255), (0, 0, 0)) > 90


def _worst_case_distance(a: RGB, b: RGB) -> float:
    """Smallest CIEDE2000 across normal vision and each gated deficiency."""
    distances = [delta_e_2000(a, b)]
    distances += [
        delta_e_2000(simulate_deficiency(a, kind), simulate_deficiency(b, kind))
        for kind in GATED_DEFICIENCIES
    ]
    return min(distances)


# ---------------------------------------------------------------------------
# Categorical chart palette
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fill", T.CHART_ALL, ids=[T.to_hex(c) for c in T.CHART_ALL])
def test_chart_fill_reads_against_the_chart_background(fill: RGB) -> None:
    """A wedge/bar must be distinguishable from the chart canvas (SURFACE_BASE)."""
    ratio = contrast_ratio(fill, T.SURFACE_BASE)
    assert ratio >= NON_TEXT, f"{T.to_hex(fill)} on the chart background is {ratio:.2f}:1"


@pytest.mark.parametrize("fill", T.CHART_ALL, ids=[T.to_hex(c) for c in T.CHART_ALL])
def test_chart_fill_carries_a_readable_label(fill: RGB) -> None:
    """Labels drawn on a fill measured 1.10:1 before the redesign."""
    ink = T.chart_label_ink(fill)
    ratio = contrast_ratio(ink, fill)
    assert ratio >= BODY_TEXT, (
        f"label {T.to_hex(ink)} on {T.to_hex(fill)} is {ratio:.2f}:1; "
        "chart_label_ink picked the better of the two label colours and it still fails"
    )


@pytest.mark.parametrize(
    ("a", "b"),
    list(itertools.combinations(T.CHART_ALL, 2)),
    ids=[f"{T.to_hex(a)}~{T.to_hex(b)}" for a, b in itertools.combinations(T.CHART_ALL, 2)],
)
def test_chart_palette_members_are_mutually_distinguishable(a: RGB, b: RGB) -> None:
    """Every pair stays apart under normal, deuteranopic and protanopic vision.

    The threshold is CIEDE2000 >= ``CHART_MIN_DELTA_E`` (12). CIEDE2000's just-
    noticeable difference is ~1-2.3; ~10 is the level usually quoted for "reads as
    a different colour at a glance" on large filled areas, and 12 leaves headroom
    for the ~2 units of error the dichromat simulation itself introduces. The
    outgoing 11-pastel palette scored 2.3 on this measure.
    """
    distance = _worst_case_distance(a, b)
    assert distance >= T.CHART_MIN_DELTA_E, (
        f"{T.to_hex(a)} and {T.to_hex(b)} are {distance:.1f} CIEDE2000 apart in the "
        "worst of normal/deuteranopic/protanopic vision"
    )


def test_chart_palette_stays_apart_under_tritanopia() -> None:
    """Tritanopia is held to a lower floor than deuteranopia/protanopia.

    Gating tritanopia at the full threshold is achievable, but every solution that
    manages it drops the neutral "Other" swatch (see the palette comment in
    theme.py). ~0.01% prevalence against a concrete loss of an encoding slot is the
    trade this floor represents; it still forbids any two members collapsing onto
    each other. The palette measures 8.0.
    """
    worst = min(
        delta_e_2000(simulate_deficiency(a, "tritanopia"), simulate_deficiency(b, "tritanopia"))
        for a, b in itertools.combinations(T.CHART_ALL, 2)
    )
    assert worst >= T.CHART_MIN_DELTA_E_TRITAN, f"tritanopia worst case is {worst:.1f}"


def test_chart_palette_helper_slices_the_prefix() -> None:
    assert T.chart_palette(0) == []
    assert T.chart_palette(3) == list(T.CHART_CATEGORICAL[:3])
    assert T.chart_palette(len(T.CHART_CATEGORICAL)) == list(T.CHART_CATEGORICAL)
    # Beyond the palette it wraps, which is the documented "colour no longer
    # identifies a category" regime.
    wrapped = T.chart_palette(len(T.CHART_CATEGORICAL) + 2)
    assert wrapped[len(T.CHART_CATEGORICAL)] == T.CHART_CATEGORICAL[0]


# ---------------------------------------------------------------------------
# Type scale
# ---------------------------------------------------------------------------
#: Levels smallest to largest. The ladder must be monotonic in this order.
TYPE_ORDER = ("caption", "body", "heading", "title", "display")


def test_type_order_matches_the_declared_steps() -> None:
    """Guards the ordering this module's ladder assertions depend on."""
    assert TYPE_ORDER == tuple(sorted(T.TYPE_STEPS, key=lambda level: T.TYPE_STEPS[level]))


@pytest.mark.parametrize("base", range(6, 25))
def test_type_ladder_is_whole_points_and_clears_1_2x_at_every_step(base: int) -> None:
    """The ladder's core guarantee, checked across every plausible base size.

    The old scale used +-1..4pt off a 9pt base, i.e. 1.10-1.11x steps. Note that
    an integer ladder clears 1.2x at a 9pt base too (7/9/11/14/17) — the base was
    raised for caption legibility, not because the arithmetic failed.
    """
    ladder = T.type_ladder(base)
    sizes = [ladder[level] for level in TYPE_ORDER]
    assert all(isinstance(size, int) for size in sizes), f"non-integer point size in {ladder}"
    assert sizes == sorted(sizes), f"ladder is not monotonic at base {base}: {ladder}"
    for smaller, larger, low, high in zip(TYPE_ORDER, TYPE_ORDER[1:], sizes, sizes[1:]):
        assert high / low >= 1.2, f"base {base}: {smaller} -> {larger} is only {high / low:.3f}x"


def test_declared_base_produces_the_agreed_ladder() -> None:
    assert T.BASE_FONT_POINT_SIZE == 10
    assert [T.type_ladder()[level] for level in TYPE_ORDER] == [8, 10, 12, 15, 18]


def test_font_point_size_returns_whole_points() -> None:
    for level in T.TYPE_STEPS:
        size = T.font_point_size(level=level)
        assert isinstance(size, int) and size > 0


def test_integer_ladder_arithmetic_is_exact() -> None:
    """The ladder must come out of exact integer arithmetic, not float scaling.

    Pins concrete rungs so a refactor to ``ceil(base * 1.2)`` is caught by value.
    (An earlier comment here claimed ``10 * 1.2`` evaluates to
    ``12.000000000000002`` and so ceils to 13. That is not true -- it is exactly
    ``12.0``, and no base in 4..59 diverges. The reason to use ``Fraction(6, 5)``
    is exactness by construction, not this specific bug.)
    """
    assert T.type_ladder(10)["heading"] == 12
    assert T.type_ladder(5)["heading"] == 6


def test_only_headings_and_above_are_bold() -> None:
    assert T.TYPE_BOLD_LEVELS == {"heading", "title", "display"}
    assert "body" not in T.TYPE_BOLD_LEVELS
    assert "caption" not in T.TYPE_BOLD_LEVELS


def test_which_levels_qualify_for_the_large_text_allowance() -> None:
    """Raising the base moves this set, so pin it rather than assume it.

    At the 10pt base, ``title`` (15pt bold) and ``display`` (18pt bold) clear
    WCAG's large-text cutoff. At the old 9pt base only ``display`` did. Nothing
    the app renders as a label, button or table cell is either level.
    """
    large = {level for level in T.TYPE_STEPS if T.is_large_text(level=level)}
    assert large == {"title", "display"}
    assert not T.is_large_text(level="heading"), "12pt bold is not WCAG large text"


def test_no_text_pair_relies_on_the_large_text_allowance() -> None:
    """The 3:1 rows must all be non-text boundaries, never text at a large size.

    This is the check that keeps ``is_large_text`` honest: if a future phase
    lowers a text pair to 3:1 by claiming it is large, this fails.
    """
    text_pairs_at_3to1 = [
        pair_id
        for pair_id, _fg, _bg, minimum, _reason in CONTRAST_PAIRS
        if minimum == NON_TEXT and "TEXT_" in pair_id.split(" on ")[0]
    ]
    assert text_pairs_at_3to1 == [
        "TEXT_DISABLED on SURFACE_" + surface.upper() for surface in T.SURFACES
    ], (
        "only the disabled text token may sit at the 3:1 threshold, and only because "
        f"WCAG exempts disabled controls entirely; found {text_pairs_at_3to1}"
    )


def test_font_point_size_rejects_unknown_levels() -> None:
    with pytest.raises(ValueError, match="unknown type level"):
        T.font_point_size(level="gigantic")


def test_type_ladder_rejects_a_nonsense_base() -> None:
    with pytest.raises(ValueError, match="base font size"):
        T.type_ladder(0)


# ---------------------------------------------------------------------------
# Spacing scale
# ---------------------------------------------------------------------------
def test_spacing_scale_is_on_the_4px_grid() -> None:
    scale = [T.SPACE_XS, T.SPACE_SM, T.SPACE_MD, T.SPACE_LG, T.SPACE_XL]
    assert scale == [4, 8, 16, 24, 32]
    assert all(value % T.SPACE_GRID == 0 for value in scale)
    assert scale == sorted(scale)


def test_legacy_padding_constants_are_untouched() -> None:
    """Phase 3 migrates these; phase 0 must not move the app's layout."""
    from utils.constants import ui_layout

    assert (
        ui_layout.PADDING_XS,
        ui_layout.PADDING_SM,
        ui_layout.PADDING_MD,
        ui_layout.PADDING_LG,
        ui_layout.PADDING_XL,
        ui_layout.PADDING_BASE,
    ) == (2, 4, 6, 10, 12, 8)


# ---------------------------------------------------------------------------
# Alias integrity
# ---------------------------------------------------------------------------
def test_surface_aliases_did_not_change_value() -> None:
    """Renaming the surface trio must not re-tone the app."""
    assert colors.DARK_BG == (20, 22, 27)
    assert colors.DARK_PANEL == (34, 39, 46)
    assert colors.DARK_ALT == (40, 46, 54)
    assert colors.DARK_ACCENT == (59, 130, 246)
    assert colors.LIGHT_TEXT == (236, 236, 236)
    assert colors.SUBDUED_TEXT == (185, 191, 202)
    assert colors.DECK_CARD_ACTION_BUTTON_FG == (12, 14, 18)


def test_aliases_point_at_the_semantic_tokens() -> None:
    assert colors.HINT_TEXT is T.TEXT_PLACEHOLDER
    assert colors.WARNING_LABEL_COLOR is T.WARNING_TEXT
    assert colors.FLEX_SLOT_HIGHLIGHT_COLOR is T.SUCCESS_SURFACE
