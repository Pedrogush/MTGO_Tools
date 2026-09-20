"""Tests for the deck capability analysis behind the Patterns tab.

Everything here is wx-free: the whole pipeline lives in
``services/deck_patterns_service/`` precisely so the land grouping, the
castability matching and the maximal-play search can be asserted directly
rather than inferred from a screenshot.
"""

from __future__ import annotations

import pytest

from services.deck_patterns_service.castability import can_pay
from services.deck_patterns_service.lands import (
    LandGroup,
    enumerate_combinations,
    group_lands,
)
from services.deck_patterns_service.mana import (
    ALL_COLORS,
    LandProduction,
    parse_land_production,
    parse_mana_cost,
)
from services.deck_patterns_service.search import (
    Playable,
    PlaySearchCache,
    maximal_plays,
)
from services.deck_patterns_service.service import (
    DeckPatternsService,
    PatternsOptions,
)


def unit(*colors: str) -> frozenset[str]:
    return frozenset(colors)


def cost(text: str):
    return parse_mana_cost(text)


# --------------------------------------------------------------------------- mana costs ---------------------------------------------------------------------------
class TestParseManaCost:
    def test_generic_and_colored_pips(self) -> None:
        parsed = cost("{2}{R}{R}")
        assert parsed.generic == 2
        assert parsed.pips == (unit("R"), unit("R"))
        assert parsed.total == 4

    def test_hybrid_is_one_pip_with_two_options(self) -> None:
        parsed = cost("{U/R}")
        assert parsed.pips == (unit("U", "R"),)
        assert parsed.total == 1

    def test_x_is_recorded_and_counted_as_zero(self) -> None:
        parsed = cost("{X}{R}")
        assert parsed.has_x is True
        assert parsed.total == 1

    def test_monocolored_hybrid_counts_as_generic(self) -> None:
        # {2/R} is deliberately taken as 2 generic so a colourless mana base is
        # never reported as unable to cast it.
        parsed = cost("{2/R}")
        assert parsed.generic == 2
        assert parsed.pips == ()

    def test_phyrexian_keeps_its_colour(self) -> None:
        parsed = cost("{U/P}")
        assert parsed.pips == (unit("U"),)

    def test_colorless_pip_is_distinct_from_generic(self) -> None:
        parsed = cost("{C}")
        assert parsed.pips == (unit("C"),)
        assert parsed.generic == 0

    def test_empty_cost(self) -> None:
        assert cost(None).total == 0
        assert cost("").total == 0


# --------------------------------------------------------------------------- land production ---------------------------------------------------------------------------
class TestParseLandProduction:
    def test_basic_reminder_text(self) -> None:
        assert parse_land_production("({T}: Add {G}.)") == LandProduction(1, unit("G"))

    def test_dual_keeps_the_choice_unresolved(self) -> None:
        production = parse_land_production("({T}: Add {U} or {R}.)")
        assert production == LandProduction(1, unit("U", "R"))

    def test_triome_lists_three_options_as_one_unit(self) -> None:
        production = parse_land_production("({T}: Add {U}, {R}, or {W}.)")
        assert production.amount == 1
        assert production.options == unit("U", "R", "W")

    def test_repeated_symbol_is_two_units(self) -> None:
        production = parse_land_production("{T}: Add {C}{C}. This land deals 2 damage to you.")
        assert production == LandProduction(2, unit("C"))

    def test_any_color(self) -> None:
        production = parse_land_production("{T}, Pay 1 life: Add one mana of any color.")
        assert production.amount == 1
        assert production.options == ALL_COLORS

    def test_falls_back_to_basic_types_when_reminder_is_missing(self) -> None:
        production = parse_land_production(None, "Land — Island Mountain")
        assert production == LandProduction(1, unit("U", "R"))

    def test_land_that_taps_for_nothing(self) -> None:
        assert parse_land_production("{T}: Draw a card.", "Land").produces_mana is False


