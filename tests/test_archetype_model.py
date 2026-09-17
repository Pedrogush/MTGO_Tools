"""The game-log archetype classifier and the service that builds it at startup.

The model is fitted on small fixture decklists (``archetype_model_fixtures``),
never the real cache: what is under test is the behaviour on *partial* samples
-- a handful of names, no quantities -- plus the three decisions the owner asked
for explicitly: an "Unknown" below the confidence bar, candidates scoped to the
detected format, and a startup build that runs off the UI thread.
"""

from __future__ import annotations

import json
import random
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from archetype_model_fixtures import deck_text, fixture_decks, sample_seen_cards

from repositories.deck_text_cache import DeckTextCache
from services.archetype_model_service import (
    ArchetypeModelService,
    get_archetype_model_service,
    parse_deck_text,
    reset_archetype_model_service,
)
from services.gamelog_service.archetypes import (
    UNKNOWN_ARCHETYPE,
    ArchetypeModel,
    LabelledDeck,
    detect_archetype,
    is_color_bucket,
)


@pytest.fixture(scope="module")
def model() -> ArchetypeModel:
    return ArchetypeModel.build(fixture_decks())


def _cluster_of(model: ArchetypeModel, mtg_format: str, name: str):
    return next(c for c in model.clusters(mtg_format) if c.name == name)


# ---------------------------------------------------------------------------
# Building the profiles
# ---------------------------------------------------------------------------


class TestBuild:
    def test_one_scope_per_format(self, model):
        assert model.formats == ("modern", "pauper")

    def test_colour_bins_are_not_archetypes(self, model):
        assert is_color_bucket("UR") and is_color_bucket("WUBRG")
        assert not is_color_bucket("Burn") and not is_color_bucket("Ur-Dragon")
        names = {label for c in model.clusters("modern") for label in c.labels}
        assert "UR" not in names

    def test_duplicate_labels_are_merged_under_the_better_represented_name(self, model):
        living_end = _cluster_of(model, "modern", "Living End")
        assert living_end.labels == ("Living End", "Living End Cascade")
        assert living_end.deck_count == 6

    def test_distinct_archetypes_that_share_lands_stay_apart(self, model):
        # Tron and Eldrazi Tron share all three Urza lands; they are still two decks.
        names = {c.name for c in model.clusters("modern")}
        assert {"Tron", "Eldrazi Tron"} <= names

    def test_merging_can_be_disabled(self):
        unmerged = ArchetypeModel.build(fixture_decks(), merge_similarity=None)
        names = {c.name for c in unmerged.clusters("modern")}
        assert {"Living End", "Living End Cascade"} <= names

    def test_empty_input_builds_an_empty_model(self):
        empty = ArchetypeModel.build([])
        assert empty.formats == ()
        assert empty.classify(["Lightning Bolt"]) == UNKNOWN_ARCHETYPE


# ---------------------------------------------------------------------------
# Classifying partial samples
# ---------------------------------------------------------------------------


