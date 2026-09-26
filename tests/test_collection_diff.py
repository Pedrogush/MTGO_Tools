"""Deck-minus-collection diff (#1044): the decklist of what a player still needs.

Pure-function tests over the real :class:`DeckParser`; the only thing injected is
the collection lookup, which is the one seam the diff has (tests/README.md Â§1).
The tests under "Through the service" run the same arithmetic through a real
``CollectionService`` so the mixin method and its ``get_owned_count`` wiring are
covered too.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from services.collection_service import CollectionService, build_collection_diff
from utils.card_names import fold_card_name


def _owned(inventory: dict[str, int]):
    """A ``get_owned_count``-shaped lookup over a literal inventory."""
    return lambda name: inventory.get(name, 0)


def test_diff_is_the_issues_worked_example() -> None:
    """The example from #1044: 3 owned Bolts and 4 Islands against 2 and 12."""
    diff = build_collection_diff(
        "2 Lightning Bolt\n12 Island",
        _owned({"Lightning Bolt": 3, "Island": 4}),
    )

    # Bolt is fully covered (3 owned vs 2 needed) and drops out entirely; only
    # the shortfall is written, which is what makes the output a shopping list.
    assert diff.text == "8 Island"
    assert diff.mainboard == [("Island", 8)]
    assert diff.missing_total == 8
    assert diff.required_total == 14


def test_diff_keeps_the_sideboard_split_and_deck_order() -> None:
    deck_text = "4 Colossus Hammer\n4 Ornithopter\n\nSideboard\n2 Dismember"
    diff = build_collection_diff(deck_text, _owned({"Colossus Hammer": 1, "Ornithopter": 4}))

    # Round-trippable: blank line + "Sideboard" is the format the app's own
    # parser and every deck site read back.
    assert diff.text == "3 Colossus Hammer\n\nSideboard\n2 Dismember"
    assert diff.mainboard == [("Colossus Hammer", 3)]
    assert diff.sideboard == [("Dismember", 2)]


def test_owned_copies_are_one_pool_spent_mainboard_first() -> None:
    """A card in both zones draws on the same physical copies, not two budgets."""
    diff = build_collection_diff(
        "4 Lightning Bolt\n\nSideboard\n2 Lightning Bolt",
        _owned({"Lightning Bolt": 3}),
    )

    # 6 needed, 3 owned: the maindeck takes all three, so 1 main + 2 side remain.
    assert diff.mainboard == [("Lightning Bolt", 1)]
    assert diff.sideboard == [("Lightning Bolt", 2)]
    assert diff.missing_total == 3


def test_sideboard_only_diff_still_names_its_zone() -> None:
    diff = build_collection_diff(
        "4 Lightning Bolt\n\nSideboard\n2 Dismember",
        _owned({"Lightning Bolt": 4}),
    )

    # No leading blank line to strip, but the header has to survive or the file
    # reads back as a 2-card maindeck.
    assert diff.text == "Sideboard\n2 Dismember"
    assert diff.mainboard == []


def test_fully_owned_deck_yields_an_empty_diff() -> None:
    diff = build_collection_diff(
        "4 Lightning Bolt\n20 Island", _owned({"Lightning Bolt": 4, "Island": 20})
    )

    assert diff.text == ""
    assert diff.is_empty
    assert diff.missing_total == 0
    assert diff.required_total == 24


def test_unowned_deck_is_returned_whole() -> None:
    diff = build_collection_diff("4 Lightning Bolt\n20 Island", _owned({}))

    assert diff.text == "4 Lightning Bolt\n20 Island"
    assert diff.missing_total == 24


def test_empty_deck_text_yields_an_empty_diff() -> None:
    diff = build_collection_diff("", _owned({"Lightning Bolt": 4}))

    assert diff.text == ""
    assert diff.is_empty
    assert diff.required_total == 0


def test_duplicate_lines_in_one_zone_are_summed_before_the_subtraction() -> None:
    """Two "2 Lightning Bolt" lines are a 4-of, not two independent 2-ofs."""
    diff = build_collection_diff(
        "2 Lightning Bolt\n2 Lightning Bolt",
        _owned({"Lightning Bolt": 3}),
    )

    assert diff.mainboard == [("Lightning Bolt", 1)]


