from __future__ import annotations

import threading
from typing import Any

from controllers.app_controller.cache_warmer import CacheWarmer


def _make_warmer(
    *,
    current_format: str = "Legacy",
    formats: list[str] | None = None,
    archetypes: dict[str, list[dict[str, Any]]] | None = None,
    decks: dict[str, list[dict[str, Any]]] | None = None,
    deck_text: dict[str, str] | None = None,
):
    formats = formats if formats is not None else ["Modern", "Legacy"]
    archetypes = archetypes or {
        "Legacy": [
            {"name": "A", "href": "legacy-a"},
            {"name": "B", "href": "legacy-b"},
        ],
        "Modern": [{"name": "C", "href": "modern-c"}],
    }
    decks = decks or {
        "legacy-a": [{"number": "1"}, {"number": "2"}],
        "legacy-b": [{"number": "3"}],
        "modern-c": [{"number": "4"}, {"number": "5"}],
    }
    deck_text = deck_text or {
        "1": "4 Card One\n2 Island\n",
        "2": "4 Card Two\n",
        "3": "4 Card Three\n",
        "4": "4 Card Four\n",
        "5": "4 Card Five\n",
    }

    fetched: list[str] = []
    queued: list[str] = []

    def get_archetypes(fmt: str) -> list[dict[str, Any]]:
        return archetypes.get(fmt, [])

    def get_decks(archetype: dict[str, Any]) -> list[dict[str, Any]]:
        return decks.get(archetype.get("href", ""), [])

    def download_text(deck: dict[str, Any]) -> str:
        number = str(deck.get("number"))
        fetched.append(number)
        return deck_text.get(number, "")

    def extract_names(text: str) -> list[str]:
        names = []
        for line in text.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                names.append(parts[1])
        return names

    def enqueue(request) -> None:
        queued.append(request.card_name)

    warmer = CacheWarmer(
        get_current_format=lambda: current_format,
        formats=formats,
        get_archetypes=get_archetypes,
        get_decks_for_archetype=get_decks,
        download_deck_text=download_text,
        extract_card_names=extract_names,
        enqueue_image=enqueue,
        start_delay=0.0,
        fast_throttle=0.0,
        slow_throttle=0.0,
        top_decks_per_format=6,
        progress_interval=50,
    )
    return warmer, fetched, queued


def test_ordered_formats_puts_selected_first_and_dedupes():
    warmer, _, _ = _make_warmer(current_format="Legacy")
    assert warmer._ordered_formats() == ["Legacy", "Modern"]


def test_ordered_formats_prepends_unknown_selected():
    warmer, _, _ = _make_warmer(current_format="Pauper")
    assert warmer._ordered_formats() == ["Pauper", "Modern", "Legacy"]


def test_ordered_formats_dedupes_case_insensitively():
    # The selected format differs only in case from one of the known formats, so
    # the .lower() dedup must drop the duplicate while keeping the selected
    # spelling first.
    warmer, _, _ = _make_warmer(current_format="legacy", formats=["Modern", "Legacy"])
    assert warmer._ordered_formats() == ["legacy", "Modern"]


def test_warm_images_uses_first_deck_per_archetype_selected_format_first():
    warmer, fetched, queued = _make_warmer()

    warmer._warm_images()

    # Legacy archetypes (A, B) processed before Modern (C); each uses decks[0].
    assert fetched == ["1", "3", "4"]
    # Basic land "Island" from deck 1 is skipped; real cards are queued.
    assert "Island" not in queued
    assert set(queued) == {"Card One", "Card Three", "Card Four"}


def test_warm_decklists_phases_and_dedup():
    warmer, fetched, _ = _make_warmer()

    warmer._warm_decklists()

    # Phase 1 (top deck per archetype, every format): 1, 3 (Legacy), 4 (Modern).
    # Phase 2 (all of selected Legacy): adds 2 (1, 3 already warmed).
    # Phase 3 (all of remaining Modern): adds 5 (4 already warmed).
    assert fetched == ["1", "3", "4", "2", "5"]
    # No deck fetched twice.
    assert len(fetched) == len(set(fetched))
    # All five decks returned text, so all count as hydrated.
    assert warmer._dl_ok == 5
    assert warmer._dl_failed == 0


