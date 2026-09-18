"""The Goldfish tab's game state and its geometry (issue #1045).

Two wx-free halves, tested here because both are the kind of thing that is
tedious to check on screen and trivial to check in a list:

*The table.* :class:`~services.deck_service.goldfish.GoldfishTable` is the whole
"game": a shuffled library, a hand, and a play area. Its shuffle takes a seed, so
these assert on **exact** hands rather than on a distribution -- a goldfish that
sometimes deals eight cards or quietly shuffles the sideboard in is not a flaky
test, it is a wrong one, and a distributional assertion would let it through.

*The layout.* :mod:`widgets.panels.deck_goldfish_panel.layout` is where the
clicks land. Hit-testing is the half of a drag-and-drop surface that has no
visible failure mode until the user notices they are tapping the wrong card, and
"topmost wins" in particular is only observable where two cards overlap -- which
in a fanned hand is everywhere.
"""

from __future__ import annotations

import pytest

from services.deck_service.goldfish import (
    OPENING_HAND_SIZE,
    GoldfishTable,
    build_library,
)
from utils.constants import (
    GOLDFISH_CARD_HEIGHT,
    GOLDFISH_CARD_SPAN,
    GOLDFISH_CARD_WIDTH,
    GOLDFISH_HAND_MIN_STEP,
    SPACE_SM,
)
from widgets.panels.deck_goldfish_panel.layout import (
    Box,
    auto_place_fraction,
    card_size,
    drop_fraction,
    hand_boxes,
    hit_test,
    split_regions,
    table_box,
)

#: A real decklist in the app's own text format -- the "4 Card Name" lines, the
#: blank line, then the sideboard -- because that is what reaches the panel.
DECK_TEXT = """4 Colossus Hammer
4 Sigarda's Aid
4 Puresteel Paladin
4 Stoneforge Mystic
4 Lightning Greaves
4 Giver of Runes
4 Esper Sentinel
4 Urza's Saga
4 Inkmoth Nexus
4 Ancient Tomb
20 Plains

3 Damping Sphere
4 Path to Exile
"""

MAINBOARD_SIZE = 60


# ---------------------------------------------------------------------------
# The library
# ---------------------------------------------------------------------------
def test_library_is_one_entry_per_physical_card() -> None:
    library = build_library(DECK_TEXT)
    assert len(library) == MAINBOARD_SIZE
    assert library.count("Colossus Hammer") == 4
    assert library.count("Plains") == 20


def test_the_sideboard_is_not_in_the_library() -> None:
    """A 75-card library would make every opening hand subtly wrong."""
    library = build_library(DECK_TEXT)
    assert "Path to Exile" not in library
    assert "Damping Sphere" not in library


def test_fractional_counts_round_down_to_whole_copies() -> None:
    """Averaged decklists carry fractions; a physical library cannot."""
    assert build_library("2.6 Plains") == ["Plains", "Plains"]


def test_an_empty_decklist_is_an_empty_library() -> None:
    assert build_library("") == []
    assert GoldfishTable("").deck_size == 0


# ---------------------------------------------------------------------------
# Dealing
# ---------------------------------------------------------------------------
def test_a_new_hand_is_seven_cards_off_a_shuffled_library() -> None:
    table = GoldfishTable(DECK_TEXT, seed=1045)
    hand = table.new_hand()
    assert len(hand) == OPENING_HAND_SIZE
    assert table.library_size == MAINBOARD_SIZE - OPENING_HAND_SIZE
    # Every card dealt came out of the decklist.
    assert set(hand) <= set(build_library(DECK_TEXT))


def test_the_same_seed_deals_the_same_hand() -> None:
    """The point of the seed: a hand this test can name."""
    first = GoldfishTable(DECK_TEXT, seed=7).new_hand()
    second = GoldfishTable(DECK_TEXT, seed=7).new_hand()
    assert first == second


