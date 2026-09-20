"""Archetype baseline: frequency table, classification, and the root commit.

The pools here are written by hand so every expected classification can be read
straight off the deck definitions -- a card in every list at one count is a
staple, a card in every list at a moving count is a partial staple, and anything
below the cut-off is flex. That makes a failure point at the classifier rather
than at a fixture nobody can check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from repositories.deck_vcs_repository.baseline import (
    BASELINE_EPOCH,
    BaselineRootError,
    baseline_message,
)
from repositories.deck_vcs_repository.repository import DeckVcsRepository
from services.archetype_baseline_service import (
    ArchetypeBaselineService,
    BaselineStore,
    CardRole,
    build_baseline,
    build_frequency_table,
    classify_card,
    deck_card_counts,
    pool_zone_sizes,
)
from services.archetype_baseline_service.classify import DEFAULT_STAPLE_THRESHOLD
from services.archetype_baseline_service.service import MIN_POOL_SIZE


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

    def test_below_threshold_is_flex_and_fixes_nothing(self, pool):
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

    def test_threshold_is_tunable_and_changes_the_verdict(self, pool):
        # Murktide is in 60% of the pool: flex at the default, a staple-family
        # card once the cut-off drops below it.
        strict = build_baseline(pool, archetype="A", mtg_format="modern", threshold=0.9)
        loose = build_baseline(pool, archetype="A", mtg_format="modern", threshold=0.5)
        assert next(c for c in strict.cards if c.name == "Murktide Regent").role is CardRole.FLEX
        assert (
            next(c for c in loose.cards if c.name == "Murktide Regent").role
            is CardRole.PARTIAL_STAPLE
        )

    def test_threshold_of_one_demands_literally_every_deck(self):
        # Nine decks run it, one does not: a staple at 0.9, nothing at 1.0.
        decks = [make_deck(bolt=4, consider=4) for _ in range(9)]
        decks.append(make_deck(bolt=4, consider=0))
        strict = build_baseline(decks, archetype="A", mtg_format="modern", threshold=1.0)
        loose = build_baseline(decks, archetype="A", mtg_format="modern", threshold=0.9)
        assert next(c for c in strict.cards if c.name == "Consider").role is CardRole.FLEX
        assert next(c for c in loose.cards if c.name == "Consider").role is CardRole.STAPLE

    def test_classify_card_is_directly_callable(self):
        table = build_frequency_table([make_deck(bolt=4, consider=4)] * 3)
        role, fixed = classify_card(table[("Lightning Bolt", False)], threshold=1.0)
        assert (role, fixed) == (CardRole.STAPLE, 4)

    def test_default_threshold_tolerates_one_rogue_list(self):
        # Ten decks, one of which drops the card: still a staple by default.
        decks = [make_deck(bolt=4, consider=4) for _ in range(9)]
        decks.append(make_deck(bolt=4, consider=0))
        baseline = build_baseline(
            decks, archetype="A", mtg_format="modern", threshold=DEFAULT_STAPLE_THRESHOLD
        )
        assert next(c for c in baseline.cards if c.name == "Consider").role is CardRole.STAPLE


# ------------------------------------------------------------------ flex arithmetic ------------------------------------------------------------------
class TestFlexSlots:
    def test_fixed_and_flex_slots_add_up_to_the_zone(self, pool):
        baseline = build_baseline(pool, archetype="Izzet Murktide", mtg_format="modern")
        # Main median is 32; fixed is Bolt 4 + Consider floor 3 + Island floor 20.
        assert baseline.main.fixed == 27
        assert baseline.main.size == 32
        assert baseline.main.flex == 5
        assert baseline.sideboard.fixed == 3
        assert baseline.flex_slots == baseline.main.flex + baseline.sideboard.flex

    def test_flex_is_never_negative(self):
        # A pool whose fixed slots exceed the median zone size must clamp
        # rather than report a negative number of free slots.
        decks = ["40 Island\n", "40 Island\n", "20 Island\n", "20 Island\n"]
        baseline = build_baseline(decks, archetype="A", mtg_format="modern", threshold=0.9)
        assert baseline.main.fixed == 20
        assert baseline.main.flex >= 0

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
        assert loaded.threshold == baseline.threshold
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
        store.save(build_baseline(pool, archetype="A", mtg_format="modern", threshold=0.9))
        store.save(build_baseline(pool, archetype="A", mtg_format="modern", threshold=0.5))
        assert store.get("A", "modern").threshold == 0.5
        assert store.keys() == ["modern::a"]


# ------------------------------------------------------------------ service ------------------------------------------------------------------
class _FakeMetagameRepo:
    def __init__(self, numbers: list[str]) -> None:
        self.numbers = numbers

    def get_decks_for_archetype(self, archetype, source_filter=None):
        return [{"number": number} for number in self.numbers]


class TestBaselineService:
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

    def test_pool_below_the_floor_returns_none(self, tmp_path, pool):
        service = self._service(tmp_path, pool[: MIN_POOL_SIZE - 1])
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
