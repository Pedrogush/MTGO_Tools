"""Archetype baseline: frequency table, classification, and the root commit.

The pools here are written by hand so every expected classification can be read
straight off the deck definitions -- a card in every list at one count is a
staple, a card in every list at a moving count is a partial staple, and anything
below the cut-off is flex. That makes a failure point at the classifier rather
than at a fixture nobody can check.
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

from repositories.deck_text_cache import DeckTextCache
from repositories.deck_vcs_repository.baseline import (
    BASELINE_EPOCH,
    BaselineRootError,
    baseline_message,
)
from repositories.deck_vcs_repository.repository import DeckVcsRepository
from services.archetype_baseline_service import (
    MEMBERSHIP_THRESHOLD,
    ArchetypeBaselineService,
    BaselineStore,
    CardFrequency,
    CardRole,
    ZoneShape,
    build_baseline,
    build_frequency_table,
    classify_card,
    deck_card_counts,
    jaccard,
    maindeck_names,
    partition_pool,
    pool_zone_sizes,
    similarity_scores,
)
from services.archetype_baseline_service import service as service_module
from services.archetype_baseline_service.frequency import median, zone_size
from services.archetype_baseline_service.membership import MIN_POOL_FOR_FILTERING
from services.archetype_baseline_service.store import baseline_from_dict, baseline_to_dict


def make_deck(*, bolt: int, consider: int, murktide: int = 0, ragavan: int = 0, island: int = 20):
    """One decklist. Only the cards a test cares about vary."""
    lines = [f"{bolt} Lightning Bolt", f"{consider} Consider"]
    if murktide:
        lines.append(f"{murktide} Murktide Regent")
    if ragavan:
        lines.append(f"{ragavan} Ragavan, Nimble Pilferer")
    lines.append(f"{island} Island")
    return "\n".join(lines) + "\n\nSideboard\n3 Abrade\n"


@pytest.fixture
def pool() -> list[str]:
    """A five-deck pool with one card of each role, by construction.

    - Lightning Bolt: 4 in all five      -> staple at 4
    - Consider:       3 or 4 in all five -> partial staple, floor 3
    - Murktide:       in three of five   -> flex (0.6)
    - Ragavan:        in one of five     -> flex (0.2)
    - Abrade (SB):    3 in all five      -> sideboard staple at 3
    """
    return [
        make_deck(bolt=4, consider=4, murktide=4, island=20),
        make_deck(bolt=4, consider=3, murktide=4, island=21),
        make_deck(bolt=4, consider=4, murktide=2, island=22),
        make_deck(bolt=4, consider=3, ragavan=2, island=23),
        make_deck(bolt=4, consider=4, island=24),
    ]


@pytest.fixture
def vcs_repo(tmp_path: Path) -> DeckVcsRepository:
    return DeckVcsRepository(tmp_path / "deck_vcs")


# ------------------------------------------------------------------ frequency ------------------------------------------------------------------
class TestFrequencyTable:
    def test_deck_card_counts_splits_zones(self):
        counts = deck_card_counts("4 Lightning Bolt\n\nSideboard\n3 Abrade\n")
        assert counts[("Lightning Bolt", False)] == 4
        assert counts[("Abrade", True)] == 3

    def test_same_card_in_both_zones_stays_separate(self):
        counts = deck_card_counts("2 Abrade\n\nSideboard\n3 Abrade\n")
        assert counts[("Abrade", False)] == 2
        assert counts[("Abrade", True)] == 3

    def test_duplicate_lines_are_summed(self):
        counts = deck_card_counts("2 Consider\n2 Consider\n")
        assert counts[("Consider", False)] == 4

    def test_table_records_distribution_not_just_presence(self, pool):
        table = build_frequency_table(pool)
        consider = table[("Consider", False)]
        assert consider.decks_with == 5
        assert consider.pool_size == 5
        # Three decks on 4, two on 3 -- the distribution is the whole point.
        assert consider.counts == {4.0: 3, 3.0: 2}
        assert consider.floor_count == 3
        assert consider.max_count == 4
        assert not consider.is_uniform

    def test_play_rate_is_share_of_pool(self, pool):
        table = build_frequency_table(pool)
        assert table[("Murktide Regent", False)].play_rate == pytest.approx(0.6)
        assert table[("Ragavan, Nimble Pilferer", False)].play_rate == pytest.approx(0.2)
        assert table[("Lightning Bolt", False)].play_rate == pytest.approx(1.0)

    def test_average_count_is_among_decks_that_run_it(self, pool):
        # Murktide: 4, 4, 2 across the three decks that run it -> 10/3.
        table = build_frequency_table(pool)
        assert table[("Murktide Regent", False)].average_count == pytest.approx(10 / 3)

    def test_empty_pool_is_empty_table(self):
        assert build_frequency_table([]) == {}
        assert build_frequency_table(["", "   "]) == {}

    def test_zone_sizes_use_the_median(self, pool):
        # Every deck in the fixture is 32 main / 3 sideboard by construction.
        main, side = pool_zone_sizes(pool)
        assert main == 32.0
        assert side == 3.0

    def test_median_ignores_one_outlier_deck(self):
        # A single 80-card Yorion list must not drag the pool's notion of size.
        decks = [make_deck(bolt=4, consider=4, island=20)] * 4
        decks.append("4 Lightning Bolt\n4 Consider\n72 Island\n\nSideboard\n3 Abrade\n")
        main, _side = pool_zone_sizes(decks)
        assert main == 28.0

    def test_zone_size_totals_one_zone_of_one_deck(self):
        counts = deck_card_counts("4 Lightning Bolt\n2 Consider\n\nSideboard\n3 Abrade\n")
        assert zone_size(counts, is_sideboard=False) == 6.0
        assert zone_size(counts, is_sideboard=True) == 3.0


class TestMedian:
    """The zone-size summary, including the half of it no pool here reached.

    Every other pool in this file has an odd number of decks, so the even
    branch -- the one that has to average the middle *two* -- never ran.
    """

    def test_an_odd_pool_takes_the_middle_value(self):
        assert median([62, 58, 60]) == 60.0

    def test_an_even_pool_averages_the_middle_two(self):
        # 58, 59, 61, 62 sorted: no single middle deck exists, so the answer is
        # (59 + 61) / 2 = 60 -- a size no deck in the pool has.
        assert median([58, 62, 59, 61]) == 60.0
        assert median([1, 2]) == 1.5

    def test_the_median_of_nothing_is_zero(self):
        assert median([]) == 0.0

    def test_an_even_pool_gets_an_even_pools_zone_size(self):
        # Mains of 24, 25, 27 and 28 -> 26.0, which is nobody's deck size.
        decks = [make_deck(bolt=4, consider=4, island=island) for island in (16, 17, 19, 20)]
        assert pool_zone_sizes(decks) == (26.0, 3.0)

    def test_a_pool_with_no_decklists_has_no_zone_sizes(self):
        assert pool_zone_sizes([]) == (0.0, 0.0)
        assert pool_zone_sizes(["", "   "]) == (0.0, 0.0)


# ------------------------------------------------------------------ classification ------------------------------------------------------------------
class TestClassification:
    def test_uniform_and_universal_is_a_staple(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        bolt = next(c for c in baseline.cards if c.name == "Lightning Bolt")
        assert bolt.role is CardRole.STAPLE
        assert bolt.fixed_count == 4

    def test_universal_but_variable_is_a_partial_staple_at_its_floor(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        consider = next(c for c in baseline.cards if c.name == "Consider")
        assert consider.role is CardRole.PARTIAL_STAPLE
        # The floor is fixed; the copy above it is flex, not baseline.
        assert consider.fixed_count == 3
        assert consider.flex_above_floor == 1

    def test_a_card_missing_from_one_deck_is_excluded_entirely(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        murktide = next(c for c in baseline.cards if c.name == "Murktide Regent")
        assert murktide.role is CardRole.FLEX
        assert murktide.fixed_count == 0

    def test_sideboard_staple_is_classified_in_its_own_zone(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        abrade = next(c for c in baseline.cards if c.name == "Abrade")
        assert abrade.is_sideboard
        assert abrade.role is CardRole.STAPLE
        assert abrade.fixed_count == 3

    def test_one_dissenting_deck_removes_the_card_outright(self):
        # Nine decks run it, one does not. There is no cut-off to fall back on:
        # the card's range across the pool starts at zero, so it is not baseline.
        decks = [make_deck(bolt=4, consider=4) for _ in range(9)]
        decks.append(make_deck(bolt=4, consider=0))
        baseline = build_baseline(decks, archetype="A", mtg_format="modern")

        assert next(c for c in baseline.cards if c.name == "Consider").role is CardRole.FLEX
        assert next(c for c in baseline.cards if c.name == "Consider").fixed_count == 0
        # ...while the card every list runs stays fixed.
        assert next(c for c in baseline.cards if c.name == "Lightning Bolt").fixed_count == 4

    def test_the_floor_is_what_every_deck_can_afford(self):
        # The user's own example: every deck plays 1-4 copies, so the baseline
        # is one copy -- not the average, the mode, or the maximum.
        decks = [
            make_deck(bolt=1, consider=4),
            make_deck(bolt=2, consider=4),
            make_deck(bolt=4, consider=4),
            make_deck(bolt=3, consider=4),
        ]
        baseline = build_baseline(decks, archetype="A", mtg_format="modern")
        bolt = next(c for c in baseline.cards if c.name == "Lightning Bolt")
        assert bolt.fixed_count == 1
        assert bolt.role is CardRole.PARTIAL_STAPLE

    def test_classify_card_is_directly_callable(self):
        table = build_frequency_table([make_deck(bolt=4, consider=4)] * 3)
        role, fixed = classify_card(table[("Lightning Bolt", False)])
        assert (role, fixed) == (CardRole.STAPLE, 4)

    def test_baseline_may_total_fewer_than_a_legal_deck(self):
        # An expected and correct outcome, not a shortfall to pad out.
        decks = [make_deck(bolt=4, consider=4, island=0), make_deck(bolt=4, consider=0, island=0)]
        baseline = build_baseline(decks, archetype="A", mtg_format="modern")
        assert baseline.main.fixed < 60

    def test_a_card_measured_against_no_pool_is_never_a_staple(self):
        """``classify_card``'s ``pool_size > 0`` guard, on its own.

        ``build_frequency_table`` never emits a record with ``pool_size == 0``
        (it returns an empty table instead), so this can only be reached through
        the exported :func:`classify_card` -- which is where the guard earns its
        keep: ``decks_with == pool_size`` is trivially true at ``0 == 0``, and
        without the guard a card measured against nothing would be reported as
        settled archetype consensus at its floor.
        """
        nothing = CardFrequency(
            name="Lightning Bolt", is_sideboard=False, decks_with=0, pool_size=0, counts={4.0: 0}
        )
        assert nothing.floor_count == 4.0  # the premise: it would otherwise qualify
        assert nothing.play_rate == 0.0
        assert classify_card(nothing) == (CardRole.FLEX, 0.0)

    def test_fractional_counts_reach_the_baseline_intact(self):
        """Averaged decklists carry fractions (DeckAverager), and a fractional
        floor is a real floor -- rounding it would invent a count no list runs."""
        decks = [
            "3.5 Lightning Bolt\n20 Island\n",
            "3.5 Lightning Bolt\n20 Island\n",
            "4 Lightning Bolt\n20 Island\n",
        ]
        baseline = build_baseline(decks, archetype="A", mtg_format="modern")
        bolt = next(c for c in baseline.cards if c.name == "Lightning Bolt")
        assert bolt.role is CardRole.PARTIAL_STAPLE
        assert bolt.fixed_count == 3.5
        assert bolt.flex_above_floor == 0.5
        assert baseline.main.fixed == 23.5
        assert "3.5 Lightning Bolt" in baseline.decklist()


class TestEmptyBaselines:
    """A baseline of nothing, which is a real answer rather than a crash.

    ``partition_pool`` can legitimately keep nobody -- a pool of mutual
    strangers has no members -- so ``build_baseline`` reaches its empty-table
    branch in production, not only when a caller passes ``[]``.
    """

    def test_no_decks_at_all(self):
        baseline = build_baseline([], archetype="A", mtg_format="modern")
        assert baseline.pool_size == 0
        assert baseline.cards == ()
        assert baseline.flex_candidates == ()
        assert baseline.sources == ()
        assert (baseline.main.size, baseline.main.fixed, baseline.main.flex) == (0.0, 0, 0.0)
        assert baseline.flex_slots == 0.0
        assert baseline.decklist() == ""

    def test_a_pool_the_membership_filter_empties(self):
        strangers = [f"4 Card{i}A\n4 Card{i}B\n20 Land{i}\n" for i in range(6)]
        sources = tuple(f"deck-{i}" for i in range(6))
        baseline = build_baseline(strangers, archetype="A", mtg_format="modern", sources=sources)
        # The premise: everybody was examined and nobody was kept.
        assert baseline.membership.examined == 6
        assert baseline.membership.kept_count == 0
        # The conclusion: an empty baseline that names nothing as its source.
        assert baseline.pool_size == 0
        assert baseline.cards == ()
        assert baseline.sources == ()

    def test_a_kept_deck_with_no_card_lines(self):
        # A lone deck is always kept (no pairs to be atypical of), so a blank
        # one reaches the frequency table and empties it there instead.
        baseline = build_baseline(["   "], archetype="A", mtg_format="modern")
        assert baseline.membership.kept_indices == (0,)
        assert baseline.pool_size == 0
        assert baseline.cards == ()


class TestBaselineOrdering:
    """A baseline renders the same way twice, and in the order a reader wants.

    Main deck before sideboard, then most-played first, then by name with case
    ignored. Nothing else in the file pins the tie-breaks, so a sort that fell
    back to insertion order -- or to raw ASCII, which puts every capital before
    every lowercase -- would have gone unnoticed.
    """

    #: Three lists: two cards whose casefolded order is the reverse of their
    #: ASCII order, one card only the first list runs, one sideboard card whose
    #: name sorts before everything.
    RICH = "4 Basalt Monolith\n4 apple Pie\n20 Island\n4 Rare Card\n\nSideboard\n4 Aether Vial\n"
    PLAIN = "4 Basalt Monolith\n4 apple Pie\n20 Island\n\nSideboard\n4 Aether Vial\n"

    def _baseline(self):
        return build_baseline([self.RICH, self.PLAIN, self.PLAIN], archetype="A", mtg_format="m")

    def test_the_whole_order_at_once(self):
        assert [c.name for c in self._baseline().cards] == [
            "apple Pie",  # play rate 1.0, casefolds before "basalt"
            "Basalt Monolith",  # play rate 1.0; raw ASCII would put it first
            "Island",  # play rate 1.0
            "Rare Card",  # play rate 1/3, so it follows regardless of name
            "Aether Vial",  # sideboard, so last despite a play rate of 1.0
        ]

    def test_the_sideboard_follows_the_main_deck_whatever_its_play_rate(self):
        cards = self._baseline().cards
        vial = next(c for c in cards if c.name == "Aether Vial")
        assert vial.play_rate == 1.0
        assert cards.index(vial) == len(cards) - 1

    def test_flex_candidates_break_a_tied_play_rate_on_the_bigger_average(self):
        # Two cards in two of four lists each -- the same play rate -- at four
        # copies and at one. The builder filling a slot wants the four first.
        decks = [
            "4 Lightning Bolt\n20 Island\n4 Big Card\n",
            "4 Lightning Bolt\n20 Island\n1 Small Card\n",
            "4 Lightning Bolt\n20 Island\n4 Big Card\n",
            "4 Lightning Bolt\n20 Island\n1 Small Card\n",
        ]
        candidates = build_baseline(decks, archetype="A", mtg_format="m").flex_candidates
        assert [(c.name, c.play_rate, c.average_count) for c in candidates] == [
            ("Big Card", 0.5, 4.0),
            ("Small Card", 0.5, 1.0),
        ]


# ------------------------------------------------------------------ flex arithmetic ------------------------------------------------------------------
class TestFlexSlots:
    def test_fixed_and_flex_slots_add_up_to_the_zone(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        # Main median is 32; fixed is Bolt 4 + Consider floor 3 + Island floor 20.
        assert baseline.main.fixed == 27
        assert baseline.main.size == 32
        assert baseline.main.flex == 5
        # Every list runs the same three Abrade, so the sideboard commits every
        # slot it has and the whole pool's free space is the maindeck's five.
        assert baseline.sideboard.size == 3
        assert baseline.sideboard.fixed == 3
        assert baseline.sideboard.flex == 0
        assert baseline.flex_slots == 5

    def test_flex_is_never_negative(self):
        """The clamp on the type, because the pipeline above cannot reach it.

        Nothing ``build_baseline`` can be handed makes ``max(0.0, ...)`` fire: a
        card is fixed at its floor across the pool, so the fixed total is
        bounded by the smallest deck's zone, which is never above the median.
        (The comment this replaces claimed the opposite, on a pool whose median
        is 30 against a fixed of 20 -- see the test below.) The guard is still
        worth keeping, since ``ZoneShape`` is a public dataclass anyone may
        build, so it is tested where it lives rather than through a pool that
        cannot produce it.
        """
        assert ZoneShape(size=20.0, fixed=27.0).flex == 0.0
        # ...and it is a clamp, not a floor applied to everything.
        assert ZoneShape(size=60.0, fixed=27.0).flex == 33.0

    def test_the_fixed_total_is_bounded_by_the_smallest_deck_in_the_pool(self):
        """Two 40-card lists and two 20-card ones: the median is 30, the floor 20.

        The number that matters is ``fixed``, which is what every deck in the
        pool can afford -- so the two small lists cap it at 20 even though half
        the pool has twice the room. The ten slots between that and the median
        are the pool's disagreement about how big the deck is, reported as flex.
        """
        decks = ["40 Island\n", "40 Island\n", "20 Island\n", "20 Island\n"]
        baseline = build_baseline(decks, archetype="A", mtg_format="modern")
        assert baseline.main.size == 30
        assert baseline.main.fixed == 20
        assert baseline.main.flex == 10

    def test_flex_candidates_are_ranked_by_play_rate(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        main_rates = [c.play_rate for c in baseline.flex_candidates if not c.is_sideboard]
        assert main_rates == sorted(main_rates, reverse=True)

    def test_partial_staple_remainder_is_a_flex_candidate(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        consider = next(c for c in baseline.flex_candidates if c.name == "Consider")
        # It is fixed at 3 and competing for a 4th slot -- both facts matter.
        assert consider.above_floor is True

    def test_plain_flex_card_is_not_marked_above_floor(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        murktide = next(c for c in baseline.flex_candidates if c.name == "Murktide Regent")
        assert murktide.above_floor is False

    def test_a_pure_staple_is_not_a_flex_candidate(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        assert not [c for c in baseline.flex_candidates if c.name == "Lightning Bolt"]


# ------------------------------------------------------------------ baseline decklist ------------------------------------------------------------------
class TestBaselineDecklist:
    def test_decklist_holds_staples_and_floors_only(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        text = baseline.decklist()
        assert "4 Lightning Bolt" in text
        assert "3 Consider" in text  # the floor, not the modal 4
        assert "Murktide" not in text  # flex is not committed to
        assert "3 Abrade" in text

    def test_decklist_is_canonically_normalized(self, pool):
        from repositories.deck_vcs_repository.normalize import normalize_decklist

        text = build_baseline(pool, archetype="A", mtg_format="modern").decklist()
        assert text == normalize_decklist(text)


# ------------------------------------------------------------------ root commit ------------------------------------------------------------------
class TestBaselineRootCommit:
    def test_root_sha_is_identical_across_separate_decks(self, vcs_repo):
        text = "4 Lightning Bolt\n2 Consider\n"
        first = vcs_repo.seed_baseline_root(
            "deck-a", text, archetype="Izzet Murktide", mtg_format="modern"
        )
        second = vcs_repo.seed_baseline_root(
            "deck-b", text, archetype="Izzet Murktide", mtg_format="modern"
        )
        # Separate repos, same ancestor: this is what makes cross-player diffs
        # against the archetype well defined without a shared repo.
        assert first == second

    def test_root_sha_is_stable_across_processes(self, vcs_repo):
        # Nothing time-dependent may enter the sha, or two players computing the
        # same baseline on different days would not share a root.
        text = "4 Lightning Bolt\n2 Consider\n"
        sha = vcs_repo.seed_baseline_root("d", text, archetype="A", mtg_format="modern")
        with tempfile.TemporaryDirectory() as other_root:
            other = DeckVcsRepository(Path(other_root))
            again = other.seed_baseline_root("d", text, archetype="A", mtg_format="modern")
        assert sha == again

    def test_reordered_baseline_text_gives_the_same_root(self, vcs_repo):
        first = vcs_repo.seed_baseline_root(
            "a", "4 Lightning Bolt\n2 Consider\n", archetype="A", mtg_format="modern"
        )
        second = vcs_repo.seed_baseline_root(
            "b", "2 Consider\n4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        assert first == second

    def test_different_baseline_gives_a_different_root(self, vcs_repo):
        first = vcs_repo.seed_baseline_root(
            "a", "4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        second = vcs_repo.seed_baseline_root(
            "b", "3 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        assert first != second

    def test_different_archetype_gives_a_different_root(self, vcs_repo):
        text = "4 Lightning Bolt\n"
        first = vcs_repo.seed_baseline_root("a", text, archetype="A", mtg_format="modern")
        second = vcs_repo.seed_baseline_root("b", text, archetype="B", mtg_format="modern")
        assert first != second

    def test_rooting_a_deck_with_history_is_refused(self, vcs_repo):
        vcs_repo.commit_deck("d", "4 Lightning Bolt\n", "Initial version")
        with pytest.raises(BaselineRootError, match="already has version history"):
            vcs_repo.seed_baseline_root("d", "2 Consider\n", archetype="A", mtg_format="modern")

    def test_refusal_leaves_the_existing_history_untouched(self, vcs_repo):
        original = vcs_repo.commit_deck("d", "4 Lightning Bolt\n", "Initial version")
        with pytest.raises(BaselineRootError):
            vcs_repo.seed_baseline_root("d", "2 Consider\n", archetype="A", mtg_format="modern")
        assert [c.sha for c in vcs_repo.list_commits("d")] == [original]
        assert vcs_repo.read_commit_text("d", original) == "4 Lightning Bolt\n"

    def test_empty_baseline_is_refused(self, vcs_repo):
        with pytest.raises(BaselineRootError, match="empty baseline"):
            vcs_repo.seed_baseline_root("d", "   \n", archetype="A", mtg_format="modern")

    def test_root_commit_sha_finds_the_parentless_commit(self, vcs_repo):
        root = vcs_repo.seed_baseline_root(
            "d", "4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        vcs_repo.commit_deck("d", "4 Lightning Bolt\n2 Consider\n", "add Consider")
        vcs_repo.commit_deck("d", "4 Lightning Bolt\n4 Consider\n", "more Consider")
        assert vcs_repo.root_commit_sha("d") == root

    def test_is_baseline_root_distinguishes_a_seeded_root_from_a_save(self, vcs_repo):
        seeded = vcs_repo.seed_baseline_root(
            "a", "4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        saved = vcs_repo.commit_deck("b", "4 Lightning Bolt\n", "Initial version")
        assert vcs_repo.is_baseline_root("a", seeded) is True
        assert vcs_repo.is_baseline_root("b", saved) is False

    def test_saves_land_on_top_of_the_baseline_root(self, vcs_repo):
        root = vcs_repo.seed_baseline_root(
            "d", "4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        child = vcs_repo.commit_deck("d", "4 Lightning Bolt\n2 Consider\n", "add Consider")
        commits = {c.sha: c for c in vcs_repo.list_commits("d")}
        assert commits[child].parents == (root,)

    def test_diff_against_the_root_is_an_ordinary_ancestor_diff(self, vcs_repo):
        root = vcs_repo.seed_baseline_root(
            "d", "4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        tip = vcs_repo.commit_deck("d", "4 Lightning Bolt\n2 Consider\n", "add Consider")
        diff = vcs_repo.diff_commits("d", root, tip)
        assert [c.name for c in diff.added] == ["Consider"]

    def test_message_names_the_archetype_and_format(self):
        assert baseline_message("Izzet Murktide", "modern") == (
            "Archetype baseline: Izzet Murktide (modern)"
        )

    def test_root_carries_the_pinned_epoch(self, vcs_repo):
        sha = vcs_repo.seed_baseline_root(
            "d", "4 Lightning Bolt\n", archetype="A", mtg_format="modern"
        )
        commit = next(c for c in vcs_repo.list_commits("d") if c.sha == sha)
        assert commit.timestamp == BASELINE_EPOCH


# ------------------------------------------------------------------ store ------------------------------------------------------------------
class TestBaselineStore:
    def test_round_trips_a_baseline(self, tmp_path, pool):
        store = BaselineStore(tmp_path / "baselines.json")
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        store.save(baseline)

        loaded = store.get("Izzet Murktide", "modern")
        assert loaded is not None
        assert loaded.pool_size == baseline.pool_size
        assert loaded.decklist() == baseline.decklist()
        assert loaded.main.flex == baseline.main.flex
        assert [c.name for c in loaded.flex_candidates] == [
            c.name for c in baseline.flex_candidates
        ]

    def test_lookup_is_case_insensitive(self, tmp_path, pool):
        store = BaselineStore(tmp_path / "baselines.json")
        store.save(build_baseline(pool, archetype="Izzet Murktide", mtg_format="Modern"))
        assert store.get("izzet murktide", "modern") is not None

    def test_missing_entry_is_none(self, tmp_path):
        assert BaselineStore(tmp_path / "baselines.json").get("Nothing", "modern") is None

    def test_recomputing_overwrites_the_entry(self, tmp_path, pool):
        store = BaselineStore(tmp_path / "baselines.json")
        store.save(build_baseline(pool, archetype="A", mtg_format="modern"))
        store.save(build_baseline(pool, archetype="A", mtg_format="modern"))
        assert store.get("A", "modern").pool_size == len(pool)
        assert store.keys() == ["modern::a"]


class TestBaselineStoreSchemaVersion:
    """What happens when the file on disk is not the shape this build writes.

    The stakes are higher than a cache's: a deck's root commit is seeded from
    this store, so quietly deciding there is no stored baseline changes the root
    sha of every deck created afterwards.

    The field names and the version number are spelled out here rather than
    imported from the store. This is a test of the *on-disk* format, and one
    that reads the format out of the code under test cannot notice the code
    changing it.
    """

    #: Mirrors ``store.SCHEMA_VERSION``; deliberately duplicated, see above.
    VERSION = 1

    @pytest.fixture
    def warnings(self):
        """Capture loguru WARNING messages (loguru does not feed pytest's caplog)."""
        from loguru import logger

        messages: list[str] = []
        sink_id = logger.add(lambda msg: messages.append(str(msg)), level="WARNING")
        try:
            yield messages
        finally:
            logger.remove(sink_id)

    def test_the_stored_file_says_which_schema_it_is(self, tmp_path, pool):
        path = tmp_path / "baselines.json"
        BaselineStore(path).save(build_baseline(pool, archetype="A", mtg_format="modern"))

        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["version"] == self.VERSION
        assert list(document["baselines"]) == ["modern::a"]

    def test_a_schema_this_build_cannot_read_is_ignored_out_loud(self, tmp_path, pool, warnings):
        """Not silently: the log has to name the file and both versions."""
        path = tmp_path / "baselines.json"
        store = BaselineStore(path)
        store.save(build_baseline(pool, archetype="A", mtg_format="modern"))

        document = json.loads(path.read_text(encoding="utf-8"))
        document["version"] = self.VERSION + 99
        path.write_text(json.dumps(document), encoding="utf-8")

        assert store.get("A", "modern") is None
        assert store.keys() == []
        assert warnings, "a discarded store must be logged, not dropped in silence"
        assert str(self.VERSION + 99) in warnings[-1]
        assert "baselines.json" in warnings[-1]

    def test_saving_over_an_unreadable_file_makes_it_readable_again(self, tmp_path, pool):
        """The recovery path: a user who moved back to an older build is not stuck."""
        path = tmp_path / "baselines.json"
        store = BaselineStore(path)
        path.write_text(json.dumps({"version": self.VERSION + 99}), encoding="utf-8")

        store.save(build_baseline(pool, archetype="A", mtg_format="modern"))
        assert store.get("A", "modern") is not None

    def test_a_file_written_before_versioning_is_still_read(self, tmp_path, pool):
        """The pre-version layout was the bare mapping, and its shape is unchanged."""
        path = tmp_path / "baselines.json"
        entry = baseline_to_dict(build_baseline(pool, archetype="A", mtg_format="modern"))
        path.write_text(json.dumps({"modern::a": entry}), encoding="utf-8")

        store = BaselineStore(path)
        assert store.get("A", "modern") is not None
        assert store.keys() == ["modern::a"]


# ------------------------------------------------------------------ service ------------------------------------------------------------------
class _FakeMetagameRepo:
    def __init__(self, numbers: list[str]) -> None:
        self.numbers = numbers
        #: Every ``source_filter`` it was asked for, in order. The real
        #: repository does the filtering; the service's job is to pass it on.
        self.source_filters: list[str | None] = []

    def get_decks_for_archetype(self, archetype, source_filter=None):
        self.source_filters.append(source_filter)
        return [{"number": number} for number in self.numbers]


class TestBaselineService:
    @pytest.fixture(autouse=True)
    def _small_pools_allowed(self, monkeypatch):
        """Let the five-deck fixture through the minimum-pool guard.

        These tests are about the service's plumbing (storing, sourcing, root
        seeding), not about whether five lists are enough evidence -- that
        judgement is :data:`MIN_POOL_SIZE`'s own, and it has its own test.
        """
        monkeypatch.setattr(service_module, "MIN_POOL_SIZE", 2)

    def _service(self, tmp_path, pool, numbers=None):
        numbers = numbers or [f"deck-{i}" for i in range(len(pool))]
        texts = dict(zip(numbers, pool, strict=False))
        return ArchetypeBaselineService(
            metagame_repo=_FakeMetagameRepo(numbers),
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
            text_provider=lambda wanted: {n: texts[n] for n in wanted if n in texts},
        )

    def test_compute_stores_the_baseline(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        baseline = service.compute({"name": "Izzet Murktide"}, mtg_format="modern")
        assert baseline is not None
        assert baseline.pool_size == 5
        assert service.stored("Izzet Murktide", "modern") is not None

    def test_compute_records_its_sources(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        baseline = service.compute({"name": "A"}, mtg_format="modern")
        assert len(baseline.sources) == 5

    def test_pool_below_the_floor_returns_none(self, tmp_path, pool, monkeypatch):
        # Opts back out of the autouse relaxation above: this one is about the
        # guard itself, so it needs a floor the fixture pool cannot clear.
        monkeypatch.setattr(service_module, "MIN_POOL_SIZE", len(pool) + 1)
        service = self._service(tmp_path, pool)
        assert service.compute({"name": "A"}, mtg_format="modern") is None

    def test_missing_decklists_are_skipped_not_counted(self, tmp_path, pool):
        numbers = [f"deck-{i}" for i in range(len(pool))]
        texts = {numbers[0]: pool[0], numbers[1]: pool[1]}
        service = ArchetypeBaselineService(
            metagame_repo=_FakeMetagameRepo(numbers),
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
            text_provider=lambda wanted: {n: texts[n] for n in wanted if n in texts},
        )
        texts_found, numbers_found = service.pool_texts({"name": "A"})
        assert len(texts_found) == 2
        assert numbers_found == numbers[:2]

    def test_seed_root_uses_the_stored_baseline(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        service.compute({"name": "Izzet Murktide"}, mtg_format="modern")

        sha = service.seed_root_for_new_deck(
            "my-deck", archetype="Izzet Murktide", mtg_format="modern"
        )
        assert sha is not None
        assert service.has_baseline_root("my-deck")
        stored = service.stored("Izzet Murktide", "modern")
        assert service.vcs_repo.read_commit_text("my-deck", sha) == stored.decklist()

    def test_seed_root_without_a_stored_baseline_does_nothing(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        assert service.seed_root_for_new_deck("d", archetype="Unknown", mtg_format="modern") is None

    def test_seed_root_is_skipped_for_a_deck_that_already_has_history(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        service.compute({"name": "A"}, mtg_format="modern")
        service.vcs_repo.commit_deck("d", "4 Lightning Bolt\n", "Initial version")

        # Never re-root: the player's commits stay where they are.
        assert service.seed_root_for_new_deck("d", archetype="A", mtg_format="modern") is None
        assert len(service.vcs_repo.list_commits("d")) == 1

    def test_two_decks_of_one_archetype_share_a_root(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        service.compute({"name": "A"}, mtg_format="modern")
        first = service.seed_root_for_new_deck("deck-1", archetype="A", mtg_format="modern")
        second = service.seed_root_for_new_deck("deck-2", archetype="A", mtg_format="modern")
        assert first == second

    def test_missing_archetype_or_format_is_a_no_op(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        assert service.seed_root_for_new_deck("d", archetype=None, mtg_format="modern") is None
        assert service.seed_root_for_new_deck("d", archetype="A", mtg_format=None) is None

    def test_root_sha_reports_none_without_history(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        assert service.root_sha("nothing") is None
        assert service.has_baseline_root("nothing") is False

    def test_the_source_filter_is_handed_to_the_metagame_repository(self, tmp_path, pool):
        """Which site's decks to draw from is the repository's decision to make.

        The service's only job is not to swallow the argument -- and it had no
        test, so passing ``None`` unconditionally would have gone unnoticed.
        """
        repo = _FakeMetagameRepo([f"deck-{i}" for i in range(len(pool))])
        texts = dict(zip(repo.numbers, pool, strict=False))
        service = ArchetypeBaselineService(
            metagame_repo=repo,
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
            text_provider=lambda wanted: {n: texts[n] for n in wanted if n in texts},
        )
        service.pool_texts({"name": "A"})
        service.pool_texts({"name": "A"}, source_filter="mtggoldfish")
        service.compute({"name": "A"}, mtg_format="modern", source_filter="melee")
        assert repo.source_filters == [None, "mtggoldfish", "melee"]

    def test_limit_caps_the_pool_before_any_decklist_is_fetched(self, tmp_path, pool):
        """The limit is a cap on work, so it has to apply before the lookup.

        Asking the cache for fifty lists and then throwing forty-seven away
        would read the same and cost the round trips this exists to avoid.
        """
        numbers = [f"deck-{i}" for i in range(len(pool))]
        texts = dict(zip(numbers, pool, strict=False))
        asked: list[list[str]] = []

        def provider(wanted):
            asked.append(list(wanted))
            return {n: texts[n] for n in wanted if n in texts}

        service = ArchetypeBaselineService(
            metagame_repo=_FakeMetagameRepo(numbers),
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
            text_provider=provider,
        )
        found_texts, found_numbers = service.pool_texts({"name": "A"}, limit=3)
        assert asked == [numbers[:3]]
        assert found_numbers == numbers[:3]
        assert len(found_texts) == 3

    def test_no_limit_asks_for_everything(self, tmp_path, pool):
        service = self._service(tmp_path, pool)
        _texts, numbers = service.pool_texts({"name": "A"}, limit=None)
        assert len(numbers) == len(pool)


class TestTheProductionPoolPath:
    """``pool_texts`` through the real deck-text cache, with no ``text_provider``.

    Every other service test injects the seam, so ``self.deck_cache.get_many``
    -- the branch the app runs, and the only one that can be wrong about the
    cache's shape -- had never been executed by a test. A real
    :class:`DeckTextCache` on ``tmp_path`` costs one sqlite file.
    """

    def _service(self, tmp_path, cache):
        numbers = [f"deck-{i}" for i in range(5)]
        return numbers, ArchetypeBaselineService(
            metagame_repo=_FakeMetagameRepo(numbers),
            deck_cache=cache,
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
        )

    def test_the_pool_is_read_out_of_the_cache(self, tmp_path, pool):
        cache = DeckTextCache(tmp_path / "deck_cache.db")
        numbers, service = self._service(tmp_path, cache)
        for number, text in zip(numbers, pool, strict=True):
            cache.set(number, text)

        texts, found = service.pool_texts({"name": "Izzet Murktide"})
        assert found == numbers
        assert texts == pool
        assert service._text_provider is None  # the seam really is not in play

    def test_a_deck_the_cache_has_never_seen_is_skipped(self, tmp_path, pool):
        # The research panel is what fills the cache; a baseline summarises what
        # has been collected rather than downloading the rest inline.
        cache = DeckTextCache(tmp_path / "deck_cache.db")
        numbers, service = self._service(tmp_path, cache)
        for number, text in zip(numbers[:2], pool[:2], strict=True):
            cache.set(number, text)

        texts, found = service.pool_texts({"name": "A"})
        assert found == numbers[:2]
        assert len(texts) == 2

    def test_an_empty_cache_yields_an_empty_pool(self, tmp_path):
        cache = DeckTextCache(tmp_path / "deck_cache.db")
        _numbers, service = self._service(tmp_path, cache)
        assert service.pool_texts({"name": "A"}) == ([], [])

    def test_a_baseline_computes_end_to_end_off_the_cache(self, tmp_path, pool, monkeypatch):
        monkeypatch.setattr(service_module, "MIN_POOL_SIZE", 2)
        cache = DeckTextCache(tmp_path / "deck_cache.db")
        numbers, service = self._service(tmp_path, cache)
        for number, text in zip(numbers, pool, strict=True):
            cache.set(number, text)

        baseline = service.compute({"name": "Izzet Murktide"}, mtg_format="modern")
        assert baseline is not None
        assert baseline.pool_size == 5
        assert baseline.sources == tuple(numbers)
        assert "4 Lightning Bolt" in baseline.decklist()


class TestTheMinimumPoolSize:
    """:data:`MIN_POOL_SIZE` itself -- the test 12 others assumed existed.

    They monkeypatch it to 2 so a five-deck fixture can exercise the plumbing,
    and none of them asserted anything about the real number. A strict
    intersection fails towards *larger* baselines on small pools, so the floor
    is the only thing standing between "one player's deck" and "the archetype".
    """

    def _service(self, tmp_path, texts):
        numbers = [f"deck-{i}" for i in range(len(texts))]
        by_number = dict(zip(numbers, texts, strict=True))
        return ArchetypeBaselineService(
            metagame_repo=_FakeMetagameRepo(numbers),
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
            text_provider=lambda wanted: {n: by_number[n] for n in wanted if n in by_number},
        )

    def test_the_floor_is_the_documented_eight(self):
        assert service_module.MIN_POOL_SIZE == 8

    def test_seven_lists_are_not_enough(self, tmp_path):
        pool = [affinity_like(f"Card {i}") for i in range(7)]
        service = self._service(tmp_path, pool)
        assert service.compute({"name": "Affinity"}, mtg_format="modern") is None
        assert service.stored("Affinity", "modern") is None

    def test_eight_of_the_same_lists_are(self, tmp_path):
        pool = [affinity_like(f"Card {i}") for i in range(8)]
        service = self._service(tmp_path, pool)
        baseline = service.compute({"name": "Affinity"}, mtg_format="modern")
        assert baseline is not None
        assert baseline.pool_size == 8
        assert service.stored("Affinity", "modern") is not None

    def test_the_floor_applies_to_the_survivors_not_the_label(self, tmp_path):
        """Eight lists offered, one an impostor: seven survive and that is short.

        The guard runs twice on purpose -- once on what the label produced and
        once on what membership kept -- so a pool that is mostly other
        archetypes cannot clear it on size and then answer from the remainder.
        """
        pool = [affinity_like(f"Card {i}") for i in range(7)] + [alien_deck()]
        service = self._service(tmp_path, pool)
        assert len(pool) >= service_module.MIN_POOL_SIZE
        assert service.compute({"name": "Affinity"}, mtg_format="modern") is None


# ------------------------------------------------------------------ membership ------------------------------------------------------------------
def affinity_like(extra: str = "", *, saga: int = 4) -> str:
    """A list from one archetype: a shared core plus an optional private card."""
    lines = [
        f"{saga} Urza's Saga",
        "4 Mox Opal",
        "4 Mishra's Bauble",
        "4 Kappa Cannoneer",
        "4 Thought Monitor",
        "16 Darksteel Citadel",
    ]
    if extra:
        lines.append(f"1 {extra}")
    return "\n".join(lines) + "\n\nSideboard\n4 Consign to Memory\n"


def alien_deck() -> str:
    """A deck sharing nothing with :func:`affinity_like` -- a different archetype."""
    return (
        "4 Tarmogoyf\n4 Thoughtseize\n4 Fatal Push\n"
        "4 Verdant Catacombs\n20 Swamp\n\nSideboard\n4 Duress\n"
    )


# --- the partly-overlapping pool, built so its scores can be worked out by hand ---
#
# ``affinity_like`` and ``alien_deck`` share *zero* maindeck names, so every
# score they produce is 0.0 or >= 0.667 and any threshold in (0.182, 0.667]
# splits them identically -- including 0.20 and 0.65, both of which would
# misclassify the real pool membership.py's docstring describes. The pool below
# has the partial overlap the real one has, and its two bands are 4/17 and
# 58/119, so the shipped 0.30 is the only kind of value that splits it.

#: The eight names every member of :func:`shell_sharing_member` runs.
SHARED_CORE = (
    "Urza's Saga",
    "Mox Opal",
    "Springleaf Drum",
    "Metallic Rebuke",
    "Mishra's Bauble",
    "Thought Monitor",
    "Kappa Cannoneer",
    "Darksteel Citadel",
)

#: The four of them the impostor also runs -- the artifact-mana shell that
#: membership.py's docstring names as the whole of what Affinity and Hammer
#: Time have in common.
SHARED_SHELL = SHARED_CORE[:4]

#: Three names of its own per member, all twelve distinct, so a member's list is
#: eight core + three private = eleven names.
MEMBER_PRIVATE_CARDS = (
    ("Nettlecyst", "Patchwork Automaton", "Seat of the Synod"),
    ("Emry, Lurker of the Loch", "Vault of Whispers", "Thoughtcast"),
    ("Master of Etherium", "Tree of Tales", "Galvanic Blast"),
    ("Cranial Plating", "Ancient Den", "Frogmite"),
)


def shell_sharing_member(index: int) -> str:
    """Member ``index`` of the partly-overlapping pool: the core plus its own three."""
    lines = [f"4 {name}" for name in SHARED_CORE]
    lines += [f"2 {name}" for name in MEMBER_PRIVATE_CARDS[index]]
    return "\n".join(lines) + "\n\nSideboard\n4 Consign to Memory\n"


def shell_sharing_impostor() -> str:
    """A different archetype that runs the same artifact-mana shell and nothing else.

    Four of the core's eight names plus six of its own -- ten names in all.
    """
    lines = [f"4 {name}" for name in SHARED_SHELL]
    lines += [
        "4 Colossus Hammer",
        "4 Sigarda's Aid",
        "4 Puresteel Paladin",
        "4 Stoneforge Mystic",
        "4 Giver of Runes",
        "4 Inkmoth Nexus",
    ]
    return "\n".join(lines) + "\n\nSideboard\n4 Path to Exile\n"


@pytest.fixture
def partly_overlapping_pool() -> list[str]:
    """Four members and one impostor that shares half their mana base.

    Worked out from the definitions above, using |A n B| / |A u B| on maindeck
    names only:

    - member vs. member: 8 shared, 8 + 3 + 3 = 14 in either -> **8/14 = 4/7**
    - member vs. impostor: 4 shared, 11 + 10 - 4 = 17 in either -> **4/17**

    Each deck's score is the mean over the other four:

    - a member: (3 * 4/7 + 4/17) / 4 = (12/7 + 4/17) / 4 = (232/119) / 4
      = **58/119 = 0.4874**
    - the impostor: (4 * 4/17) / 4 = **4/17 = 0.2353**

    Both land in the bands membership.py's docstring measured on the real
    60-deck pool -- kept 0.462-0.638, rejected 0.093-0.266 -- which is what
    makes this pool able to tell a wrong threshold from the shipped one.
    """
    return [shell_sharing_member(i) for i in range(4)] + [shell_sharing_impostor()]


#: The two hand-computed scores the fixture above produces.
MEMBER_SCORE = 58 / 119
IMPOSTOR_SCORE = 4 / 17


class TestPoolMembership:
    def test_jaccard_is_shared_over_either(self):
        left = frozenset({"a", "b", "c", "d", "e"})
        right = frozenset({"a", "b", "c", "d", "e", "f", "g"})
        # 5 shared, 7 in either.
        assert jaccard(left, right) == pytest.approx(5 / 7)

    def test_jaccard_of_a_hand_checked_pair(self):
        # The shape of the real Affinity-vs-Hammer pair: 5 shared of 37 names.
        shared = {f"shared{i}" for i in range(5)}
        left = frozenset(shared | {f"l{i}" for i in range(15)})
        right = frozenset(shared | {f"r{i}" for i in range(17)})
        assert jaccard(left, right) == pytest.approx(5 / 37)
        assert jaccard(left, right) == pytest.approx(0.135, abs=0.001)

    def test_jaccard_is_symmetric(self):
        left, right = frozenset({"a", "b"}), frozenset({"b", "c", "d"})
        assert jaccard(left, right) == jaccard(right, left)

    def test_identical_lists_score_one(self):
        names = frozenset({"a", "b", "c"})
        assert jaccard(names, names) == 1.0

    def test_counts_are_ignored(self):
        # Same cards, different ratios -> the same deck, as far as membership goes.
        assert maindeck_names(affinity_like(saga=4)) == maindeck_names(affinity_like(saga=1))

    def test_sideboard_is_not_part_of_the_comparison(self):
        names = maindeck_names(affinity_like())
        assert "Consign to Memory" not in names
        assert "Mox Opal" in names

    def test_a_zero_count_card_is_not_a_card_the_deck_runs(self):
        assert "Consider" not in maindeck_names("4 Lightning Bolt\n0 Consider\n")

    def test_the_alien_deck_is_excluded(self):
        pool = [affinity_like(f"Card {i}") for i in range(9)] + [alien_deck()]
        result = partition_pool(pool)
        assert result.excluded_count == 1
        assert result.kept_count == 9
        # It is the impostor that went, not an arbitrary victim.
        assert 9 not in result.kept_indices

    def test_a_variant_build_is_kept(self):
        # Shares the core, differs in one slot: a build, not another archetype.
        pool = [affinity_like(f"Card {i}") for i in range(9)]
        assert partition_pool(pool).excluded_count == 0

    def test_excluded_decks_are_named_by_their_source(self):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        sources = ("a", "b", "c", "d", "e", "the-impostor")
        result = partition_pool(pool, sources=sources)
        assert [deck.source for deck in result.excluded] == ["the-impostor"]

    def test_excluded_decks_fall_back_to_an_index_without_sources(self):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        assert [deck.source for deck in partition_pool(pool).excluded] == ["#5"]

    def test_a_blank_source_falls_back_to_an_index_too(self):
        """A deck record with no number is identified by position, not by "".

        ``pool_texts`` drops numberless decks, but ``partition_pool`` is
        exported and takes whatever tuple it is handed; an exclusion the user
        cannot name is one they cannot check.
        """
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        sources = ("a", "b", "c", "d", "e", "")
        assert [deck.source for deck in partition_pool(pool, sources=sources).excluded] == ["#5"]

    def test_sources_shorter_than_the_pool_fall_back_for_the_rest(self):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        assert [deck.source for deck in partition_pool(pool, sources=("a",)).excluded] == ["#5"]


class TestTheSmallestScorablePool:
    """``MIN_POOL_FOR_FILTERING``: below two decks there are no pairs.

    The constant had no test. It is the line between "invent a score" and
    "measure one", and moving it up would silently keep every two-deck pool.
    """

    def test_the_constant_is_two_because_that_is_where_pairs_start(self):
        assert MIN_POOL_FOR_FILTERING == 2

    def test_nothing_scores_nothing(self):
        assert similarity_scores([]) == []

    def test_a_lone_deck_is_perfectly_typical_of_itself(self):
        assert similarity_scores([frozenset({"a", "b"})]) == [1.0]

    def test_two_decks_are_measured_rather_than_assumed(self):
        # One pair: {a,b} and {b,c} share one name of three -> 1/3 each. The
        # invented 1.0 above must not leak into the smallest real pool.
        left, right = frozenset({"a", "b"}), frozenset({"b", "c"})
        assert similarity_scores([left, right]) == pytest.approx([1 / 3, 1 / 3])

    def test_two_strangers_are_both_rejected(self):
        # The end-to-end consequence: at two decks the filter is live, and a
        # pool of two unrelated lists produces no members at all.
        result = partition_pool([affinity_like(), alien_deck()])
        assert result.kept_count == 0
        assert result.scores == (0.0, 0.0)


class TestMembershipProtectsTheBaseline:
    def test_no_single_deck_can_flatten_the_baseline(self):
        """The user's rule: one impostor must not take the baseline to zero."""
        clean = [affinity_like(f"Card {i}") for i in range(9)]
        contaminated = clean + [alien_deck()]

        expected = build_baseline(clean, archetype="Affinity", mtg_format="modern")
        actual = build_baseline(contaminated, archetype="Affinity", mtg_format="modern")

        assert expected.main.fixed > 0
        assert [(c.name, c.fixed_count) for c in actual.cards if c.fixed_count] == [
            (c.name, c.fixed_count) for c in expected.cards if c.fixed_count
        ]
        assert actual.main.fixed == expected.main.fixed

    def test_without_the_guard_one_deck_would_have_flattened_it(self):
        # The failure the filter exists to prevent, pinned so the premise cannot
        # quietly stop being true.
        contaminated = [affinity_like(f"Card {i}") for i in range(9)] + [alien_deck()]
        unguarded = build_baseline(
            contaminated, archetype="Affinity", mtg_format="modern", membership_threshold=0.0
        )
        assert unguarded.main.fixed == 0

    def test_every_position_for_the_impostor_is_survivable(self):
        clean = [affinity_like(f"Card {i}") for i in range(9)]
        for position in range(len(clean) + 1):
            pool = clean[:position] + [alien_deck()] + clean[position:]
            baseline = build_baseline(pool, archetype="A", mtg_format="modern")
            assert baseline.main.fixed > 0, f"flattened with the impostor at {position}"

    def test_kept_sources_name_only_the_survivors(self):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        sources = ("a", "b", "c", "d", "e", "impostor")
        baseline = build_baseline(pool, archetype="A", mtg_format="modern", sources=sources)
        assert baseline.sources == ("a", "b", "c", "d", "e")
        assert baseline.pool_size == 5


class TestMembershipIsOrderIndependent:
    """The property the measure was chosen for."""

    def _pool(self) -> list[str]:
        return [affinity_like(f"Card {i}") for i in range(8)] + [alien_deck()]

    def test_shuffling_the_pool_rejects_the_same_decks(self):
        pool = self._pool()
        sources = tuple(f"deck-{i}" for i in range(len(pool)))
        expected = set(partition_pool(pool, sources=sources).excluded)

        for seed in range(6):
            order = list(range(len(pool)))
            random.Random(seed).shuffle(order)
            result = partition_pool(
                [pool[i] for i in order], sources=tuple(sources[i] for i in order)
            )
            assert set(result.excluded) == expected, f"differed at seed {seed}"

    def test_shuffling_the_pool_gives_an_identical_baseline(self):
        pool = self._pool()
        expected = build_baseline(pool, archetype="A", mtg_format="modern").decklist()

        for seed in range(6):
            shuffled = list(pool)
            random.Random(seed).shuffle(shuffled)
            actual = build_baseline(shuffled, archetype="A", mtg_format="modern").decklist()
            assert actual == expected, f"differed at seed {seed}"

    def test_scores_do_not_depend_on_position(self):
        pool = self._pool()
        forward = similarity_scores([maindeck_names(text) for text in pool])
        backward = similarity_scores([maindeck_names(text) for text in reversed(pool)])
        assert forward == pytest.approx(list(reversed(backward)))


class TestMembershipThresholdGap:
    def test_the_same_split_across_the_empty_gap(self):
        """The shipped threshold is not a knife edge: the gap is wide."""
        pool = [affinity_like(f"Card {i}") for i in range(9)] + [alien_deck()]
        splits = {
            partition_pool(pool, threshold=t).kept_indices for t in (0.27, 0.30, 0.35, 0.40, 0.45)
        }
        assert len(splits) == 1

    def test_a_threshold_of_zero_keeps_everything(self):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        assert partition_pool(pool, threshold=0.0).excluded_count == 0

    def test_the_shipped_threshold_sits_between_the_two_groups(self):
        pool = [affinity_like(f"Card {i}") for i in range(9)] + [alien_deck()]
        result = partition_pool(pool)
        kept = [result.scores[i] for i in result.kept_indices]
        dropped = [deck.similarity for deck in result.excluded]
        assert max(dropped) < MEMBERSHIP_THRESHOLD <= min(kept)


class TestScoresAreHandComputable:
    """``similarity_scores`` against arithmetic done on paper, not against itself.

    Every other test in this file reads a *split* rather than a number, and a
    split survives a measure that is wrong by a constant factor -- or that
    returns all zeros, which reversal symmetry cannot tell from a real answer.
    These name the numbers.
    """

    def test_three_sets_worked_out_by_hand(self):
        # A = {a,b,c,d}  B = {a,b,e,f}  C = {a,g,h,i}
        #   J(A,B) = 2 shared / 6 in either = 1/3
        #   J(A,C) = 1 shared / 7 in either = 1/7
        #   J(B,C) = 1 shared / 7 in either = 1/7
        # Each score is the mean over the *other* two:
        #   A: (1/3 + 1/7) / 2 = (10/21) / 2 = 5/21
        #   B: (1/3 + 1/7) / 2 = 5/21
        #   C: (1/7 + 1/7) / 2 = 1/7
        first = frozenset({"a", "b", "c", "d"})
        second = frozenset({"a", "b", "e", "f"})
        third = frozenset({"a", "g", "h", "i"})
        assert similarity_scores([first, second, third]) == pytest.approx([5 / 21, 5 / 21, 1 / 7])

    def test_a_deck_shares_the_credit_for_every_pair_it_is_in(self):
        # Two identical lists and one stranger: the identical pair scores 1.0,
        # both strangers' pairs score 0.0.
        #   identical deck: (1.0 + 0.0) / 2 = 0.5
        #   the stranger:   (0.0 + 0.0) / 2 = 0.0
        twin = frozenset({"a", "b"})
        stranger = frozenset({"y", "z"})
        assert similarity_scores([twin, twin, stranger]) == pytest.approx([0.5, 0.5, 0.0])

    def test_the_partly_overlapping_pool_scores_as_worked_out(self, partly_overlapping_pool):
        """The fixture's own derivation, read back off ``partition_pool``.

        See :func:`partly_overlapping_pool` for the arithmetic: members sit at
        58/119 and the impostor at 4/17.
        """
        result = partition_pool(partly_overlapping_pool)
        assert result.scores == pytest.approx(
            [MEMBER_SCORE, MEMBER_SCORE, MEMBER_SCORE, MEMBER_SCORE, IMPOSTOR_SCORE]
        )
        assert result.scores[0] == pytest.approx(0.4874, abs=0.0001)
        assert result.scores[4] == pytest.approx(0.2353, abs=0.0001)

    def test_the_pairs_behind_those_scores(self, partly_overlapping_pool):
        """The premise: the pool really is 4/7 within the group and 4/17 across it."""
        names = [maindeck_names(text) for text in partly_overlapping_pool]
        assert [len(deck) for deck in names] == [11, 11, 11, 11, 10]
        assert jaccard(names[0], names[1]) == pytest.approx(8 / 14)
        assert jaccard(names[0], names[4]) == pytest.approx(4 / 17)


class TestTheShippedThresholdIsPinned:
    """0.30 itself, not merely "some number between nothing and everything".

    The alien-deck pools cannot do this: sharing zero names, they score 0.0 or
    >= 0.667, so anything in (0.182, 0.667] splits them the same way. These use
    :func:`partly_overlapping_pool`, whose two bands are 0.2353 and 0.4874, so
    the split moves the moment the constant leaves (0.2353, 0.4874].
    """

    def test_the_shipped_threshold_splits_the_partly_overlapping_pool(
        self, partly_overlapping_pool
    ):
        result = partition_pool(partly_overlapping_pool)
        assert result.kept_indices == (0, 1, 2, 3)
        assert [deck.source for deck in result.excluded] == ["#4"]

    def test_the_constant_lies_between_this_pools_two_bands(self):
        assert IMPOSTOR_SCORE < MEMBERSHIP_THRESHOLD <= MEMBER_SCORE

    def test_the_constant_lies_in_the_gap_the_real_pool_measured(self):
        """membership.py documents kept 0.462-0.638, rejected 0.093-0.266.

        A threshold outside that gap misclassifies the pool the constant was
        chosen on, whatever the fixtures here happen to say.
        """
        assert 0.266 < MEMBERSHIP_THRESHOLD <= 0.462

    def test_a_looser_threshold_keeps_the_impostor(self, partly_overlapping_pool):
        """Why 0.30 may not drift down: at 0.20 the impostor is a member."""
        loose = partition_pool(partly_overlapping_pool, threshold=0.20)
        assert loose.excluded_count == 0
        # ...and it takes most of the baseline with it: the intersection is
        # unforgiving, so the eight shared core cards (4 copies each, 32 slots)
        # collapse to the four the impostor happens to share.
        loosened = build_baseline(
            partly_overlapping_pool,
            archetype="A",
            mtg_format="modern",
            membership_threshold=0.20,
        )
        assert {card.name for card in loosened.cards if card.fixed_count} == set(SHARED_SHELL)
        assert loosened.main.fixed == 16

    def test_a_tighter_threshold_throws_the_whole_archetype_away(self, partly_overlapping_pool):
        """Why 0.30 may not drift up: at 0.65 four honest lists are impostors."""
        tight = partition_pool(partly_overlapping_pool, threshold=0.65)
        assert tight.kept_count == 0
        assert tight.excluded_count == 5

    def test_the_shipped_threshold_keeps_the_members_and_their_core(self, partly_overlapping_pool):
        """The conclusion the two bands exist for: the eight core cards survive."""
        baseline = build_baseline(
            partly_overlapping_pool, archetype="Affinity", mtg_format="modern"
        )
        assert baseline.pool_size == 4
        main_fixed = {
            card.name for card in baseline.cards if card.fixed_count and not card.is_sideboard
        }
        assert main_fixed == set(SHARED_CORE)
        assert baseline.main.fixed == 32  # eight cards, four copies each


class TestMembershipDegeneratePools:
    def test_empty_pool(self):
        result = partition_pool([])
        assert (result.kept_count, result.excluded_count, result.examined) == (0, 0, 0)

    def test_a_single_deck_is_kept(self):
        # It cannot be atypical of a pool it is the whole of.
        result = partition_pool([alien_deck()])
        assert result.kept_indices == (0,)
        assert result.excluded == ()

    def test_all_identical_decks_are_all_kept(self):
        result = partition_pool([affinity_like() for _ in range(6)])
        assert result.excluded_count == 0
        assert set(result.scores) == {1.0}

    def test_a_pool_of_mutual_strangers_keeps_nobody(self):
        pool = [f"4 Card{i}A\n4 Card{i}B\n20 Land{i}\n" for i in range(6)]
        result = partition_pool(pool)
        assert result.kept_count == 0
        assert result.excluded_count == 6

    def test_a_pool_of_blank_texts_keeps_nobody(self):
        assert partition_pool(["", "   ", ""]).kept_count == 0

    def test_the_measure_finds_the_minority_not_the_wrong_label(self):
        """A documented limit, pinned so it cannot surprise anyone later.

        Membership is relative to the pool. Three real lists drowned by nine
        copies of something else makes the *real* lists the outliers, and no
        amount of similarity arithmetic can say which group wears the label
        correctly. This guards against contamination, not against a pool that
        is mostly the wrong archetype.
        """
        pool = [affinity_like() for _ in range(3)] + [alien_deck() for _ in range(9)]
        result = partition_pool(pool)
        assert result.kept_count == 9
        assert result.excluded_count == 3

    def test_a_contaminated_pool_yields_no_baseline_from_the_survivors(self, tmp_path):
        """Fewer members than the floor is 'no answer', not a small answer."""
        # Six related lists, each with its own flavour card, plus six decks that
        # resemble nothing at all -- so the members survive but are too few.
        pool = [affinity_like(f"Card {i}") for i in range(6)] + [
            f"4 Card{i}A\n4 Card{i}B\n20 Land{i}\n" for i in range(6)
        ]
        numbers = [f"deck-{i}" for i in range(len(pool))]
        texts = dict(zip(numbers, pool, strict=False))
        service = ArchetypeBaselineService(
            metagame_repo=_FakeMetagameRepo(numbers),
            vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"),
            store=BaselineStore(tmp_path / "baselines.json"),
            text_provider=lambda wanted: {n: texts[n] for n in wanted if n in texts},
        )
        # The raw pool of 12 clears MIN_POOL_SIZE; only the filtered six do not.
        assert len(pool) >= service_module.MIN_POOL_SIZE
        assert service.compute({"name": "A"}, mtg_format="modern") is None
        assert service.stored("A", "modern") is None


class TestMembershipIsReported:
    def test_the_baseline_carries_what_it_rejected(self):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        sources = ("a", "b", "c", "d", "e", "impostor")
        baseline = build_baseline(pool, archetype="A", mtg_format="modern", sources=sources)
        assert baseline.membership.excluded_count == 1
        assert baseline.membership.excluded[0].source == "impostor"
        assert baseline.membership.examined == 6
        assert baseline.membership.kept_count == 5

    def test_a_clean_pool_reports_no_filtering(self):
        baseline = build_baseline(
            [affinity_like() for _ in range(5)], archetype="A", mtg_format="modern"
        )
        assert baseline.membership.filtered_anything is False

    def test_membership_survives_the_store_round_trip(self, tmp_path):
        pool = [affinity_like() for _ in range(5)] + [alien_deck()]
        sources = ("a", "b", "c", "d", "e", "impostor")
        baseline = build_baseline(pool, archetype="A", mtg_format="modern", sources=sources)
        store = BaselineStore(tmp_path / "baselines.json")
        store.save(baseline)

        read_back = store.get("A", "modern")
        assert read_back is not None
        assert read_back.membership.excluded_count == 1
        assert read_back.membership.excluded[0].source == "impostor"
        assert read_back.membership.threshold == baseline.membership.threshold
        assert read_back.membership.kept_indices == baseline.membership.kept_indices

    def test_a_stored_baseline_without_membership_still_reads(self):
        # Entries written before the filter existed must not break on load.
        baseline = build_baseline(
            [affinity_like() for _ in range(3)], archetype="A", mtg_format="modern"
        )
        data = baseline_to_dict(baseline)
        del data["membership"]
        assert baseline_from_dict(data).membership.examined == 0