def test_different_seeds_deal_different_hands() -> None:
    """A guard against a 'shuffle' that does not.

    Two seeds can legitimately collide on the same *multiset* of cards, so this
    walks a handful rather than asserting on one pair.
    """
    hands = {GoldfishTable(DECK_TEXT, seed=seed).new_hand() for seed in range(8)}
    assert len(hands) > 1


def test_nothing_is_dealt_until_asked() -> None:
    """Loading a deck must not deal: the tab may never be opened, and the deck
    render block this rides on is already the app's heaviest moment."""
    table = GoldfishTable(DECK_TEXT, seed=1)
    assert table.hand == ()
    assert table.library_size == 0
    assert not table.has_dealt


def test_a_new_hand_shuffles_played_cards_back_in() -> None:
    table = GoldfishTable(DECK_TEXT, seed=3)
    table.new_hand()
    table.play(0)
    table.play(0)
    assert len(table.table) == 2

    table.new_hand()
    assert table.table == ()
    assert len(table.hand) == OPENING_HAND_SIZE
    assert table.library_size + len(table.hand) == MAINBOARD_SIZE


def test_drawing_moves_one_card_from_library_to_hand() -> None:
    table = GoldfishTable(DECK_TEXT, seed=4)
    table.new_hand()
    drawn = table.draw()
    assert len(drawn) == 1
    assert table.hand[-1] == drawn[0]
    assert table.library_size == MAINBOARD_SIZE - OPENING_HAND_SIZE - 1


def test_drawing_past_the_end_of_the_library_stops_rather_than_raising() -> None:
    """A goldfish has no loss condition, so decking is just the end of the cards."""
    table = GoldfishTable(DECK_TEXT, seed=5)
    table.new_hand()
    drawn = table.draw(MAINBOARD_SIZE)
    assert len(drawn) == MAINBOARD_SIZE - OPENING_HAND_SIZE
    assert table.library_size == 0
    assert table.draw() == ()


# ---------------------------------------------------------------------------
# Mulligans
# ---------------------------------------------------------------------------
def test_a_mulligan_deals_seven_again_and_counts_itself() -> None:
    table = GoldfishTable(DECK_TEXT, seed=11)
    table.new_hand()
    assert table.mulligans == 0

    hand = table.mulligan()
    assert len(hand) == OPENING_HAND_SIZE, "a London mulligan draws seven, then bottoms"
    assert table.mulligans == 1
    assert table.cards_to_bottom == 1


def test_a_new_hand_resets_the_mulligan_count() -> None:
    """The difference between the two buttons is exactly this line."""
    table = GoldfishTable(DECK_TEXT, seed=12)
    table.mulligan()
    table.mulligan()
    assert table.mulligans == 2

    table.new_hand()
    assert table.mulligans == 0
    assert table.cards_to_bottom == 0


def test_the_bottoming_count_stops_at_a_full_hand() -> None:
    """Eight mulligans do not ask for eight cards back out of seven."""
    table = GoldfishTable(DECK_TEXT, seed=13)
    for _ in range(9):
        table.mulligan()
    assert table.mulligans == 9
    assert table.cards_to_bottom == OPENING_HAND_SIZE


# ---------------------------------------------------------------------------
# The play area
# ---------------------------------------------------------------------------
def test_playing_a_card_moves_it_out_of_hand_and_onto_the_table() -> None:
    table = GoldfishTable(DECK_TEXT, seed=21)
    hand = table.new_hand()
    played = table.play(2, 0.5, 0.25)

    assert played is not None and played.name == hand[2]
    assert len(table.hand) == OPENING_HAND_SIZE - 1
    # The card left the hand rather than being copied out of it.
    assert sorted([*table.hand, played.name]) == sorted(hand)
    assert (played.x, played.y, played.tapped) == (0.5, 0.25, False)


def test_any_card_can_be_played_because_there_are_no_rules() -> None:
    """#1045: "no rules parsing mechanics". A Plains and a Lightning Greaves are
    the same thing to this code, and so is playing eight of them on turn one."""
    table = GoldfishTable(DECK_TEXT, seed=22)
    table.new_hand()
    for _ in range(OPENING_HAND_SIZE):
        assert table.play(0) is not None
    assert table.hand == ()
    assert len(table.table) == OPENING_HAND_SIZE


