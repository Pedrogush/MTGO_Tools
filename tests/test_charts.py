"""Phase 5: the shared bar-chart builder and the columns it feeds.

These are the parts of the data-display work that hold still without a wx app:
the ordering/aggregation/palette decisions, the WebView markup, and the column
fitting the deck table depends on. The rendering itself is verified on screen --
see the phase 5 notes on why wxHTML was rejected as a fallback.
"""

from __future__ import annotations

from utils.constants.theme import CHART_ALL, CHART_CATEGORICAL, CHART_OTHER, to_hex
from widgets.charts.bars import MAX_BARS, build_bars, build_webview_page

# ---------------------------------------------------------------------------
# build_bars
# ---------------------------------------------------------------------------


def test_bars_are_sorted_descending() -> None:
    bars = build_bars([("b", 10.0), ("a", 30.0), ("c", 20.0)])
    assert [bar.label for bar in bars] == ["a", "c", "b"]


def test_ties_break_on_label_so_the_order_is_stable() -> None:
    """A metagame with several equal shares must not reshuffle between refreshes."""
    first = build_bars([("zeta", 9.1), ("alpha", 9.1), ("mu", 9.1)])
    second = build_bars([("mu", 9.1), ("alpha", 9.1), ("zeta", 9.1)])
    assert [bar.label for bar in first] == [bar.label for bar in second]


def test_zero_valued_entries_are_dropped() -> None:
    """The pie drew a zero-angle wedge *and* a full leader label for these.

    Every capture of the old chart has a pile of overlapping "(0.0%)" strings
    stacked at one o'clock because of it.
    """
    bars = build_bars([("real", 5.0), ("gone", 0.0), ("also gone", 0.0)])
    assert [bar.label for bar in bars] == ["real"]


def test_fraction_is_relative_to_the_longest_bar_not_the_total() -> None:
    bars = build_bars([("a", 40.0), ("b", 10.0)])
    assert bars[0].fraction == 1.0
    assert bars[1].fraction == 0.25


def test_the_tail_is_aggregated_into_one_other_bar() -> None:
    entries = [(f"arch {index}", float(100 - index)) for index in range(MAX_BARS + 5)]
    bars = build_bars(entries, other_label="Other")
    assert len(bars) == MAX_BARS + 1
    assert bars[-1].label == "Other"
    tail_total = sum(value for _label, value in entries[MAX_BARS:])
    assert bars[-1].value_text == f"{tail_total:.1f}%"


def test_no_other_bar_when_everything_fits() -> None:
    bars = build_bars([("a", 3.0), ("b", 2.0)], other_label="Other")
    assert [bar.label for bar in bars] == ["a", "b"]


def test_only_the_top_seven_take_a_hue_and_the_rest_take_the_neutral() -> None:
    """Colour identifies at most seven categories; past that it identifies none.

    Phase 0 capped the palette at seven hues plus a neutral. Rank is carried by
    vertical position and magnitude by bar length, so the tail losing its hue
    costs the reader nothing.
    """
    entries = [(f"arch {index:02d}", float(100 - index)) for index in range(MAX_BARS)]
    bars = build_bars(entries)
    hues = [to_hex(rgb) for rgb in CHART_CATEGORICAL]
    assert [bar.colour for bar in bars[: len(hues)]] == hues
    assert {bar.colour for bar in bars[len(hues) :]} == {to_hex(CHART_OTHER)}


def test_every_bar_colour_comes_from_the_phase_0_palette() -> None:
    """No chart may invent a colour: the palette is the CVD-safe guarantee."""
    entries = [(f"arch {index:02d}", float(100 - index)) for index in range(30)]
    allowed = {to_hex(rgb) for rgb in CHART_ALL}
    assert {bar.colour for bar in build_bars(entries)} <= allowed


def test_empty_input_produces_no_bars() -> None:
    assert build_bars([]) == []
    assert build_bars([("a", 0.0)]) == []


# ---------------------------------------------------------------------------
# build_webview_page
# ---------------------------------------------------------------------------


def test_page_carries_each_label_and_value_exactly_once() -> None:
    """The pie printed every percentage twice -- autopct inside the wedge and
    again in the leader label. One encoding, one number."""
    page = build_webview_page("t", "s", build_bars([("Temur Prowess", 57.1)]), "")
    assert page.count("Temur Prowess") == 2  # cell text + its title= tooltip
    assert page.count("57.1%") == 1


def test_page_escapes_markup_in_archetype_names() -> None:
    page = build_webview_page("t", "s", build_bars([("<b>x</b>", 1.0)]), "")
    assert "<b>x</b>" not in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_a_present_but_tiny_bar_still_has_width() -> None:
    """Length is the encoding, so a row that rounds to a hairline must not
    render as absent."""
    page = build_webview_page("t", "s", build_bars([("big", 1000.0), ("tiny", 0.1)]), "")
    assert "width:0.00%" not in page


def test_empty_state_renders_the_empty_text_and_no_rows() -> None:
    page = build_webview_page("t", "s", [], "No data available")
    assert "No data available" in page
    assert 'class="row"' not in page


def test_title_and_subtitle_are_separate_so_the_period_can_be_pluralised() -> None:
    """The old title was one string, ``Modern Metagame (Last 1 day(s))``."""
    page = build_webview_page("Modern metagame share", "Last day", [], "")
    assert "day(s)" not in page
    assert "Modern metagame share" in page
    assert "Last day" in page
