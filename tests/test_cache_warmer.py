from __future__ import annotations

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
        throttle=0.0,
        top_decks_per_format=6,
    )
    return warmer, fetched, queued


def test_ordered_formats_puts_selected_first_and_dedupes():
    warmer, _, _ = _make_warmer(current_format="Legacy")
    assert warmer._ordered_formats() == ["Legacy", "Modern"]


def test_ordered_formats_prepends_unknown_selected():
    warmer, _, _ = _make_warmer(current_format="Pauper")
    assert warmer._ordered_formats() == ["Pauper", "Modern", "Legacy"]


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


def test_stop_before_start_does_no_work():
    warmer, fetched, queued = _make_warmer()
    warmer.stop()

    warmer._warm_images()
    warmer._warm_decklists()

    assert fetched == []
    assert queued == []


def test_failing_dependencies_are_swallowed():
    warmer, _, queued = _make_warmer()
    warmer._get_archetypes = lambda fmt: (_ for _ in ()).throw(RuntimeError("boom"))

    # Should not raise.
    warmer._warm_images()
    warmer._warm_decklists()

    assert queued == []
