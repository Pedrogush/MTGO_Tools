from __future__ import annotations

import pytest

from repositories.deck_repository.repository import DeckRepository
from repositories.metagame_repository.repository import MetagameRepository
from services.deck_service.averager import DeckAverager
from services.deck_service.text_builder import DeckTextBuilder
from services.deck_workflow_service import DeckWorkflowService


def make_repo(tmp_path) -> DeckRepository:
    """Real repository backed by an isolated on-disk SQLite database."""
    return DeckRepository(db_path=tmp_path / "decks.sqlite")


def make_metagame_repo(tmp_path) -> MetagameRepository:
    """Real metagame repository backed by isolated on-disk JSON caches."""
    return MetagameRepository(
        archetype_list_cache_file=tmp_path / "archetype_list.json",
        archetype_decks_cache_file=tmp_path / "archetype_decks.json",
    )


def build_service(
    *,
    deck_repo,
    deck_service=None,
    metagame_repo=None,
    **kwargs,
):
    return DeckWorkflowService(
        deck_repo=deck_repo,
        deck_service=deck_service if deck_service is not None else DeckAverager(),
        metagame_repo=metagame_repo,
        **kwargs,
    )


def test_fetch_archetypes_respects_force_flag(tmp_path):
    calls: list[tuple[str, bool]] = []

    def provider(fmt: str, *, allow_stale: bool):
        calls.append((fmt, allow_stale))
        return [{"name": "Test"}]

    service = build_service(deck_repo=make_repo(tmp_path), archetype_provider=provider)
    result = service.fetch_archetypes("Modern", force=True)

    assert result == [{"name": "Test"}]
    assert calls == [("modern", False)]


def test_fetch_archetypes_allows_stale_when_not_forced(tmp_path):
    calls: list[tuple[str, bool]] = []

    def provider(fmt: str, *, allow_stale: bool):
        calls.append((fmt, allow_stale))
        return []

    service = build_service(deck_repo=make_repo(tmp_path), archetype_provider=provider)
    service.fetch_archetypes("Legacy", force=False)

    assert calls == [("legacy", True)]


def test_load_decks_routes_all_and_archetype_scopes_through_real_repo(tmp_path):
    """Drive a real MetagameRepository off isolated caches and assert on deck VALUES."""
    metagame_repo = make_metagame_repo(tmp_path)
    archetype = {"name": "Dimir Control", "href": "modern-dimir-control"}

    # Seed the per-archetype deck cache that get_decks_for_archetype reads.
    metagame_repo._save_cached_decks(
        archetype["href"],
        [{"name": "Dimir Control", "number": "1", "source": "mtggoldfish"}],
    )
    # Seed the aggregated deck cache that get_all_cached_decks reads.
    metagame_repo._save_cached_decks(
        "pioneer-any",
        [{"name": "Any", "number": "2", "source": "mtgo", "event": "Pioneer Challenge"}],
    )

    service = build_service(deck_repo=make_repo(tmp_path), metagame_repo=metagame_repo)

    archetype_result = service.load_decks(
        scope="archetype", archetype=archetype, source_filter="mtggoldfish"
    )
    all_result = service.load_decks(scope="all", source_filter="mtgo", mtg_format="Pioneer")

    assert archetype_result == [{"name": "Dimir Control", "number": "1", "source": "mtggoldfish"}]
    assert all_result == [
        {"name": "Any", "number": "2", "source": "mtgo", "event": "Pioneer Challenge"}
    ]


def test_load_decks_archetype_scope_requires_archetype(tmp_path):
    service = build_service(
        deck_repo=make_repo(tmp_path), metagame_repo=make_metagame_repo(tmp_path)
    )
    with pytest.raises(ValueError, match="Archetype scope requires an archetype"):
        service.load_decks(scope="archetype", archetype=None, source_filter="mtggoldfish")