def test_warm_decklists_deep_pass_is_capped():
    from utils.constants.timing import CACHE_WARMUP_DEEP_PASS_MAX_DECKS

    # One format, one archetype, far more lists than the deep-pass budget.
    total = CACHE_WARMUP_DEEP_PASS_MAX_DECKS + 50
    numbers = [str(n) for n in range(total)]
    warmer, fetched, _ = _make_warmer(
        current_format="Legacy",
        formats=["Legacy"],
        archetypes={"Legacy": [{"name": "A", "href": "legacy-a"}]},
        decks={"legacy-a": [{"number": n} for n in numbers]},
        deck_text={n: f"4 Card {n}\n" for n in numbers},
    )

    warmer._warm_decklists()

    # Phase 1 hydrates the archetype's top deck; the deep pass then hydrates at
    # most CACHE_WARMUP_DEEP_PASS_MAX_DECKS more — so the warmer stops well short
    # of every available list and the process can go idle.
    assert len(fetched) == 1 + CACHE_WARMUP_DEEP_PASS_MAX_DECKS
    assert len(fetched) == len(set(fetched))  # nothing fetched twice
    assert warmer._dl_ok == 1 + CACHE_WARMUP_DEEP_PASS_MAX_DECKS


def test_warm_decklists_deep_pass_budget_is_shared_across_formats():
    from utils.constants.timing import CACHE_WARMUP_DEEP_PASS_MAX_DECKS

    # Selected format alone holds more than the whole budget, so Phase 3 (the
    # other format) must get nothing left to fetch.
    legacy = [str(n) for n in range(CACHE_WARMUP_DEEP_PASS_MAX_DECKS + 20)]
    warmer, fetched, _ = _make_warmer(
        current_format="Legacy",
        formats=["Legacy", "Modern"],
        archetypes={
            "Legacy": [{"name": "A", "href": "legacy-a"}],
            "Modern": [{"name": "C", "href": "modern-c"}],
        },
        decks={
            "legacy-a": [{"number": n} for n in legacy],
            "modern-c": [{"number": "m1"}, {"number": "m2"}],
        },
        deck_text={**{n: f"4 Card {n}\n" for n in legacy}, "m1": "4 M1\n", "m2": "4 M2\n"},
    )

    warmer._warm_decklists()

    # Phase 1 takes Legacy's top deck and Modern's top deck (1 each); the shared
    # deep-pass budget is exhausted entirely within Legacy, so Modern's second
    # list ("m2") is never reached.
    assert "m2" not in fetched
    assert warmer._dl_ok == 2 + CACHE_WARMUP_DEEP_PASS_MAX_DECKS


def test_warm_decklists_counts_empty_text_as_failed():
    deck_text = {"1": "4 Card One\n", "3": "4 Card Three\n", "4": "4 Card Four\n", "5": ""}
    warmer, _, _ = _make_warmer(deck_text=deck_text)

    warmer._warm_decklists()

    # Deck 2 and 5 have no text; the rest hydrate.
    assert warmer._dl_ok == 3
    assert warmer._dl_failed == 2


def test_stop_before_start_does_no_work():
    warmer, fetched, queued = _make_warmer()
    warmer.stop()

    warmer._warm_images()
    warmer._warm_decklists()

    assert fetched == []
    assert queued == []


def test_failing_dependencies_are_swallowed():
    warmer, fetched, queued = _make_warmer()
    warmer._get_archetypes = lambda fmt: (_ for _ in ()).throw(RuntimeError("boom"))

    # Should not raise.
    warmer._warm_images()
    warmer._warm_decklists()

    # A failing archetype source yields no decks, so nothing is fetched, queued,
    # or counted as hydrated/failed — the warmer degrades to a clean no-op.
    assert queued == []
    assert fetched == []
    assert warmer._dl_ok == 0
    assert warmer._dl_failed == 0


