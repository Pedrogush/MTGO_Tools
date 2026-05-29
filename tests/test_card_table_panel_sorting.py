"""Tests for the pure sort/grouping helpers behind the deck table/pile views."""

from __future__ import annotations

from typing import Any

import pytest

from widgets.panels.card_table_panel.sorting import (
    COL_COLOR,
    COL_MANA,
    COL_NAME,
    COL_TEXT,
    COL_TYPE,
    PILE_SORT_COLOR,
    PILE_SORT_MV,
    PILE_SORT_TYPE,
    TABLE_ACTION_ADD,
    TABLE_ACTION_REMOVE,
    TABLE_ACTION_SUB,
    action_slot_at,
    color_sort_key,
    group_into_piles,
    is_land,
    pile_key_for,
    sort_table_rows,
    table_sort_key,
)


def _meta_factory(rows: dict[str, dict[str, Any]]):
    def _lookup(name: str) -> dict[str, Any] | None:
        return rows.get(name)

    return _lookup


# A small fixture deck covering creatures, instants, lands, multicolor, MDFC-ish.
@pytest.fixture
def deck_meta() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    meta = {
        "Llanowar Elves": {
            "mana_cost": "{G}",
            "mana_value": 1,
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
            "colors": ["G"],
        },
        "Lightning Bolt": {
            "mana_cost": "{R}",
            "mana_value": 1,
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "colors": ["R"],
        },
        "Counterspell": {
            "mana_cost": "{U}{U}",
            "mana_value": 2,
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "colors": ["U"],
        },
        "Forest": {
            "mana_cost": "",
            "mana_value": 0,
            "type_line": "Basic Land — Forest",
            "oracle_text": "({T}: Add {G}.)",
            "colors": [],
        },
        "Niv-Mizzet, Parun": {
            "mana_cost": "{U}{U}{U}{R}{R}{R}",
            "mana_value": 6,
            "type_line": "Legendary Creature — Dragon Wizard",
            "oracle_text": "This spell can't be countered.",
            "colors": ["U", "R"],
        },
    }
    cards = [
        {"name": "Llanowar Elves", "qty": 4},
        {"name": "Lightning Bolt", "qty": 4},
        {"name": "Counterspell", "qty": 2},
        {"name": "Forest", "qty": 8},
        {"name": "Niv-Mizzet, Parun", "qty": 1},
    ]
    return cards, meta


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------
def test_is_land_recognises_basic_land():
    assert is_land({"type_line": "Basic Land — Forest"}) is True
    assert is_land({"type_line": "Legendary Land"}) is True
    assert is_land({"type_line": "Creature — Elf"}) is False
    assert is_land({}) is False


def test_color_sort_key_orders_wubrg_then_multi_then_colorless():
    keys = [
        color_sort_key({"colors": ["W"]}),
        color_sort_key({"colors": ["U"]}),
        color_sort_key({"colors": ["B"]}),
        color_sort_key({"colors": ["R"]}),
        color_sort_key({"colors": ["G"]}),
        color_sort_key({"colors": ["U", "R"]}),
        color_sort_key({"colors": []}),
    ]
    assert sorted(keys) == keys


# ---------------------------------------------------------------------------
# Table sort
# ---------------------------------------------------------------------------
def test_sort_by_mana_puts_lands_last(deck_meta):
    cards, meta = deck_meta
    sorted_rows = sort_table_rows(cards, _meta_factory(meta), COL_MANA)
    names = [c["name"] for c in sorted_rows]
    # Cheap spells first, lands at the end.
    assert names[0] in {"Llanowar Elves", "Lightning Bolt"}
    assert names[-1] == "Forest"


def test_sort_descending_reverses_order(deck_meta):
    cards, meta = deck_meta
    asc = [c["name"] for c in sort_table_rows(cards, _meta_factory(meta), COL_NAME)]
    desc = [
        c["name"] for c in sort_table_rows(cards, _meta_factory(meta), COL_NAME, descending=True)
    ]
    assert asc == sorted(asc, key=str.lower)
    assert desc == list(reversed(asc))


def test_sort_by_type_groups_creatures_then_instants_then_lands(deck_meta):
    cards, meta = deck_meta
    sorted_rows = sort_table_rows(cards, _meta_factory(meta), COL_TYPE)
    types = [(meta[c["name"]]["type_line"].split(" ")[0]).lower() for c in sorted_rows]
    # The first type bucket should be creatures and the last should be land.
    assert types[0] in {"creature", "legendary"}
    assert "land" in types[-1] or types[-1].startswith("basic")