class TestClassifyPartialSamples:
    @pytest.mark.parametrize(
        ("cards", "expected"),
        [
            (
                ["Murktide Regent", "Consider", "Island", "Lightning Bolt", "Scalding Tarn"],
                "Izzet Murktide",
            ),
            (
                ["Goblin Guide", "Lava Spike", "Mountain", "Lightning Bolt", "Arid Mesa"],
                "Boros Burn",
            ),
            (["Urza's Tower", "Thought-Knot Seer", "Eldrazi Temple", "Wastes"], "Eldrazi Tron"),
            (["Urza's Mine", "Karn Liberated", "Ancient Stirrings", "Forest"], "Tron"),
            (["Violent Outburst", "Street Wraith", "Grief"], "Living End"),
        ],
    )
    def test_a_handful_of_names_is_enough(self, model, cards, expected):
        assert model.classify(cards, "Modern") == expected

    def test_names_are_matched_the_way_mtgo_spells_them(self, model):
        # Case, accents and one half of a split card all resolve.
        cards = ["MURKTIDE REGENT", "Ragavan, Nímble Pilferer", "Fire", "consider", "Island"]
        assert model.classify(cards, "modern") == "Izzet Murktide"

    def test_unrecognised_names_are_ignored_not_penalised(self, model):
        cards = ["Goblin Guide", "Lava Spike", "Rift Bolt", "Some Token", "Mis-parsed line"]
        assert model.classify(cards, "modern") == "Boros Burn"

    def test_held_out_decks_are_classified_from_random_partial_samples(self):
        """A miniature of the offline evaluation in the pull request.

        Leave-one-out over the fixture decks: each deck is removed, the model is
        fitted on the rest, and twelve random 8-name samples are dealt from it.
        """
        decks = fixture_decks()
        rng = random.Random(1035)
        correct = answered = total = 0
        for index, held_out in enumerate(decks):
            if is_color_bucket(held_out.archetype):
                continue
            fitted = ArchetypeModel.build(decks[:index] + decks[index + 1 :])
            for _ in range(12):
                cards = sample_seen_cards(held_out, 8, rng)
                total += 1
                result = fitted.classify(cards, held_out.mtg_format)
                if result == UNKNOWN_ARCHETYPE:
                    continue
                answered += 1
                cluster = _cluster_of(fitted, held_out.mtg_format, result)
                correct += held_out.archetype in cluster.labels
        assert correct / total >= 0.85
        assert correct / answered >= 0.95


class TestUnknownThreshold:
    def test_no_cards_or_no_known_cards(self, model):
        assert model.classify([], "modern") == UNKNOWN_ARCHETYPE
        assert model.match(["Nothing Anyone Plays"], "modern") is None
        assert model.classify(["Nothing Anyone Plays"], "modern") == UNKNOWN_ARCHETYPE

    def test_a_staple_two_archetypes_share_is_not_a_guess(self, model):
        result = model.match(["Lightning Bolt"], "modern")
        assert result is not None and result.archetype in {"Boros Burn", "Izzet Murktide"}
        assert result.confidence < model.min_confidence
        assert model.classify(["Lightning Bolt"], "modern") == UNKNOWN_ARCHETYPE

    def test_shared_lands_alone_do_not_pick_a_tron_deck(self, model):
        assert model.classify(["Urza's Tower", "Urza's Mine"], "modern") == UNKNOWN_ARCHETYPE

    def test_the_bar_is_what_decides(self):
        cards = ["Lightning Bolt", "Mountain"]
        lenient = ArchetypeModel.build(fixture_decks(), min_confidence=0.0)
        strict = ArchetypeModel.build(fixture_decks(), min_confidence=1.01)
        assert lenient.classify(cards, "modern") != UNKNOWN_ARCHETYPE
        assert strict.classify(["Murktide Regent", "Consider"], "modern") == UNKNOWN_ARCHETYPE

    def test_no_land_count_fallback(self, model):
        # The old detector called any unmatched pile "Aggro"/"Midrange"/"Control".
        assert model.classify([f"Unknown Creature {i}" for i in range(20)]) == UNKNOWN_ARCHETYPE


class TestFormatScoping:
    BURN_SPELLS = ["Lightning Bolt", "Rift Bolt", "Skewer the Critics", "Mountain"]

    def test_the_same_cards_name_each_formats_own_archetype(self, model):
        assert model.classify(self.BURN_SPELLS, "Modern") == "Boros Burn"
        assert model.classify(self.BURN_SPELLS, "Pauper") == "Burn"

    def test_a_format_scope_never_returns_another_formats_archetype(self, model):
        affinity = ["Myr Enforcer", "Thoughtcast", "Frogmite", "Seat of the Synod"]
        assert model.classify(affinity, "pauper") == "Affinity"
        assert model.classify(affinity, "modern") == UNKNOWN_ARCHETYPE

    @pytest.mark.parametrize("mtg_format", [None, "Unknown", "Vintage"])
    def test_unknown_or_uncached_format_scores_every_format(self, model, mtg_format):
        affinity = ["Myr Enforcer", "Thoughtcast", "Frogmite", "Seat of the Synod"]
        result = model.match(affinity, mtg_format)
        assert result is not None
        assert (result.archetype, result.mtg_format) == ("Affinity", "pauper")
        assert model.classify(["Murktide Regent", "Consider", "Island"], mtg_format) == (
            "Izzet Murktide"
        )