def test_failing_deck_source_swallowed_and_other_archetypes_continue():
    # Archetype A's deck source raises; B and C still warm normally.
    warmer, fetched, queued = _make_warmer()
    original_get_decks = warmer._get_decks_for_archetype

    def get_decks(archetype: dict[str, Any]) -> list[dict[str, Any]]:
        if archetype.get("href") == "legacy-a":
            raise RuntimeError("decks boom")
        return original_get_decks(archetype)

    warmer._get_decks_for_archetype = get_decks

    warmer._warm_images()

    # _safe_decks swallows A's failure (no deck 1); B (deck 3) and C (deck 4) warm.
    assert fetched == ["3", "4"]
    assert set(queued) == {"Card Three", "Card Four"}


def test_failing_deck_text_counts_as_failed_and_warming_continues():
    # The download for one deck raises; _safe_deck_text returns "" so it is
    # counted as failed while the remaining decks still hydrate.
    warmer, fetched, _ = _make_warmer()
    original_download = warmer._download_deck_text

    def download(deck: dict[str, Any]) -> str:
        if str(deck.get("number")) == "2":
            # Record the attempt (as the real downloader would) before failing,
            # so deck 2 still appears in ``fetched`` though it never hydrates.
            fetched.append("2")
            raise RuntimeError("text boom")
        return original_download(deck)

    warmer._download_deck_text = download

    warmer._warm_decklists()

    # Deck 2 raised (counted failed); the other four hydrated. All still fetched.
    assert fetched == ["1", "3", "4", "2", "5"]
    assert warmer._dl_ok == 4
    assert warmer._dl_failed == 1


def test_warm_decklists_no_formats_is_a_clean_no_op():
    warmer, fetched, _ = _make_warmer(current_format="", formats=[])

    warmer._warm_decklists()

    # No formats to warm: early return before any work or tallies.
    assert fetched == []
    assert warmer._dl_ok == 0
    assert warmer._dl_failed == 0


def test_warm_images_dedupes_repeated_card_within_a_deck():
    # A card listed twice in the same decklist is queued only once.
    archetypes = {"Legacy": [{"name": "A", "href": "legacy-a"}]}
    decks = {"legacy-a": [{"number": "1"}]}
    deck_text = {"1": "4 Card One\n2 Card One\n1 Card Two\n"}
    warmer, fetched, queued = _make_warmer(
        current_format="Legacy",
        formats=["Legacy"],
        archetypes=archetypes,
        decks=decks,
        deck_text=deck_text,
    )

    warmer._warm_images()

    assert fetched == ["1"]
    # "Card One" appears on two lines but is enqueued exactly once.
    assert queued == ["Card One", "Card Two"]


def test_warm_images_basic_land_skip_and_dedup_are_case_insensitive():
    # An uppercase basic land must still be skipped, and the same card in two
    # different casings must be enqueued only once — both rely on .lower().
    archetypes = {"Legacy": [{"name": "A", "href": "legacy-a"}]}
    decks = {"legacy-a": [{"number": "1"}]}
    deck_text = {"1": "10 ISLAND\n4 Card One\n2 CARD ONE\n1 Card Two\n"}
    warmer, fetched, queued = _make_warmer(
        current_format="Legacy",
        formats=["Legacy"],
        archetypes=archetypes,
        decks=decks,
        deck_text=deck_text,
    )

    warmer._warm_images()

    assert fetched == ["1"]
    # "ISLAND" is a basic land regardless of case (skipped); "CARD ONE" is the
    # same card as "Card One" under .lower() so it is enqueued exactly once,
    # keeping the first-seen casing.
    assert queued == ["Card One", "Card Two"]