def test_playing_an_index_that_is_not_in_hand_is_a_no_op() -> None:
    table = GoldfishTable(DECK_TEXT, seed=23)
    table.new_hand()
    assert table.play(99) is None
    assert table.play(-1) is None
    assert len(table.hand) == OPENING_HAND_SIZE


def test_a_position_outside_the_table_is_clamped_onto_it() -> None:
    table = GoldfishTable(DECK_TEXT, seed=24)
    table.new_hand()
    played = table.play(0, -3.0, 9.0)
    assert played is not None
    assert (played.x, played.y) == (0.0, 1.0)


def test_tapping_toggles_and_nothing_untaps_on_its_own() -> None:
    table = GoldfishTable(DECK_TEXT, seed=25)
    table.new_hand()
    table.play(0)

    assert table.toggle_tap(0) is True
    assert table.table[0].tapped is True
    # A draw is the closest thing to a turn this has, and it changes nothing.
    table.draw()
    assert table.table[0].tapped is True
    assert table.toggle_tap(0) is False


def test_moving_a_card_repositions_it_and_brings_it_to_the_front() -> None:
    table = GoldfishTable(DECK_TEXT, seed=27)
    table.new_hand()
    table.play(0, 0.0, 0.0)
    table.play(0, 0.1, 0.1)
    first = table.table[0].name

    assert table.move(0, 0.75, 0.75) is True
    assert table.table[-1].name == first
    assert (table.table[-1].x, table.table[-1].y) == (0.75, 0.75)


def test_a_card_taken_back_returns_untapped() -> None:
    table = GoldfishTable(DECK_TEXT, seed=28)
    table.new_hand()
    played = table.play(0)
    assert played is not None
    table.toggle_tap(0)

    assert table.return_to_hand(0) is True
    assert table.table == ()
    assert table.hand[-1] == played.name
    assert len(table.hand) == OPENING_HAND_SIZE


def test_table_operations_on_a_missing_index_are_no_ops() -> None:
    table = GoldfishTable(DECK_TEXT, seed=29)
    table.new_hand()
    assert table.move(0, 0.5, 0.5) is False
    assert table.toggle_tap(0) is False
    assert table.return_to_hand(0) is False


def test_loading_another_deck_ends_the_game_in_progress() -> None:
    table = GoldfishTable(DECK_TEXT, seed=30)
    table.new_hand()
    table.play(0)
    table.mulligan()

    table.set_deck("4 Lightning Bolt")
    assert table.deck_size == 4
    assert (table.hand, table.table, table.mulligans) == ((), (), 0)
    assert not table.has_dealt


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def test_the_hand_strip_sits_along_the_bottom_and_the_table_takes_the_rest() -> None:
    table_region, hand_region = split_regions(900, 600)
    assert table_region.y == 0
    assert hand_region.y == table_region.height
    assert table_region.height + hand_region.height == 600
    assert hand_region.height > GOLDFISH_CARD_HEIGHT


def test_a_panel_too_short_for_a_card_still_splits_in_two() -> None:
    """Dragging the tab short shows less of both zones, not none of one."""
    table_region, hand_region = split_regions(900, 120)
    assert hand_region.height == 60
    assert table_region.height == 60


def test_a_hand_that_fits_is_laid_out_at_full_card_width() -> None:
    boxes = hand_boxes(7, Box(0, 0, 1200, 160))
    assert len(boxes) == 7
    assert all(box.width == GOLDFISH_CARD_WIDTH for box in boxes)
    steps = {b.x - a.x for a, b in zip(boxes, boxes[1:])}
    assert steps == {GOLDFISH_CARD_WIDTH + SPACE_SM}