class TestDetectArchetype:
    def test_without_a_model_everything_is_unknown(self):
        assert detect_archetype(["Murktide Regent", "Dragon's Rage Channeler"]) == UNKNOWN_ARCHETYPE

    def test_empty_cards_are_unknown(self, model):
        assert detect_archetype([], model, "Modern") == UNKNOWN_ARCHETYPE

    def test_delegates_to_the_model_with_the_format(self, model):
        assert detect_archetype(TestFormatScoping.BURN_SPELLS, model, "Pauper") == "Burn"


# ---------------------------------------------------------------------------
# The service: reading the caches
# ---------------------------------------------------------------------------


def _write_caches(tmp_path: Path, decks: list[LabelledDeck]) -> ArchetypeModelService:
    """Lay the fixture decks out the way the three real caches store them."""
    hrefs: dict[tuple[str, str], str] = {}
    lists: dict[str, dict] = {}
    index: dict[str, dict] = {}
    texts: list[tuple[str, str, str]] = []
    for number, deck in enumerate(decks, start=1000):
        key = (deck.mtg_format, deck.archetype)
        if key not in hrefs:
            href = f"{deck.mtg_format}-{deck.archetype.lower().replace(' ', '-')}"
            hrefs[key] = href
            # Mixed-case format keys, as older writers left them.
            fmt_key = deck.mtg_format.title() if deck.mtg_format == "pauper" else deck.mtg_format
            lists.setdefault(fmt_key, {"timestamp": 0, "items": []})["items"].append(
                {"name": deck.archetype, "href": href}
            )
        item_number: str | int = number if number % 2 else str(number)
        index.setdefault(hrefs[key], {"timestamp": 0, "items": []})["items"].append(
            {"number": item_number, "date": "2026-09-01", "player": "p", "source": "mtgo"}
        )
        texts.append((str(number), deck_text(deck), "mtgo"))

    list_file = tmp_path / "archetype_list.json"
    decks_file = tmp_path / "archetype_decks_cache.json"
    db_file = tmp_path / "deck_cache.db"
    list_file.write_text(json.dumps(lists), encoding="utf-8")
    decks_file.write_text(json.dumps(index), encoding="utf-8")
    DeckTextCache(db_path=db_file).bulk_set(texts)
    return ArchetypeModelService(list_file, decks_file, db_file)


