"""Phase 5: the table/column decisions, without a wx app.

Covers the deck table's column set and fitting, the deck stats panel's two
renderings, and the WebView-absent switch.
"""

from __future__ import annotations

import pytest

from utils.constants.ui_layout import (
    TOP_CARDS_COL_ARCHETYPES_WIDTH,
    TOP_CARDS_COL_AVG_WIDTH,
    TOP_CARDS_COL_CARD_WIDTH,
    TOP_CARDS_COL_COPIES_WIDTH,
    TOP_CARDS_COL_DECKS_WIDTH,
    TOP_CARDS_COL_FORMATS_WIDTH,
    TOP_CARDS_COL_RANK_WIDTH,
    TOP_CARDS_FRAME_SIZE,
)
from widgets.charts.view import DISABLE_WEBVIEW_ENV, webview_disabled_by_env
from widgets.panels.card_table_panel.sorting import (
    COL_COLOR,
    COL_MANA,
    COL_NAME,
    COL_QTY,
    COL_TEXT,
    COL_TYPE,
    TABLE_COLUMNS,
    sort_table_rows,
)
from widgets.panels.card_table_panel.table_columns import (
    _MIN_NAME_WIDTH,
    _MIN_TEXT_WIDTH,
    _MIN_TYPE_WIDTH,
    cell_text,
)
from widgets.panels.card_table_panel.table_columns import fit_to_width as fit
from widgets.panels.deck_stats_panel.stats_chart_html import (
    DEFAULT_CHART_TITLES,
    build_sections,
)

# Column indices, in TABLE_COLUMNS order.
QTY, MANA, NAME, TYPE, TEXT = range(5)
_NATURAL = {QTY: 30, MANA: 80, NAME: 180, TYPE: 120, TEXT: 320}


def _fit(available: int) -> dict[int, int]:
    return fit(_NATURAL, available, TYPE, TEXT, NAME)


def _total(available: int) -> int:
    merged = dict(_NATURAL)
    merged.update(_fit(available))
    return sum(merged.values())


# ---------------------------------------------------------------------------
# Deck table columns
# ---------------------------------------------------------------------------


def test_quantity_is_its_own_column_not_a_prefix_on_the_name() -> None:
    """It was ``"2× Arid Mesa"`` inside the left-aligned Name column, so the
    quantities could not be scanned as a column at all."""
    card = {"name": "Arid Mesa", "qty": 2}
    assert cell_text(card, {}, COL_QTY) == "2"
    assert cell_text(card, {}, COL_NAME) == "Arid Mesa"


def test_color_is_no_longer_a_displayed_column_but_is_still_a_sort_key() -> None:
    """For every non-land it repeated the Mana column beside it; for a land it
    was the same colourless diamond on every row. The pile view still groups by
    colour, so the key stays."""
    assert COL_COLOR not in TABLE_COLUMNS
    cards = [{"name": "b", "qty": 1}, {"name": "a", "qty": 1}]
    assert [c["name"] for c in sort_table_rows(cards, lambda _n: {}, COL_COLOR)] == ["a", "b"]


def test_columns_are_in_decklist_order() -> None:
    assert TABLE_COLUMNS == (COL_QTY, COL_MANA, COL_NAME, COL_TYPE, COL_TEXT)


def test_sorting_by_quantity_puts_the_biggest_playset_first() -> None:
    cards = [{"name": "one", "qty": 1}, {"name": "four", "qty": 4}, {"name": "two", "qty": 2}]
    ordered = sort_table_rows(cards, lambda _n: {}, COL_QTY)
    assert [card["qty"] for card in ordered] == [4, 2, 1]


# ---------------------------------------------------------------------------
# fit_to_width
# ---------------------------------------------------------------------------


def test_no_shrink_when_the_row_already_fits() -> None:
    assert _fit(sum(_NATURAL.values()) + 50) == {}


#: Everything at its floor: the unshrinkable Qty and Mana columns, Name and Type
#: at their minima, and Text dropped. Below this the row genuinely cannot fit and
#: the grid scrolls horizontally.
_HARD_FLOOR = _NATURAL[QTY] + _NATURAL[MANA] + _MIN_NAME_WIDTH + _MIN_TYPE_WIDTH


@pytest.mark.parametrize("available", [_HARD_FLOOR, 300, 340, 420, 500, 600, 700])
def test_the_row_always_fits_the_width_it_was_given(available: int) -> None:
    """The trailing +/-/x controls are the last column, so a row that overflows
    pushes the destructive control off-screen behind a horizontal scrollbar --
    which is exactly where it was before phase 5."""
    assert _total(available) <= available


