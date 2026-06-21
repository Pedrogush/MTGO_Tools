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
    card_colors,
    card_mana_value,
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


def test_card_mana_value_defaults_to_zero_when_missing_or_none():
    # Missing key and explicit None both fall back to 0.0 (e.g. lands).
    assert card_mana_value({}) == 0.0
    assert card_mana_value({"mana_value": None}) == 0.0


def test_card_mana_value_coerces_numeric_strings_and_swallows_bad_values():
    # Numeric strings coerce cleanly; non-numeric values fall back to 0.0
    # instead of raising (defensive against malformed metadata).
    assert card_mana_value({"mana_value": "3"}) == 3.0
    assert card_mana_value({"mana_value": "X"}) == 0.0
    assert card_mana_value({"mana_value": object()}) == 0.0


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


def test_card_colors_normalises_string_and_filters_non_str():
    # A bare string color is wrapped into a single-element list (defensive
    # against metadata that stores colors as "R" rather than ["R"]).
    assert card_colors({"colors": "R"}) == ["R"]
    # Missing/empty colors yield an empty list.
    assert card_colors({}) == []
    assert card_colors({"colors": None}) == []
    # Non-string items in the list are dropped rather than raising downstream.
    assert card_colors({"colors": ["U", 5, None, "R"]}) == ["U", "R"]


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


def test_sort_by_type_orders_all_buckets_creature_through_land():
    # Drive every type bucket so the full creature→planeswalker→instant→sorcery
    # →artifact→enchantment→other→land ordering is asserted, including the
    # instant-between-creature-and-land position the deck fixture can't reach.
    meta = {
        "Bear": {"type_line": "Creature — Bear"},
        "Jace": {"type_line": "Legendary Planeswalker — Jace"},
        "Bolt": {"type_line": "Instant"},
        "Divination": {"type_line": "Sorcery"},
        "Sol Ring": {"type_line": "Artifact"},
        "Pacifism": {"type_line": "Enchantment — Aura"},
        "Conspiracy": {"type_line": "Conspiracy"},
        "Island": {"type_line": "Basic Land — Island"},
    }
    cards = [{"name": n, "qty": 1} for n in meta]
    rows = sort_table_rows(cards, _meta_factory(meta), COL_TYPE)
    assert [c["name"] for c in rows] == [
        "Bear",
        "Jace",
        "Bolt",
        "Divination",
        "Sol Ring",
        "Pacifism",
        "Conspiracy",  # unmatched type_line falls into the "other" bucket
        "Island",
    ]


def test_sort_by_mana_descending_puts_lands_first():
    # With descending=True the land flag (1) sorts ahead of nonland (0), so the
    # land floats to the top and the highest mana value follows.
    meta = {
        "Forest": {"mana_value": 0, "type_line": "Basic Land — Forest"},
        "Bear": {"mana_value": 2, "type_line": "Creature — Bear"},
        "Titan": {"mana_value": 6, "type_line": "Creature — Giant"},
    }
    cards = [{"name": n, "qty": 1} for n in meta]
    rows = sort_table_rows(cards, _meta_factory(meta), COL_MANA, descending=True)
    names = [c["name"] for c in rows]
    assert names[0] == "Forest"  # land flag reversed to the front
    assert names[1:] == ["Titan", "Bear"]  # then highest mana value first


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


def test_table_sort_key_unknown_column_falls_back_to_name(deck_meta):
    # An unrecognised column name falls back to a case-folded name sort rather
    # than raising, so a stray/legacy column id still produces a usable order.
    _cards, meta = deck_meta
    key = table_sort_key("not-a-real-column", meta["Lightning Bolt"], "Lightning Bolt")
    assert key == ("lightning bolt",)


def test_sort_table_rows_unknown_column_orders_by_name(deck_meta):
    cards, meta = deck_meta
    rows = sort_table_rows(cards, _meta_factory(meta), "not-a-real-column")
    names = [c["name"] for c in rows]
    assert names == sorted(names, key=str.lower)


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


def test_pile_sort_by_color_uses_readable_mono_labels(deck_meta):
    # Monochrome piles must carry the spelled-out color name, not the raw
    # WUBRG token, so the pile header reads "Red"/"Green"/"Blue".
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_COLOR)
    labels = [label for (_order, label), _ in piles]
    assert "Red" in labels  # Lightning Bolt
    assert "Green" in labels  # Llanowar Elves
    assert "Blue" in labels  # Counterspell
    # Raw single-letter tokens must never leak into the labels.
    assert not ({"R", "G", "U"} & set(labels))


def test_pile_sort_by_type(deck_meta):
    cards, meta = deck_meta
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_TYPE)
    labels = [label for (_order, label), _ in piles]
    assert "Land" in labels
    assert "Creature" in labels


