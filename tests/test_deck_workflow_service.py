from __future__ import annotations

import pytest

from repositories.deck_repository.repository import DeckRepository
from services.deck_service.averager import DeckAverager
from services.deck_service.text_builder import DeckTextBuilder
from services.deck_workflow_service import DeckWorkflowService


class FakeMetagameRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None, str, str | None]] = []

    def get_decks_for_archetype(self, archetype, source_filter):
        self.calls.append(("archetype", archetype, source_filter, None))
        return [{"name": archetype.get("name"), "number": "1"}]

    def get_all_cached_decks(self, source_filter, mtg_format=None):
        self.calls.append(("all", None, source_filter, mtg_format))
        return [{"name": "Any", "number": "2"}]


def make_repo(tmp_path) -> DeckRepository:
    """Real repository backed by an isolated on-disk SQLite database."""
    return DeckRepository(db_path=tmp_path / "decks.sqlite")


def build_service(
    *,
    deck_repo=None,
    deck_service=None,
    metagame_repo=None,
    **kwargs,
):
    return DeckWorkflowService(
        deck_repo=deck_repo if deck_repo is not None else DeckRepository(),
        deck_service=deck_service if deck_service is not None else DeckAverager(),
        metagame_repo=metagame_repo or FakeMetagameRepo(),
        **kwargs,
    )


def test_fetch_archetypes_respects_force_flag():
    calls: list[tuple[str, bool]] = []

    def provider(fmt: str, *, allow_stale: bool):
        calls.append((fmt, allow_stale))
        return [{"name": "Test"}]

    service = build_service(archetype_provider=provider)
    result = service.fetch_archetypes("Modern", force=True)

    assert result == [{"name": "Test"}]
    assert calls == [("modern", False)]


def test_fetch_archetypes_allows_stale_when_not_forced():
    calls: list[tuple[str, bool]] = []

    def provider(fmt: str, *, allow_stale: bool):
        calls.append((fmt, allow_stale))
        return []

    service = build_service(archetype_provider=provider)
    service.fetch_archetypes("Legacy", force=False)

    assert calls == [("legacy", True)]


def test_load_decks_routes_all_and_archetype_scopes_through_one_use_case():
    metagame_repo = FakeMetagameRepo()
    service = build_service(metagame_repo=metagame_repo)
    archetype = {"name": "Dimir Control"}

    archetype_result = service.load_decks(
        scope="archetype", archetype=archetype, source_filter="mtggoldfish"
    )
    all_result = service.load_decks(scope="all", source_filter="mtgo", mtg_format="Pioneer")

    assert archetype_result == [{"name": "Dimir Control", "number": "1"}]
    assert all_result == [{"name": "Any", "number": "2"}]
    assert metagame_repo.calls == [
        ("archetype", archetype, "mtggoldfish", None),
        ("all", None, "mtgo", "Pioneer"),
    ]


def test_load_decks_archetype_scope_requires_archetype():
    service = build_service()
    with pytest.raises(ValueError, match="Archetype scope requires an archetype"):
        service.load_decks(scope="archetype", archetype=None, source_filter="mtggoldfish")


def test_load_decks_rejects_unsupported_scope():
    service = build_service()
    with pytest.raises(ValueError, match="Unsupported deck load scope: bogus"):
        service.load_decks(scope="bogus", source_filter="mtggoldfish")


def test_download_deck_text_uses_injected_dependencies():
    download_calls: list[tuple[str, str | None]] = []
    reader_calls = 0

    def downloader(deck_number: str, source_filter: str | None = None):
        download_calls.append((deck_number, source_filter))

    def reader():
        nonlocal reader_calls
        reader_calls += 1
        return "deck text"

    service = build_service(deck_downloader=downloader, deck_reader=reader)
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


def test_build_deck_text_prefers_existing_values(tmp_path):
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("existing deck")
    service = build_service(deck_repo=repo)
    assert service.build_deck_text({"main": []}) == "existing deck"

    repo.set_current_deck_text("")
    repo.set_current_deck({"deck_text": "cached deck"})
    assert service.build_deck_text({}) == "cached deck"


@pytest.mark.parametrize("fallback_key", ["deck_text", "content", "text"])
def test_build_deck_text_falls_back_through_current_deck_keys(tmp_path, fallback_key):
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("")
    repo.set_current_deck({fallback_key: "fallback deck"})
    service = build_service(deck_repo=repo)

    # No zone cards, so the only source is the current-deck fallback keys.
    assert service.build_deck_text({}) == "fallback deck"


def test_build_deck_text_uses_zone_cards_when_needed(tmp_path):
    repo = make_repo(tmp_path)
    repo.set_current_deck_text("")
    repo.set_current_deck({})
    service = build_service(deck_repo=repo, deck_service=DeckTextBuilder())

    text = service.build_deck_text({"main": [{"name": "Card", "qty": 4}]})

    assert text == "4 Card"