def test_load_decks_rejects_unsupported_scope(tmp_path):
    service = build_service(
        deck_repo=make_repo(tmp_path), metagame_repo=make_metagame_repo(tmp_path)
    )
    with pytest.raises(ValueError, match="Unsupported deck load scope: bogus"):
        service.load_decks(scope="bogus", source_filter="mtggoldfish")


def test_download_deck_text_uses_injected_dependencies(tmp_path):
    download_calls: list[tuple[str, str | None]] = []
    reader_calls = 0

    def downloader(deck_number: str, source_filter: str | None = None):
        download_calls.append((deck_number, source_filter))

    def reader():
        nonlocal reader_calls
        reader_calls += 1
        return "deck text"

    service = build_service(
        deck_repo=make_repo(tmp_path), deck_downloader=downloader, deck_reader=reader
    )
    deck_text = service.download_deck_text("123", source_filter="mtgo")

    assert deck_text == "deck text"
    assert download_calls == [("123", "mtgo")]
    assert reader_calls == 1


def test_set_and_get_decks_list_round_trip(tmp_path):
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)
    decks = [{"name": "Burn", "number": "9"}]

    service.set_decks_list(decks)

    assert service.get_decks_list() == decks


# --------------------------------------------------------------------------- averaging


def _decklist_reader(decklists: dict[str, str]):
    """A real reader/downloader pair driven by a row->decklist mapping.

    The real ``build_daily_average_deck`` calls ``download_func(number)`` and
    then ``read_func()``; this pair mimics that by remembering the most recently
    requested deck's text, exactly like the file-backed reader does in prod.
    """
    state = {"current": ""}

    def downloader(deck_number: str, source_filter: str | None = None) -> None:
        state["current"] = decklists[deck_number]

    def reader() -> str:
        return state["current"]

    return downloader, reader


def test_build_daily_average_buffer_accumulates_real_card_counts(tmp_path):
    repo = make_repo(tmp_path)
    deck_service = DeckAverager()
    decklists = {
        "a": "4 Brainstorm\n2 Island",
        "b": "2 Brainstorm\n3 Island",
    }
    downloader, reader = _decklist_reader(decklists)
    progress_calls: list[tuple[int, int]] = []

    service = build_service(
        deck_repo=repo,
        deck_service=deck_service,
        deck_downloader=downloader,
        deck_reader=reader,
    )
    rows = [{"number": "a"}, {"number": "b"}]
    buffer = service.build_daily_average_buffer(
        rows,
        source_filter="both",
        on_progress=lambda index, total: progress_calls.append((index, total)),
    )

    # Default method is "karsten": the buffer counts, per unique copy index, how
    # many decks contained at least that many copies of the card.
    assert buffer == {
        "Brainstorm\x001": 2,  # both decks have >=1 Brainstorm
        "Brainstorm\x002": 2,  # both decks have >=2 Brainstorm
        "Brainstorm\x003": 1,  # only deck "a" has >=3
        "Brainstorm\x004": 1,  # only deck "a" has >=4
        "Island\x001": 2,
        "Island\x002": 2,
        "Island\x003": 1,  # only deck "b" has >=3 Island
    }
    assert progress_calls == [(1, 2), (2, 2)]


def test_build_daily_average_buffer_threads_source_filter_to_downloader(tmp_path):
    """The configured source_filter must reach the injected downloader unchanged."""
    repo = make_repo(tmp_path)
    received_filters: list[str | None] = []
    decklists = {"a": "4 Brainstorm"}

    def downloader(deck_number: str, source_filter: str | None = None) -> None:
        received_filters.append(source_filter)

    def reader() -> str:
        return decklists["a"]

    service = build_service(
        deck_repo=repo,
        deck_service=DeckAverager(),
        deck_downloader=downloader,
        deck_reader=reader,
    )
    service.build_daily_average_buffer([{"number": "a"}], source_filter="mtgo")

    assert received_filters == ["mtgo"]