def test_pile_sort_by_type_orders_buckets_and_capitalises_labels():
    # Every type bucket gets its own capitalised pile, ordered creature first
    # through land last (matching _TYPE_BUCKET_ORDER).
    meta = {
        "Bear": {"type_line": "Creature — Bear"},
        "Jace": {"type_line": "Legendary Planeswalker — Jace"},
        "Bolt": {"type_line": "Instant"},
        "Sol Ring": {"type_line": "Artifact"},
        "Island": {"type_line": "Basic Land — Island"},
    }
    cards = [{"name": n, "qty": 1} for n in meta]
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_TYPE)
    labels = [label for (_order, label), _ in piles]
    assert labels == ["Creature", "Planeswalker", "Instant", "Artifact", "Land"]


def test_pile_intra_pile_members_ordered_by_mana_value_then_name():
    # Within a single pile, members sort by mana value then lowercased name so
    # the stack has a stable visual order regardless of input order.
    meta = {
        "Zealous Conscripts": {"mana_value": 5, "type_line": "Creature — Human"},
        "Acidic Slime": {"mana_value": 5, "type_line": "Creature — Ooze"},
        "Birds of Paradise": {"mana_value": 1, "type_line": "Creature — Bird"},
    }
    # All three land in the same type pile; deliberately unsorted input.
    cards = [
        {"name": "Zealous Conscripts", "qty": 1},
        {"name": "Acidic Slime", "qty": 1},
        {"name": "Birds of Paradise", "qty": 1},
    ]
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_TYPE)
    _key, members = piles[0]
    names = [m["name"] for m in members]
    # MV 1 first; the two MV-5 cards tie on value and fall back to name order.
    assert names == ["Birds of Paradise", "Acidic Slime", "Zealous Conscripts"]


def test_pile_skips_zero_negative_and_missing_quantities():
    # qty<=0 (and a missing qty) expand to no members, and crucially produce no
    # empty pile for that card — only the positive-qty card yields a pile.
    meta = {
        "Real": {"mana_value": 2, "type_line": "Creature — Bear"},
        "ZeroQty": {"mana_value": 3, "type_line": "Creature — Ooze"},
        "NegQty": {"mana_value": 4, "type_line": "Instant"},
        "NoQty": {"mana_value": 5, "type_line": "Sorcery"},
    }
    cards = [
        {"name": "Real", "qty": 2},
        {"name": "ZeroQty", "qty": 0},
        {"name": "NegQty", "qty": -3},
        {"name": "NoQty"},  # missing qty key
    ]
    piles = group_into_piles(cards, _meta_factory(meta), PILE_SORT_MV)
    counts = {label: len(members) for (_order, label), members in piles}
    # Only the positive-qty card produces a pile, and no empty piles linger.
    assert counts == {"2": 2}
    assert all(members for _key, members in piles)


def test_pile_key_for_buckets_high_mana_value_into_seven_plus():
    # Any nonland card with mana value >= 7 collapses into a single "7+" pile,
    # with the bucket clamped to 7 so a MV-9 card lands beside a MV-7 card.
    seven = pile_key_for({"name": "Seven", "qty": 1}, {"mana_value": 7}, PILE_SORT_MV)
    nine = pile_key_for({"name": "Nine", "qty": 1}, {"mana_value": 9}, PILE_SORT_MV)
    six = pile_key_for({"name": "Six", "qty": 1}, {"mana_value": 6}, PILE_SORT_MV)
    assert seven == (7, "7+")
    assert nine == (7, "7+")
    assert seven == nine  # same pile bucket and label
    assert six == (6, "6")  # the cutoff is exclusive below 7


def test_pile_key_for_handles_missing_metadata():
    # A card whose name doesn't exist in metadata should still bucket safely.
    key = pile_key_for({"name": "Unknown", "qty": 1}, {}, PILE_SORT_MV)
    assert key == (0, "0")  # no metadata → mv 0, label "0"


def test_group_into_piles_handles_lookup_returning_none():
    # When get_metadata returns None (card absent from the metadata store), the
    # internal lookup must coerce it to an empty dict so the card still buckets
    # as MV 0 rather than raising on the missing-attribute path.
    cards = [{"name": "Ghost Card", "qty": 2}]
    piles = group_into_piles(cards, lambda _name: None, PILE_SORT_MV)
    labels = [label for (_order, label), _ in piles]
    assert labels == ["0"]
    counts = {label: len(members) for (_order, label), members in piles}
    assert counts["0"] == 2


def test_sort_table_rows_handles_lookup_returning_none():
    # The table sort path must also tolerate a None metadata lookup.
    cards = [{"name": "Ghost Card", "qty": 1}, {"name": "Apparition", "qty": 1}]
    rows = sort_table_rows(cards, lambda _name: None, COL_MANA)
    names = [c["name"] for c in rows]
    assert names == ["Apparition", "Ghost Card"]  # tie on MV 0 → name order


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