def test_a_hand_that_does_not_fit_overlaps_rather_than_running_off_the_edge() -> None:
    """The normal case, not the edge one: nothing stops a goldfish drawing."""
    region = Box(0, 0, 600, 160)
    boxes = hand_boxes(16, region)
    step = boxes[1].x - boxes[0].x
    assert step < GOLDFISH_CARD_WIDTH, "cards must overlap once the strip is full"
    assert step >= GOLDFISH_HAND_MIN_STEP, "but never so far that no title shows"
    assert boxes[0].x >= region.x


def test_an_empty_hand_lays_out_nothing() -> None:
    assert hand_boxes(0, Box(0, 0, 900, 160)) == []


def test_a_tapped_card_is_the_same_card_turned_ninety_degrees() -> None:
    assert card_size(False) == (GOLDFISH_CARD_WIDTH, GOLDFISH_CARD_HEIGHT)
    assert card_size(True) == (GOLDFISH_CARD_HEIGHT, GOLDFISH_CARD_WIDTH)


def test_tapping_a_card_rotates_it_about_its_own_centre() -> None:
    """Anchored anywhere else, a card would jump sideways as it taps."""
    region = Box(0, 0, 800, 400)
    upright = table_box(0.4, 0.6, False, region)
    tapped = table_box(0.4, 0.6, True, region)
    assert upright.x + upright.width // 2 == tapped.x + tapped.width // 2
    assert upright.y + upright.height // 2 == tapped.y + tapped.height // 2


def test_a_card_in_either_corner_stays_on_the_table_either_way_round() -> None:
    region = Box(0, 0, 800, 400)
    for x, y in ((0.0, 0.0), (1.0, 1.0)):
        for tapped in (False, True):
            box = table_box(x, y, tapped, region)
            assert box.x >= region.x
            assert box.y >= region.y
            assert box.x + box.width <= region.x + region.width
            assert box.y + box.height <= region.y + region.height


@pytest.mark.parametrize("position", [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.25, 0.75)])
def test_dropping_a_card_where_it_is_drawn_leaves_it_where_it_is(position) -> None:
    """``drop_fraction`` is ``table_box``'s inverse; a drag that does not move
    the pointer must not move the card."""
    region = Box(0, 0, 900, 500)
    x, y = position
    box = table_box(x, y, False, region)
    centre_x = box.x + box.width // 2
    centre_y = box.y + box.height // 2
    round_tripped = drop_fraction(centre_x, centre_y, region)
    assert round_tripped[0] == pytest.approx(x, abs=0.01)
    assert round_tripped[1] == pytest.approx(y, abs=0.01)


def test_a_table_smaller_than_one_card_does_not_divide_by_zero() -> None:
    tiny = Box(0, 0, GOLDFISH_CARD_SPAN // 2, GOLDFISH_CARD_SPAN // 2)
    assert table_box(0.5, 0.5, False, tiny) is not None
    assert drop_fraction(10, 10, tiny) is not None


def test_click_placed_cards_walk_a_grid_instead_of_stacking_up() -> None:
    placed = [auto_place_fraction(i) for i in range(12)]
    assert len(set(placed)) == len(placed), "successive clicks must not land on one pixel"
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in placed)
    assert placed[0] == (0.0, 0.0)


def test_a_click_finds_the_card_under_it() -> None:
    boxes = hand_boxes(4, Box(0, 0, 1200, 160))
    third = boxes[2]
    assert hit_test(boxes, third.x + 5, third.y + 5) == 2


def test_a_click_on_nothing_finds_nothing() -> None:
    boxes = hand_boxes(3, Box(0, 200, 1200, 160))
    assert hit_test(boxes, 5, 5) is None
    assert hit_test([], 100, 100) is None


def test_where_cards_overlap_the_topmost_one_wins() -> None:
    """Last drawn is topmost. In a fanned hand that is every card but the last,
    and the one whose title is covered is not the one being pointed at."""
    overlapping = [Box(0, 0, 100, 140), Box(50, 0, 100, 140)]
    assert hit_test(overlapping, 75, 70) == 1
    assert hit_test(overlapping, 25, 70) == 0