class TestServiceLoading:
    def test_joins_list_index_and_texts(self, tmp_path):
        decks = fixture_decks()
        service = _write_caches(tmp_path, decks)
        loaded = service.load_labelled_decks()
        assert len(loaded) == len(decks)
        by_label = {(d.mtg_format, d.archetype) for d in loaded}
        assert ("pauper", "Burn") in by_label and ("modern", "Izzet Murktide") in by_label
        burn = next(d for d in loaded if d.archetype == "Boros Burn")
        assert burn.mainboard["Lightning Bolt"] == 4.0

    def test_skips_what_the_model_cannot_use(self, tmp_path):
        service = _write_caches(tmp_path, fixture_decks(per_archetype=2))
        lists = json.loads(service.archetype_list_file.read_text(encoding="utf-8"))
        index = json.loads(service.archetype_decks_file.read_text(encoding="utf-8"))
        cache = DeckTextCache(db_path=service.deck_text_db_file)
        full_list = "\n".join(f"4 Card {i}" for i in range(15))
        # A Commander archetype, an href dropped from the list, a deck with no
        # cached text, a partial scrape, and one deck filed under two hrefs.
        lists["commander"] = {"items": [{"name": "Atraxa", "href": "commander-atraxa"}]}
        index["commander-atraxa"] = {"items": [{"number": "9001"}]}
        index["modern-renamed-away"] = {"items": [{"number": "9002"}]}
        index["modern-boros-burn"]["items"] += [{"number": "9003"}, {"number": "9004"}]
        index["modern-tron"]["items"].append({"number": "1000"})
        cache.bulk_set(
            [("9001", full_list, "x"), ("9002", full_list, "x"), ("9004", "4 Card\n4 Other", "x")]
        )
        service.archetype_list_file.write_text(json.dumps(lists), encoding="utf-8")
        service.archetype_decks_file.write_text(json.dumps(index), encoding="utf-8")

        loaded = service.load_labelled_decks()
        assert len(loaded) == len(fixture_decks(per_archetype=2))
        assert {d.mtg_format for d in loaded} == {"modern", "pauper"}

    @pytest.mark.parametrize("broken", ["archetype_list.json", "archetype_decks_cache.json"])
    def test_missing_or_corrupt_caches_give_no_decks(self, tmp_path, broken):
        service = _write_caches(tmp_path, fixture_decks(per_archetype=2))
        (tmp_path / broken).write_text("{not json", encoding="utf-8")
        assert service.load_labelled_decks() == []
        (tmp_path / broken).unlink()
        assert service.load_labelled_decks() == []

    def test_parse_deck_text(self):
        main, side = parse_deck_text(
            "4 Lightning Bolt\n2 Fire // Ice\n"
            "1 Island 0a1b2c3d-0000-4000-8000-00000000abcd\n"
            "junk line\n\nSideboard\n3 Pyroblast\n"
        )
        assert main == {"Lightning Bolt": 4.0, "Fire // Ice": 2.0, "Island": 1.0}
        assert side == {"Pyroblast": 3.0}


class TestServiceBuild:
    def test_build_fits_a_model_from_the_caches(self, tmp_path):
        service = _write_caches(tmp_path, fixture_decks())
        assert service.model is None and not service.is_ready
        model = service.build()
        assert model is service.model and service.is_ready
        assert model.classify(TestFormatScoping.BURN_SPELLS, "Pauper") == "Burn"
        assert service.last_build_seconds is not None

    def test_a_failed_build_keeps_the_previous_model(self, tmp_path, monkeypatch):
        service = _write_caches(tmp_path, fixture_decks())
        first = service.build()

        def explode():
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(service, "load_labelled_decks", explode)
        assert service.build() is None
        assert service.model is first

    def test_singleton(self):
        assert get_archetype_model_service() is get_archetype_model_service()
        first = get_archetype_model_service()
        reset_archetype_model_service()
        assert get_archetype_model_service() is not first


class _GatedService(ArchetypeModelService):
    """A service whose deck load blocks until the test releases it."""

    def __init__(self, decks: list[LabelledDeck]) -> None:
        super().__init__(Path("unused-list"), Path("unused-decks"), Path("unused.db"))
        self.release = threading.Event()
        self.started = threading.Event()
        self._decks = decks

    def load_labelled_decks(self) -> list[LabelledDeck]:
        self.started.set()
        assert self.release.wait(5), "test never released the build"
        return self._decks