def test_build_daily_average_buffer_market_method_sums_quantities(tmp_path):
    repo = make_repo(tmp_path)
    deck_service = DeckAverager()
    decklists = {
        "a": "4 Brainstorm\n2 Island",
        "b": "2 Brainstorm\n3 Island",
    }
    downloader, reader = _decklist_reader(decklists)

    service = build_service(
        deck_repo=repo,
        deck_service=deck_service,
        deck_downloader=downloader,
        deck_reader=reader,
    )
    rows = [{"number": "a"}, {"number": "b"}]
    buffer = service.build_daily_average_buffer(rows, source_filter="both", method="market")

    # Non-karsten method sums raw quantities across decks.
    assert buffer == {"Brainstorm": 6.0, "Island": 5.0}


# --------------------------------------------------------------------------- saving


def test_save_deck_persists_file_and_db(tmp_path):
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)
    deck_info = {"name": "Dimir Control", "player": "Test"}

    file_path, deck_id = service.save_deck(
        deck_name="Dimir Control!",
        deck_content="4 Brainstorm",
        format_name="Legacy",
        deck=deck_info,
        deck_save_dir=tmp_path,
    )

    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == "4 Brainstorm"

    stored = repo.load_from_db(deck_id)
    assert stored["name"] == "Dimir Control!"
    assert stored["content"] == "4 Brainstorm"
    assert stored["format"] == "Legacy"
    assert stored["archetype"] == "Dimir Control"
    assert stored["player"] == "Test"
    assert stored["source"] == "mtggoldfish"
    assert stored["metadata"] == deck_info


def test_save_deck_manual_source_when_deck_is_none(tmp_path):
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)

    file_path, deck_id = service.save_deck(
        deck_name="My Manual Deck",
        deck_content="4 Lightning Bolt",
        format_name="Modern",
        deck=None,
        deck_save_dir=tmp_path,
    )

    assert file_path.exists()

    stored = repo.load_from_db(deck_id)
    assert stored["source"] == "manual"
    assert stored["archetype"] is None
    assert stored["player"] is None
    assert stored["metadata"] == {}


def test_save_deck_returns_file_even_when_db_save_fails(tmp_path):
    """File persistence succeeds; a DB failure is swallowed and ``deck_id`` is None."""
    repo = make_repo(tmp_path)

    def boom(**_kwargs):
        raise RuntimeError("db down")

    repo.save_to_db = boom  # type: ignore[method-assign]
    service = build_service(deck_repo=repo)

    file_path, deck_id = service.save_deck(
        deck_name="Resilient Deck",
        deck_content="1 Sol Ring",
        format_name="Commander",
        deck=None,
        deck_save_dir=tmp_path,
    )

    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == "1 Sol Ring"
    assert deck_id is None


# --------------------------------------------------------------------------- deck text


def test_build_deck_text_prefers_existing_current_text(tmp_path):
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("existing deck")
    service = build_service(deck_repo=repo)
    assert service.build_deck_text({"main": []}) == "existing deck"


@pytest.mark.parametrize("fallback_key", ["deck_text", "content", "text"])
def test_build_deck_text_falls_back_through_current_deck_keys(tmp_path, fallback_key):
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("")
    repo.set_current_deck({fallback_key: "fallback deck"})
    service = build_service(deck_repo=repo)

    # No zone cards, so the only source is the current-deck fallback keys.
    assert service.build_deck_text({}) == "fallback deck"


def test_build_deck_text_falls_through_to_current_deck_when_zones_yield_empty(tmp_path):
    """Zones are present but the builder yields empty -> current-deck fallback wins."""
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("")
    repo.set_current_deck({"deck_text": "cached deck"})
    service = build_service(deck_repo=repo, deck_service=DeckTextBuilder())

    # Both zones empty -> build_deck_text_from_zones returns "" -> fall through.
    assert service.build_deck_text({"main": [], "side": []}) == "cached deck"