def test_sort_by_color_orders_w_u_b_r_g(deck_meta):
    cards, meta = deck_meta
    sorted_rows = sort_table_rows(cards, _meta_factory(meta), COL_COLOR)
    # First non-colorless should be U (Counterspell), then R, then G; multicolor
    # follows mono; colorless (lands) last.
    colors = [tuple(meta[c["name"]].get("colors") or []) for c in sorted_rows]
    assert colors[-1] == ()  # Forest is colorless
    # The U-only card comes before the R-only card.
    u_idx = next(i for i, c in enumerate(colors) if c == ("U",))
    r_idx = next(i for i, c in enumerate(colors) if c == ("R",))
    g_idx = next(i for i, c in enumerate(colors) if c == ("G",))
    assert u_idx < r_idx < g_idx


def test_table_sort_key_text_sorts_alphabetically_by_oracle(deck_meta):
    _cards, meta = deck_meta
    bolt = table_sort_key(COL_TEXT, meta["Lightning Bolt"], "Lightning Bolt")
    counter = table_sort_key(COL_TEXT, meta["Counterspell"], "Counterspell")
    assert counter < bolt  # "Counter target spell." < "Lightning Bolt deals..."


# ---------------------------------------------------------------------------
# Pile grouping
# ---------------------------------------------------------------------------
def test_pile_default_groups_by_mv_with_lands_separate(deck_meta):
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_MV)
    labels = [label for (_order, label), _ in piles]
    # Expect cheap MV piles ("1", "2", "6") and a "Lands" pile.
    assert "Lands" in labels
    assert "1" in labels and "2" in labels
    lands_idx = labels.index("Lands")
    one_idx = labels.index("1")
    assert one_idx < lands_idx  # lands sit to the right of nonland piles


def test_pile_expands_by_quantity(deck_meta):
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_MV)
    counts = {label: len(members) for (_order, label), members in piles}
    # 4 Llanowar Elves + 4 Lightning Bolts = 8 in the MV-1 pile.
    assert counts.get("1") == 8
    # 2 Counterspells in the MV-2 pile.
    assert counts.get("2") == 2
    # 8 Forests in the Lands pile.
    assert counts.get("Lands") == 8


def test_pile_assigns_unique_uids(deck_meta):
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_MV)
    uids = [entry["_uid"] for _key, members in piles for entry in members]
    assert len(uids) == len(set(uids))


def test_pile_sort_by_color(deck_meta):
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_COLOR)
    labels = [label for (_order, label), _ in piles]
    # Colorless comes last; multicolor in its own pile; monocolors WUBRG ordered.
    assert "Colorless" in labels
    assert labels[-1] == "Colorless"
    assert "Multicolor" in labels


def test_pile_sort_by_type(deck_meta):
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_TYPE)
    labels = [label for (_order, label), _ in piles]
    assert "Land" in labels
    assert "Creature" in labels


def test_pile_key_for_handles_missing_metadata():
    # A card whose name doesn't exist in metadata should still bucket safely.
    key = pile_key_for({"name": "Unknown", "qty": 1}, {}, PILE_SORT_MV)
    assert key == (0, "0")  # no metadata → mv 0, label "0"


def test_action_slot_at_maps_thirds_to_add_sub_remove():
    width = 60  # three 20px slots
    # First third -> add, middle -> subtract, last -> remove.
    assert action_slot_at(0, width) == TABLE_ACTION_ADD
    assert action_slot_at(19, width) == TABLE_ACTION_ADD
    assert action_slot_at(20, width) == TABLE_ACTION_SUB
    assert action_slot_at(39, width) == TABLE_ACTION_SUB
    assert action_slot_at(40, width) == TABLE_ACTION_REMOVE
    assert action_slot_at(59, width) == TABLE_ACTION_REMOVE


def test_action_slot_at_clamps_out_of_range_and_zero_width():
    # Past the right edge clamps to the last slot; a degenerate width is safe.
    assert action_slot_at(1000, 60) == TABLE_ACTION_REMOVE
    assert action_slot_at(-5, 60) == TABLE_ACTION_ADD
    assert action_slot_at(10, 0) == TABLE_ACTION_ADD