def test_the_hard_floor_is_well_under_the_workspace_minimum() -> None:
    """The deck workspace's minimum width comes from the card grid -- two cards
    plus their gutters -- which is far wider than the table's floor, so the
    floor is not reachable through the real layout.
    """
    from utils.constants import DECK_CARD_WIDTH
    from widgets.panels.card_table_panel.frame import CardTablePanel

    assert _HARD_FLOOR < (
        (DECK_CARD_WIDTH + CardTablePanel.GRID_GAP) * CardTablePanel.GRID_MIN_COLUMNS
    )


@pytest.mark.parametrize("available", [340, 420, 500, 600])
def test_no_column_is_shrunk_below_its_minimum(available: int) -> None:
    sizes = _fit(available)
    if sizes.get(TEXT):
        assert sizes[TEXT] >= _MIN_TEXT_WIDTH
    assert sizes.get(TYPE, _NATURAL[TYPE]) >= _MIN_TYPE_WIDTH
    assert sizes.get(NAME, _NATURAL[NAME]) >= _MIN_NAME_WIDTH


def test_text_is_dropped_rather_than_shrunk_into_an_ellipsis() -> None:
    """A 30px oracle-text cell renders "S…" and nothing else, while taking room
    from the columns that could have used it."""
    sizes = _fit(280)
    assert sizes[TEXT] == 0


def test_the_narrow_row_keeps_the_quantity_and_mana_columns_intact() -> None:
    sizes = _fit(280)
    assert QTY not in sizes
    assert MANA not in sizes


# ---------------------------------------------------------------------------
# Deck stats panel: two renderings, one data path
# ---------------------------------------------------------------------------


def test_painted_sections_mirror_the_html_charts() -> None:
    curve = [("1", "6", 6.0, "#111111", "t")]
    colors = [("U", "37%", 37.0, "#222222", "t")]
    types = [("Land", 17, 17, "#333333", "t")]
    hand = [("2", "33.7%", 33.7, "#444444", "t")]
    sections = build_sections(curve, colors, types, hand)
    assert [title for title, _bars in sections] == list(DEFAULT_CHART_TITLES)
    assert [len(bars) for _title, bars in sections] == [1, 1, 1, 1]
    assert sections[2][1][0].value_text == "17"
    assert sections[0][1][0].colour == "#111111"


def test_painted_sections_survive_an_empty_deck() -> None:
    sections = build_sections([], [], [], [])
    assert [bars for _title, bars in sections] == [[], [], [], []]


def test_section_titles_are_translatable_data_not_baked_in() -> None:
    titles = ("Curva", "Cores", "Tipos", "Mao")
    sections = build_sections([], [], [], [], titles)
    assert [title for title, _bars in sections] == list(titles)


# ---------------------------------------------------------------------------
# WebView switch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_the_env_switch_forces_the_fallback(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Exists so the no-WebView2 path can be exercised on a machine that has the
    runtime installed -- otherwise it only ever ships untested."""
    monkeypatch.setenv(DISABLE_WEBVIEW_ENV, value)
    assert webview_disabled_by_env() is True


@pytest.mark.parametrize("value", ["", "0", "no", "off"])
def test_anything_else_leaves_the_webview_enabled(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(DISABLE_WEBVIEW_ENV, value)
    assert webview_disabled_by_env() is False


def test_the_switch_is_read_per_call_not_cached_at_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DISABLE_WEBVIEW_ENV, raising=False)
    assert webview_disabled_by_env() is False
    monkeypatch.setenv(DISABLE_WEBVIEW_ENV, "1")
    assert webview_disabled_by_env() is True


# ---------------------------------------------------------------------------
# Top Cards geometry
# ---------------------------------------------------------------------------


def test_top_cards_columns_fit_the_window_without_horizontal_scrolling() -> None:
    """A column wider than the window is how ``Formats`` ended up clipped by the
    window edge: it was autosized to its widest value with no cap."""
    widths = [
        TOP_CARDS_COL_RANK_WIDTH,
        TOP_CARDS_COL_CARD_WIDTH,
        TOP_CARDS_COL_COPIES_WIDTH,
        TOP_CARDS_COL_DECKS_WIDTH,
        TOP_CARDS_COL_AVG_WIDTH,
        TOP_CARDS_COL_AVG_WIDTH,
        TOP_CARDS_COL_DECKS_WIDTH,
        TOP_CARDS_COL_AVG_WIDTH,
        TOP_CARDS_COL_AVG_WIDTH,
        TOP_CARDS_COL_ARCHETYPES_WIDTH,
        TOP_CARDS_COL_FORMATS_WIDTH,
    ]
    # Window chrome: two 8px margins and a vertical scrollbar.
    assert sum(widths) <= TOP_CARDS_FRAME_SIZE[0] - 48


def test_copies_the_sort_key_is_wider_than_the_columns_beside_it() -> None:
    """The review's "near-uniform column widths, so Copies gets the same weight
    as SB avg-K"."""
    assert TOP_CARDS_COL_COPIES_WIDTH > TOP_CARDS_COL_DECKS_WIDTH