def test_stop_during_start_delay_does_no_work():
    # With a non-zero start delay, a stop requested during the initial wait must
    # short-circuit both warmers before any fetch happens.
    warmer, fetched, queued = _make_warmer()
    warmer._start_delay = 5.0

    def run_with_delayed_stop(target) -> None:
        thread = threading.Thread(target=target)
        thread.start()
        # Give the thread a moment to reach the start-delay wait, then request
        # shutdown — the wait must observe the stop event and return promptly.
        threading.Event().wait(0.05)
        warmer.stop()
        thread.join(timeout=2.0)
        assert not thread.is_alive()

    run_with_delayed_stop(warmer._warm_images)
    run_with_delayed_stop(warmer._warm_decklists)

    # The stop interrupts the start-delay wait, so no decks are fetched or
    # images queued.
    assert fetched == []
    assert queued == []
    assert warmer._dl_ok == 0
    assert warmer._dl_failed == 0


def test_warm_decklists_phase1_limit_truncates_top_decks_per_format():
    # Many archetypes per format, each with a deck, so the Phase 1 total-count
    # cap (top_decks_per_format) is the binding constraint and actually fires.
    archetypes = {
        "Legacy": [{"name": n, "href": f"legacy-{n}"} for n in ("a", "b", "c", "d")],
        "Modern": [{"name": n, "href": f"modern-{n}"} for n in ("e", "f", "g")],
    }
    decks = {
        "legacy-a": [{"number": "1"}],
        "legacy-b": [{"number": "2"}],
        "legacy-c": [{"number": "3"}],
        "legacy-d": [{"number": "4"}],
        "modern-e": [{"number": "5"}],
        "modern-f": [{"number": "6"}],
        "modern-g": [{"number": "7"}],
    }
    warmer, fetched, _ = _make_warmer(archetypes=archetypes, decks=decks)
    warmer._top_decks_per_format = 2

    # Phase 1 alone, capped at 2 decks per format: Legacy 1,2 then Modern 5,6.
    phase1 = [
        deck["number"]
        for fmt in warmer._ordered_formats()
        for deck in warmer._iter_format_decks(fmt, per_archetype=1, limit=2)
    ]
    assert phase1 == ["1", "2", "5", "6"]

    # End to end: Phase 1 takes only the first 2 archetypes of each format;
    # the remaining archetypes are then backfilled in Phases 2 and 3.
    warmer._warm_decklists()
    assert fetched == ["1", "2", "5", "6", "3", "4", "7"]
    assert len(fetched) == len(set(fetched))


def test_start_is_idempotent_and_stop_clears_threads():
    warmer, _, _ = _make_warmer()

    started = threading.Event()
    release = threading.Event()

    # Block each thread body so start() can be inspected before they finish.
    def blocking_format() -> str:
        started.set()
        release.wait(1.0)
        return "Legacy"

    warmer._get_current_format = blocking_format

    warmer.start()
    threads = list(warmer._threads)
    assert len(threads) == 2
    assert {t.name for t in threads} == {"cache-warmer-images", "cache-warmer-decklists"}

    # A second start() while threads exist is a no-op (no new threads spawned).
    warmer.start()
    assert warmer._threads == threads

    assert started.wait(1.0)
    release.set()

    warmer.stop()
    assert warmer._stop_event.is_set()
    assert warmer._threads == []
    for thread in threads:
        assert not thread.is_alive()


def test_mid_run_stop_halts_decklist_warming_immediately():
    warmer, fetched, _ = _make_warmer()

    original_download = warmer._download_deck_text

    def download_then_stop(deck: dict[str, Any]) -> str:
        text = original_download(deck)
        # Request shutdown after the very first deck is fetched.
        warmer.stop()
        return text

    warmer._download_deck_text = download_then_stop

    warmer._warm_decklists()

    # Only the pre-stop deck is fetched; cooperative cancellation halts the rest.
    assert fetched == ["1"]


def test_mid_run_stop_halts_image_warming_immediately():
    warmer, fetched, queued = _make_warmer()

    original_download = warmer._download_deck_text

    def download_then_stop(deck: dict[str, Any]) -> str:
        text = original_download(deck)
        warmer.stop()
        return text

    warmer._download_deck_text = download_then_stop

    warmer._warm_images()

    # Only the first archetype's deck is fetched before the stop is observed.
    assert fetched == ["1"]
    # The per-card stop check fires before any card from that deck is queued, so
    # no images are enqueued once shutdown is requested mid-run.
    assert queued == []
