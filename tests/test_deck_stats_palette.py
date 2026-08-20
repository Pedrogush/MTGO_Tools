"""Phase 6b deferred the deck stats panel's three private colour sets to phase 8.

They were the last chart colours in the app that phase 0's palette did not
reach, and being private module constants is exactly why: the contrast suite
walks ``utils.constants.theme``'s tokens, and these were not tokens.

Measured before the change, all against ``SURFACE_BASE`` -- the ground the bars
are actually drawn on (``stats_chart_html._TRACK_BG``):

===============================  =========  =======================================
set                              worst      what it was
===============================  =========  =======================================
``_TYPE_COLOURS``                3.65:1     ten hand-picked hues. Clears the 3:1
                                            floor -- the defect here is that none
                                            of them is from phase 0's set, so
                                            none carries its CVD guarantee (min
                                            CIEDE2000 14.7 across deuteranopia
                                            and protanopia)
``_HAND_COLOURS``                **2.40:1** ``ACCENT_PRIMARY`` as "good", #4A5568
                                            as "bad" -- a **third** colour
                                            register, an editorial claim
                                            ("2-3 lands is good") the chart never
                                            states and that is deck-dependent,
                                            and six of the eight bars below the
                                            non-text floor
mana curve ramp                  **2.07:1** #93C5FD -> #1E40AF. The tallest bars
                                            in the chart were the ones that
                                            disappeared into the background
===============================  =========  =======================================

3:1 is WCAG 1.4.11's non-text boundary and is what phase 0 holds every chart
fill to. Two of the three failed it; the third is a palette-membership defect,
not a contrast one.
"""

from __future__ import annotations

import pytest

from utils.constants import theme as T
from widgets.panels.deck_stats_panel.stats_chart_html import _curve_colour
from widgets.panels.deck_stats_panel.stats_constants import (
    _FALLBACK_SWATCH,
    _HAND_COLOURS,
    _TYPE_COLOURS,
)

#: WCAG 1.4.11: a boundary or graphical object that conveys information.
NON_TEXT = 3.0

#: Every fill the panel can paint a bar with, except ``_COLOR_MAP`` -- Magic's
#: own W/U/B/R/G identity colours, which name something in the game rather than
#: something in the UI and are allowlisted as domain colours in
#: ``tests/test_widget_audit.py``.
PANEL_FILLS: list[tuple[str, str]] = (
    [(f"_TYPE_COLOURS[{k}]", v) for k, v in _TYPE_COLOURS.items()]
    + [(f"_HAND_COLOURS[{i}]", v) for i, v in enumerate(_HAND_COLOURS)]
    + [(f"curve bucket {b}", _curve_colour(b)) for b in ("0", "1", "2", "3", "4", "5", "6+", "X")]
    + [("_FALLBACK_SWATCH", _FALLBACK_SWATCH)]
)


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


@pytest.mark.parametrize(("name", "value"), PANEL_FILLS, ids=[n for n, _ in PANEL_FILLS])
def test_every_deck_stats_fill_reads_against_the_chart_ground(name: str, value: str) -> None:
    ratio = T.contrast_ratio(_rgb(value), T.SURFACE_BASE)
    assert ratio >= NON_TEXT, f"{name} = {value} is {ratio:.2f}:1 on the chart background"


def test_the_type_bars_come_from_the_phase_0_palette() -> None:
    """Not "these look fine" -- these *are* the palette, in the chart's own order."""
    palette = [T.to_hex(c) for c in T.chart_palette(len(_TYPE_COLOURS))]
    assert list(_TYPE_COLOURS.values()) == palette


def test_the_neutral_is_no_longer_a_card_type() -> None:
    """``CHART_OTHER`` reads as "not one of the categories", which is what it now

    only ever means here: the swatch for an unnamed *colour*. It used to also be
    the fill of an "Other" card-type bar -- a category the Comprehensive Rules
    do not have. See tests/test_deck_stats_types.py.
    """
    assert "Other" not in _TYPE_COLOURS
    assert _FALLBACK_SWATCH == T.to_hex(T.CHART_OTHER)


def test_the_opening_hand_bars_no_longer_use_the_accent_as_a_categorical() -> None:
    """Phase 2 shipped exactly two accent registers and a chart bar is neither.

    Saturated ``ACCENT_PRIMARY`` fill = the single primary action on a surface;
    16% tint / 2px stroke / ``ACCENT_TEXT`` = selected-or-current. Using the same
    fill to mean "this outcome is good" is a third register, and it is the one
    phase 6b flagged as needing a decision rather than a tidy-up.
    """
    accent = T.to_hex(T.ACCENT_PRIMARY)
    assert accent not in _HAND_COLOURS
    assert accent not in _TYPE_COLOURS.values()


def test_the_ordinal_charts_share_one_ramp_and_it_is_monotonic() -> None:
    """Mana value and lands-in-opener are ordered axes, so colour is a ramp.

    Monotonic in luminance, so "further along the axis" and "darker" cannot come
    apart -- which is the only thing the colour is being asked to say.
    """
    samples = [T.chart_ramp(i / 10) for i in range(11)]
    ratios = [T.contrast_ratio(c, T.SURFACE_BASE) for c in samples]
    assert ratios == sorted(ratios, reverse=True)
    assert samples[0] == T.CHART_SEQUENTIAL_LOW
    assert samples[-1] == T.CHART_SEQUENTIAL_HIGH
    # Both ends are palette members, which is what carries the >= 3:1 guarantee
    # into a ramp that is otherwise just two hexes.
    assert T.CHART_SEQUENTIAL_LOW in T.CHART_ALL
    assert T.CHART_SEQUENTIAL_HIGH in T.CHART_ALL


def test_chart_ramp_clamps_rather_than_extrapolating() -> None:
    assert T.chart_ramp(-1.0) == T.CHART_SEQUENTIAL_LOW
    assert T.chart_ramp(2.0) == T.CHART_SEQUENTIAL_HIGH