# --------------------------------------------------------------------------- castability ---------------------------------------------------------------------------
class TestCanPay:
    def test_exact_matching_rejects_what_colour_counting_would_allow(self) -> None:
        """The case that decides precise-vs-approximate (see castability.py).

        Two ``{U, R}`` duals look like "2 red sources and 2 blue sources" to a
        per-colour count, which would wave through ``{U}{U}{R}``. Each land in
        fact picks one colour, so three pips cannot come off two lands.
        """
        duals = (unit("U", "R"), unit("U", "R"))
        assert can_pay(duals, (cost("{U}{R}"),)) is True
        assert can_pay(duals, (cost("{U}{U}"),)) is True
        assert can_pay(duals, (cost("{U}{U}{R}"),)) is False

    def test_three_duals_cannot_pay_four_pips(self) -> None:
        duals = (unit("U", "R"),) * 3
        assert can_pay(duals, (cost("{U}{U}{R}"),)) is True
        assert can_pay(duals, (cost("{U}{U}{R}{R}"),)) is False

    def test_generic_is_paid_by_leftover_units(self) -> None:
        units = (unit("R"), unit("R"), unit("G"))
        assert can_pay(units, (cost("{2}{R}"),)) is True
        assert can_pay(units, (cost("{3}{R}"),)) is False

    def test_colour_it_cannot_make(self) -> None:
        assert can_pay((unit("R"), unit("R")), (cost("{U}"),)) is False

    def test_several_costs_share_one_pool(self) -> None:
        units = (unit("R"), unit("U"))
        assert can_pay(units, (cost("{R}"), cost("{U}"))) is True
        assert can_pay(units, (cost("{R}"), cost("{R}"))) is False

    def test_colorless_pip_needs_a_colorless_source(self) -> None:
        assert can_pay((unit("C"),), (cost("{C}"),)) is True
        assert can_pay((unit("R"),), (cost("{C}"),)) is False

    def test_no_costs_is_payable(self) -> None:
        assert can_pay((unit("R"),), ()) is True


# --------------------------------------------------------------------------- grouping ---------------------------------------------------------------------------
class TestGroupLands:
    def test_lands_sharing_a_production_become_one_group(self) -> None:
        dual = LandProduction(1, unit("U", "R"))
        groups = group_lands(
            {
                "Steam Vents": (4, dual),
                "Sulfur Falls": (4, dual),
                "Island": (2, LandProduction(1, unit("U"))),
            }
        )
        merged = next(g for g in groups if len(g.names) == 2)
        assert merged.names == ("Steam Vents", "Sulfur Falls")
        assert merged.count == 8

    def test_production_amount_separates_groups(self) -> None:
        groups = group_lands(
            {
                "Ancient Tomb": (4, LandProduction(2, unit("C"))),
                "Wastes": (4, LandProduction(1, unit("C"))),
            }
        )
        assert len(groups) == 2

    def test_lands_producing_nothing_are_dropped(self) -> None:
        groups = group_lands({"Nothing": (4, LandProduction(0, frozenset()))})
        assert groups == ()


# --------------------------------------------------------------------------- enumeration ---------------------------------------------------------------------------
class TestEnumerateCombinations:
    @staticmethod
    def groups() -> tuple[LandGroup, ...]:
        return (
            LandGroup(LandProduction(1, unit("R")), ("Mountain",), 4),
            LandGroup(LandProduction(1, unit("U")), ("Island",), 4),
        )

    def test_counts_are_multinomial_not_per_object(self) -> None:
        """Two groups over 3 lands is 4 vectors, not ``C(8, 3)`` = 56."""
        combos = list(enumerate_combinations(self.groups(), 3))
        assert len(combos) == 4
        assert {c.counts for c in combos} == {(3, 0), (2, 1), (1, 2), (0, 3)}

    def test_every_combination_has_the_requested_size(self) -> None:
        for combo in enumerate_combinations(self.groups(), 5):
            assert sum(combo.counts) == 5
            assert combo.total_mana == 5

    def test_availability_is_respected(self) -> None:
        groups = (LandGroup(LandProduction(1, unit("R")), ("Mountain",), 2),)
        assert list(enumerate_combinations(groups, 3)) == []
        assert len(list(enumerate_combinations(groups, 2))) == 1

    def test_zero_and_empty(self) -> None:
        assert list(enumerate_combinations(self.groups(), 0)) == []
        assert list(enumerate_combinations((), 3)) == []

    def test_multi_mana_land_yields_more_units_than_lands(self) -> None:
        groups = (LandGroup(LandProduction(2, unit("C")), ("Ancient Tomb",), 4),)
        combo = next(iter(enumerate_combinations(groups, 2)))
        assert combo.total_mana == 4

    def test_profile_is_order_independent(self) -> None:
        groups = self.groups()
        combos = {c.counts: c for c in enumerate_combinations(groups, 2)}
        assert combos[(1, 1)].profile == tuple(
            sorted((unit("R"), unit("U")), key=lambda u: tuple(sorted(u)))
        )