class TestStartupAndNotReady:
    def test_background_build_does_not_block_the_caller(self):
        service = _GatedService(fixture_decks())
        started = time.perf_counter()
        service.start_background_build()
        assert time.perf_counter() - started < 0.5
        assert service.started.wait(5)
        assert not service.is_ready
        service.release.set()
        model = service.wait_until_ready(timeout=5)
        assert model is not None and service.is_ready

    def test_not_ready_waits_up_to_the_timeout_then_gives_up(self):
        service = _GatedService(fixture_decks())
        service.start_background_build()
        try:
            started = time.perf_counter()
            assert service.wait_until_ready(timeout=0.2) is None
            assert 0.15 <= time.perf_counter() - started < 2.0
            # ...and a parse made in that window labels matches Unknown.
            assert detect_archetype(["Murktide Regent"], service.model) == UNKNOWN_ARCHETYPE
        finally:
            service.release.set()
        assert service.wait_until_ready(timeout=5) is not None

    def test_waiting_without_any_build_requested_returns_at_once(self):
        service = _GatedService(fixture_decks())
        started = time.perf_counter()
        assert service.wait_until_ready(timeout=5) is None
        assert time.perf_counter() - started < 0.5

    def test_a_rebuild_in_flight_does_not_hide_the_current_model(self):
        service = _GatedService(fixture_decks())
        service.release.set()
        first = service.build()
        service.release.clear()
        service.started.clear()
        service.start_background_build()
        try:
            assert service.started.wait(5)
            assert service.wait_until_ready(timeout=5) is first
        finally:
            service.release.set()

    def test_a_failed_background_build_releases_waiters(self, monkeypatch):
        service = _GatedService(fixture_decks())
        monkeypatch.setattr(ArchetypeModel, "build", classmethod(lambda cls, decks: 1 / 0))
        service.release.set()
        service.start_background_build()
        started = time.perf_counter()
        assert service.wait_until_ready(timeout=5) is None
        assert time.perf_counter() - started < 4

    def test_submit_hands_the_job_to_the_given_worker(self):
        service = _GatedService(fixture_decks())
        service.release.set()
        jobs = []
        service.start_background_build(submit=jobs.append)
        assert len(jobs) == 1 and not service.is_ready
        jobs[0]()
        assert service.is_ready


class TestControllerWiring:
    def test_startup_submits_the_build_to_the_controller_worker(self, tmp_path, monkeypatch):
        from controllers.app_controller.lifecycle import LifecycleMixin

        service = _write_caches(tmp_path, fixture_decks())
        monkeypatch.setattr(
            "services.archetype_model_service._default_service", service, raising=False
        )

        class _Worker:
            def __init__(self):
                self.jobs = []

            def submit(self, func, *args, **kwargs):
                self.jobs.append(func)

        class _Stub:
            _worker = _Worker()

        stub = _Stub()
        LifecycleMixin._start_archetype_model_build(stub)
        assert len(stub._worker.jobs) == 1 and not service.is_ready
        stub._worker.jobs[0]()
        assert service.is_ready

    def test_parse_all_gamelogs_passes_the_ready_model(self, monkeypatch):
        import controllers.app_controller.controller as controller_module

        sentinel = object()
        waits = []

        class _Service:
            def wait_until_ready(self, timeout):
                waits.append(timeout)
                return sentinel

        captured = {}
        monkeypatch.setattr(controller_module, "get_archetype_model_service", lambda: _Service())
        monkeypatch.setattr(
            controller_module, "_parse_all_gamelogs", lambda **kw: captured.update(kw) or []
        )

        class _Stub:
            class card_service:  # noqa: N801 - attribute stand-in
                @staticmethod
                def get_card_manager():
                    return None

            @staticmethod
            def _loaded_rarity_index():
                return None

        controller_module.AppController.parse_all_gamelogs(_Stub(), directory="x")
        assert captured["archetype_model"] is sentinel
        assert waits == [controller_module.ARCHETYPE_MODEL_WAIT_SECONDS]


# ---------------------------------------------------------------------------
# DeckTextCache.get_many
# ---------------------------------------------------------------------------


class TestDeckTextCacheGetMany:
    def test_returns_only_cached_numbers_across_chunks(self, tmp_path):
        cache = DeckTextCache(db_path=tmp_path / "deck_cache.db")
        cache.bulk_set([(str(n), f"4 Card {n}", "mtgo") for n in range(2000)])
        wanted = [str(n) for n in range(0, 2000, 2)] + ["missing", "", "7"]
        found = cache.get_many(wanted)
        assert len(found) == 1001
        assert found["1998"] == "4 Card 1998" and "missing" not in found

    def test_does_not_touch_access_statistics(self, tmp_path):
        db = tmp_path / "deck_cache.db"
        cache = DeckTextCache(db_path=db)
        cache.bulk_set([("1", "4 Island", "mtgo")])
        assert cache.get_many(["1"]) == {"1": "4 Island"}
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT access_count FROM deck_cache").fetchone() == (0,)

    def test_empty_request(self, tmp_path):
        assert DeckTextCache(db_path=tmp_path / "d.db").get_many([]) == {}