def test_fractional_average_counts_round_up() -> None:
    """Averaged decklists carry fractions; you cannot acquire 0.4 of a card."""
    diff = build_collection_diff("3.4 Lightning Bolt", _owned({"Lightning Bolt": 1}))

    assert diff.mainboard == [("Lightning Bolt", 3)]
    assert diff.required_total == 4


def test_printing_id_suffixes_are_stripped_from_the_output() -> None:
    """A per-card art pointer must not leak into the name looked up or written."""
    deck_text = "4 Lightning Bolt 1a2b3c4d-1111-2222-3333-444455556666"
    diff = build_collection_diff(deck_text, _owned({"Lightning Bolt": 1}))

    assert diff.text == "3 Lightning Bolt"


def test_junk_lines_are_skipped_rather_than_written_out() -> None:
    diff = build_collection_diff(
        "4 Lightning Bolt\nMountain\nnot-a-count Island",
        _owned({}),
    )

    assert diff.text == "4 Lightning Bolt"


def test_two_spellings_of_one_card_share_one_budget() -> None:
    """diff.py's own worked example, and the reason it folds the budget key.

    MTGO writes ``Kili the Resourceful``; Scryfall and the bridge write
    ``Kíli``. A deck can carry both spellings across its two zones, and they
    are the same four pieces of cardboard.

    The premise first, because it is what makes the conclusion mean anything:
    the lookup here knows only the accented spelling, so a second budget entry
    would be opened at zero and the sideboard would ask for both copies. It
    asks for one, because the maindeck's three already spent three of the four.
    """
    inventory = {"Kíli the Resourceful": 4}
    owned = _owned(inventory)
    assert owned("Kíli the Resourceful") == 4
    assert owned("Kili the Resourceful") == 0  # the premise

    diff = build_collection_diff(
        "3 Kíli the Resourceful\n\nSideboard\n2 Kili the Resourceful", owned
    )

    assert diff.mainboard == []
    assert diff.sideboard == [("Kili the Resourceful", 1)]
    assert (diff.required_total, diff.missing_total) == (5, 1)
    # The output keeps the deck's own spelling of the line it is short on.
    assert diff.text == "Sideboard\n1 Kili the Resourceful"


@pytest.mark.parametrize("owned", [0, -3])
def test_a_negative_owned_count_is_treated_as_zero(owned: int) -> None:
    """A miscounted inventory must never inflate the requirement above the deck."""
    diff = build_collection_diff("4 Lightning Bolt", lambda _name: owned)

    assert diff.mainboard == [("Lightning Bolt", 4)]


# ============= Through the service =============


@pytest.fixture(name="service")
def fixture_service() -> CollectionService:
    """A service with a stub card repository: the diff never reaches for one."""
    return CollectionService(card_repository=Mock())


def test_service_build_collection_diff_uses_the_loaded_inventory(
    service: CollectionService,
) -> None:
    service.set_inventory({"lightning bolt": 3, "island": 4})

    diff = service.build_collection_diff("2 Lightning Bolt\n12 Island")

    # get_owned_count's case-insensitive probe is what bridges the deck's
    # title-cased names to the inventory's normalized keys.
    assert diff.text == "8 Island"


def test_service_diff_of_an_empty_collection_is_the_whole_deck(
    service: CollectionService,
) -> None:
    service.clear_inventory()

    diff = service.build_collection_diff("4 Lightning Bolt")

    assert diff.text == "4 Lightning Bolt"


def test_service_folds_both_spellings_onto_the_one_inventory_entry(
    service: CollectionService,
) -> None:
    """The whole path: a folded inventory key, two deck spellings, one budget.

    ``build_inventory`` normalizes with ``fold_card_name``, so this is the key
    shape a real collection load produces (#469).
    """
    service.set_inventory({fold_card_name("Kíli the Resourceful"): 4})

    diff = service.build_collection_diff(
        "3 Kíli the Resourceful\n\nSideboard\n2 Kili the Resourceful"
    )

    assert diff.mainboard == []
    assert diff.sideboard == [("Kili the Resourceful", 1)]