# --------------------------------------------------------------------------- maximal plays ---------------------------------------------------------------------------
class TestMaximalPlays:
    def test_dominated_subset_is_not_returned(self) -> None:
        """Bolt alone is castable off ``{R}{R}`` but dominated by two Bolts."""
        bolt = Playable("Lightning Bolt", cost("{R}"), quantity=4)
        result = maximal_plays((unit("R"), unit("R")), (bolt,))
        assert [p.as_text() for p in result.plays] == ["2 Lightning Bolt"]

    def test_two_incomparable_plays_are_both_kept(self) -> None:
        """Neither is a subset of the other, so both are maximal."""
        consider = Playable("Consider", cost("{U}"), quantity=4)
        counterspell = Playable("Counterspell", cost("{U}{U}"), quantity=4)
        result = maximal_plays((unit("U"), unit("U")), (consider, counterspell))
        assert {p.as_text() for p in result.plays} == {"2 Consider", "1 Counterspell"}

    def test_uncastable_colour_yields_nothing(self) -> None:
        bolt = Playable("Lightning Bolt", cost("{R}"), quantity=4)
        assert maximal_plays((unit("U"),), (bolt,)).plays == ()

    def test_quantity_caps_the_play(self) -> None:
        bolt = Playable("Lightning Bolt", cost("{R}"), quantity=2)
        result = maximal_plays((unit("R"),) * 4, (bolt,))
        assert [p.as_text() for p in result.plays] == ["2 Lightning Bolt"]

    def test_no_mana_no_plays(self) -> None:
        bolt = Playable("Lightning Bolt", cost("{R}"), quantity=4)
        assert maximal_plays((), (bolt,)).plays == ()

    def test_node_budget_sets_the_truncation_flag(self) -> None:
        playables = tuple(Playable(f"Card {i}", cost("{1}"), quantity=4) for i in range(12))
        result = maximal_plays((unit("R"),) * 7, playables, node_budget=25)
        assert result.truncated is True

    def test_max_plays_sets_the_truncation_flag(self) -> None:
        playables = tuple(Playable(f"Card {i}", cost("{1}"), quantity=2) for i in range(8))
        result = maximal_plays((unit("R"),) * 6, playables, max_plays=3)
        assert result.truncated is True
        assert len(result.plays) <= 3

    def test_a_generous_budget_is_not_truncated(self) -> None:
        bolt = Playable("Lightning Bolt", cost("{R}"), quantity=4)
        assert maximal_plays((unit("R"), unit("R")), (bolt,)).truncated is False


# --------------------------------------------------------------------------- caching ---------------------------------------------------------------------------
class TestPlaySearchCache:
    def test_repeated_profile_is_served_from_cache(self) -> None:
        cache = PlaySearchCache()
        bolt = (Playable("Lightning Bolt", cost("{R}"), quantity=4),)
        profile = (unit("R"), unit("R"))

        first = cache.get(profile, bolt)
        second = cache.get(profile, bolt)

        assert cache.misses == 1
        assert cache.hits == 1
        assert first is second

    def test_distinct_profiles_each_miss(self) -> None:
        cache = PlaySearchCache()
        bolt = (Playable("Lightning Bolt", cost("{R}"), quantity=4),)
        cache.get((unit("R"),), bolt)
        cache.get((unit("R"), unit("R")), bolt)
        assert cache.misses == 2
        assert cache.hits == 0

    def test_cache_hits_when_land_amounts_differ(self) -> None:
        """Where the profile cache actually earns its keep.

        Grouping lands by production already collapses the duplicates for a
        deck whose lands each tap for one mana, so every count vector is a
        distinct profile and the cache never hits. It pays off when a land
        makes *two* mana: one ``Ancient Tomb`` and two ``Wastes`` are different
        combinations, on different turns, with the same profile.
        """
        service = DeckPatternsService(card_manager=_FakeCardManager())
        result = service.analyse(
            [
                {"name": "Ancient Tomb", "qty": 4},
                {"name": "Wastes", "qty": 4},
                {"name": "Karn", "qty": 4},
            ],
            options=PatternsOptions(max_turn=4),
        )
        assert result.cache_hits > 0


# --------------------------------------------------------------------------- service ---------------------------------------------------------------------------
class _FakeCardManager:
    """Just enough card data to drive the service without the real index."""

    CARDS = {
        "Mountain": {"type_line": "Basic Land — Mountain", "oracle_text": "({T}: Add {R}.)"},
        "Island": {"type_line": "Basic Land — Island", "oracle_text": "({T}: Add {U}.)"},
        "Wastes": {"type_line": "Basic Land — Wastes", "oracle_text": "({T}: Add {C}.)"},
        "Ancient Tomb": {"type_line": "Land", "oracle_text": "{T}: Add {C}{C}."},
        "Steam Vents": {
            "type_line": "Land — Island Mountain",
            "oracle_text": "({T}: Add {U} or {R}.)",
        },
        "Lightning Bolt": {"type_line": "Instant", "mana_cost": "{R}"},
        "Consider": {"type_line": "Instant", "mana_cost": "{U}"},
        "Counterspell": {"type_line": "Instant", "mana_cost": "{U}{U}"},
        "Karn": {"type_line": "Planeswalker", "mana_cost": "{4}"},
    }

    is_loaded = True

    def get_card(self, name: str):
        return self.CARDS.get(name)