def test_build_deck_text_falls_through_when_zone_builder_raises(tmp_path):
    """A malformed zone entry makes the builder raise; the fallback is returned, not raised."""
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("")
    repo.set_current_deck({"deck_text": "cached deck"})
    service = build_service(deck_repo=repo, deck_service=DeckTextBuilder())

    # Entry missing the required 'qty' key raises KeyError inside the builder.
    assert service.build_deck_text({"main": [{"name": "Card"}]}) == "cached deck"


def test_build_deck_text_uses_zone_cards_when_needed(tmp_path):
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("")
    repo.set_current_deck({})
    service = build_service(deck_repo=repo, deck_service=DeckTextBuilder())

    text = service.build_deck_text({"main": [{"name": "Card", "qty": 4}]})

    assert text == "4 Card"


def test_save_deck_to_a_chosen_path_records_the_assigned_archetype(tmp_path):
    """#1034: Save As picks the file; the archetype comes from the save dialog."""
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)
    target = tmp_path / "chosen" / "Izzet.txt"
    loaded_file = {"name": "Izzet", "path": str(target), "source": "file"}

    file_path, deck_id = service.save_deck(
        deck_name="Izzet",
        deck_content="4 Murktide Regent",
        format_name="Modern",
        deck=loaded_file,
        deck_save_dir=tmp_path / "unused",
        file_path=target,
        archetype="Izzet Murktide",
    )

    assert file_path == target
    assert target.read_text(encoding="utf-8") == "4 Murktide Regent"
    assert not (tmp_path / "unused").exists()
    stored = repo.load_from_db(deck_id)
    assert stored["archetype"] == "Izzet Murktide"
    assert stored["source"] == "file"
    assert repo.find_saved_deck(file_path=target)["id"] == deck_id


def test_save_deck_with_a_blank_archetype_stores_none(tmp_path):
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)

    _file_path, deck_id = service.save_deck(
        deck_name="Brew",
        deck_content="4 Island",
        format_name="Modern",
        deck={"name": "some-archetype-slug"},
        deck_save_dir=tmp_path,
        file_path=tmp_path / "Brew.txt",
        archetype="",
    )

    # An explicit blank is the user's choice; it does not fall back to the slug.
    assert repo.load_from_db(deck_id)["archetype"] is None


def test_a_record_holding_only_the_deck_id_still_saves_as_a_manual_deck(tmp_path):
    """A deck built here gets a record at save time, purely to hold its id.

    "Where did this deck come from" used to be answered by whether there was a
    record at all, so that record must not turn a hand-built deck into a scraped
    one on its way to the database.
    """
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)
    deck: dict = {}

    _file_path, deck_id = service.save_deck(
        deck_name="My Manual Deck",
        deck_content="4 Lightning Bolt",
        format_name="Modern",
        deck=deck,
        deck_save_dir=tmp_path,
    )

    stored = repo.load_from_db(deck_id)
    assert stored["source"] == "manual"
    assert stored["archetype"] is None
    assert stored["deck_uuid"] == deck["deck_uuid"] != ""


def test_renaming_a_deck_leaves_it_with_one_record_and_not_two(tmp_path):
    """The row follows the deck's id, so a save under a new name repoints it.

    Matching only on the file would give a renamed deck a second row -- and the
    stale one would still be what loading the old file found.
    """
    repo = make_repo(tmp_path)
    service = build_service(deck_repo=repo)
    deck = {"href": "modern-burn", "name": "modern-burn"}

    service.save_deck(
        deck_name="Mono Red",
        deck_content="4 Lightning Bolt",
        format_name="Modern",
        deck=deck,
        deck_save_dir=tmp_path,
    )
    renamed, _deck_id = service.save_deck(
        deck_name="Mono Red But Better",
        deck_content="4 Lightning Bolt\n4 Monastery Swiftspear",
        format_name="Modern",
        deck=deck,
        deck_save_dir=tmp_path,
    )

    rows = repo.get_decks()
    assert len(rows) == 1
    assert rows[0]["name"] == "Mono Red But Better"
    assert repo.find_saved_deck(file_path=renamed)["deck_uuid"] == deck["deck_uuid"]