class TestDeckPatternsService:
    @staticmethod
    def service() -> DeckPatternsService:
        return DeckPatternsService(card_manager=_FakeCardManager())

    def test_split_separates_lands_from_spells(self) -> None:
        lands, playables = self.service().split_deck(
            [
                {"name": "Mountain", "qty": 4},
                {"name": "Lightning Bolt", "qty": 4},
            ]
        )
        assert set(lands) == {"Mountain"}
        assert [p.name for p in playables] == ["Lightning Bolt"]

    def test_unknown_card_is_skipped_not_guessed(self) -> None:
        lands, playables = self.service().split_deck([{"name": "Not A Real Card", "qty": 4}])
        assert lands == {} and playables == ()

    def test_hand_checked_mono_red(self) -> None:
        """Turn 1 off one Mountain is exactly one Bolt; turn 2 is exactly two."""
        result = self.service().analyse(
            [{"name": "Mountain", "qty": 4}, {"name": "Lightning Bolt", "qty": 4}],
            options=PatternsOptions(max_turn=2),
        )
        turn_one = result.turn(1)
        assert turn_one is not None
        assert [c.label for c in turn_one.combinations] == ["1 Mountain"]
        assert [p.as_text() for p in turn_one.combinations[0].plays] == ["1 Lightning Bolt"]

        turn_two = result.turn(2)
        assert turn_two is not None
        assert [p.as_text() for p in turn_two.combinations[0].plays] == ["2 Lightning Bolt"]

    def test_two_colour_turn_two_splits_by_land_mix(self) -> None:
        result = self.service().analyse(
            [
                {"name": "Mountain", "qty": 4},
                {"name": "Island", "qty": 4},
                {"name": "Lightning Bolt", "qty": 4},
                {"name": "Counterspell", "qty": 4},
            ],
            options=PatternsOptions(max_turn=2),
        )
        turn_two = result.turn(2)
        assert turn_two is not None
        by_label = {c.label: {p.as_text() for p in c.plays} for c in turn_two.combinations}
        assert by_label["2 Mountain"] == {"2 Lightning Bolt"}
        assert by_label["2 Island"] == {"1 Counterspell"}
        # One of each casts Bolt only: Counterspell needs two blue.
        assert by_label["1 Mountain, 1 Island"] == {"1 Lightning Bolt"}

    def test_combination_cap_sets_truncated(self) -> None:
        result = self.service().analyse(
            [
                {"name": "Mountain", "qty": 4},
                {"name": "Island", "qty": 4},
                {"name": "Wastes", "qty": 4},
                {"name": "Lightning Bolt", "qty": 4},
            ],
            options=PatternsOptions(max_turn=6, max_combinations=2),
        )
        assert result.truncated is True

    def test_cancellation_stops_early(self) -> None:
        calls = {"n": 0}

        def cancel() -> bool:
            calls["n"] += 1
            return calls["n"] > 2

        result = self.service().analyse(
            [{"name": "Mountain", "qty": 4}, {"name": "Lightning Bolt", "qty": 4}],
            options=PatternsOptions(max_turn=7),
            should_cancel=cancel,
        )
        assert len(result.turns) < 7

    def test_deck_with_no_lands_yields_no_combinations(self) -> None:
        result = self.service().analyse(
            [{"name": "Lightning Bolt", "qty": 4}], options=PatternsOptions(max_turn=3)
        )
        assert all(turn.combinations == () for turn in result.turns)


@pytest.mark.parametrize("turn", [1, 2, 3, 4, 5, 6, 7])
def test_every_turn_reports_combinations_summing_to_the_turn_number(turn: int) -> None:
    service = DeckPatternsService(card_manager=_FakeCardManager())
    result = service.analyse(
        [
            {"name": "Mountain", "qty": 8},
            {"name": "Island", "qty": 8},
            {"name": "Lightning Bolt", "qty": 4},
        ],
        options=PatternsOptions(max_turn=turn),
    )
    reported = result.turn(turn)
    assert reported is not None
    for combination in reported.combinations:
        assert sum(combination.combination.counts) == turn
