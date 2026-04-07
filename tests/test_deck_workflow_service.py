from __future__ import annotations

import json

from services.deck_workflow_service import DeckWorkflowService


class FakeDeckRepo:
    def __init__(self) -> None:
        self.decks_list: list[dict] = []
        self.current_deck_text = ""
        self.current_deck: dict[str, str] = {}
        self.saved_payload: dict | None = None
        self.daily_average_rows: list[list[dict]] = []

    def set_decks_list(self, decks: list[dict]) -> None:
        self.decks_list = decks

    def get_current_deck_text(self) -> str:
        return self.current_deck_text

    def set_current_deck_text(self, text: str) -> None:
        self.current_deck_text = text

    def get_current_deck(self) -> dict:
        return self.current_deck

    def set_current_deck(self, deck: dict | None) -> None:
        self.current_deck = deck or {}

    def save_deck_to_file(self, deck_name: str, deck_content: str, directory) -> object:
        from pathlib import Path

        from utils.deck import sanitize_filename

        safe_name = sanitize_filename(deck_name, fallback="saved_deck")
        path = Path(directory) / f"{safe_name}.txt"
        path.write_text(deck_content, encoding="utf-8")
        return path

    def save_to_db(self, **payload):
        self.saved_payload = payload
        return 123

    def build_daily_average_deck(
        self, rows, download_func, reader_func, add_to_buffer, progress_callback
    ):
        self.daily_average_rows.append(rows)
        for index, row in enumerate(rows, start=1):
            download_func(row["number"])
            progress_callback(index, len(rows))
        add_to_buffer({"name": "Card"}, 0.5)
        return {"Card": 0.5}


class FakeMetagameRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None, str]] = []

    def get_decks_for_archetype(self, archetype, source_filter):
        self.calls.append(("archetype", archetype, source_filter))
        return [{"name": archetype.get("name"), "number": "1"}]

    def get_all_cached_decks(self, source_filter):
        self.calls.append(("all", None, source_filter))
        return [{"name": "Any", "number": "2"}]


class FakeDeckService:
    def __init__(self) -> None:
        self.zone_calls: list[dict] = []
        self.buffer_calls = 0

    def build_deck_text_from_zones(self, zones):
        self.zone_calls.append(json.loads(json.dumps(zones)))
        return "from zones"

    def add_deck_to_buffer(self, *_args, **_kwargs):
        self.buffer_calls += 1

    def add_deck_to_karsten_buffer(self, *_args, **_kwargs):
        self.buffer_calls += 1


def build_service(
    *,
    deck_repo=None,
    deck_service=None,
    metagame_repo=None,
    **kwargs,
):
    return DeckWorkflowService(
        deck_repo=deck_repo or FakeDeckRepo(),
        deck_service=deck_service or FakeDeckService(),
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


def test_load_decks_routes_all_and_archetype_scopes_through_one_use_case():
    metagame_repo = FakeMetagameRepo()
    service = build_service(metagame_repo=metagame_repo)
    archetype = {"name": "Dimir Control"}

    archetype_result = service.load_decks(
        scope="archetype", archetype=archetype, source_filter="mtggoldfish"
    )
    all_result = service.load_decks(scope="all", source_filter="mtgo")

    assert archetype_result == [{"name": "Dimir Control", "number": "1"}]
    assert all_result == [{"name": "Any", "number": "2"}]
    assert metagame_repo.calls == [
        ("archetype", archetype, "mtggoldfish"),
        ("all", None, "mtgo"),
    ]


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


def test_build_daily_average_buffer_wires_dependencies():
    repo = FakeDeckRepo()
    deck_service = FakeDeckService()
    downloads: list[str] = []
    progress_calls: list[tuple[int, int]] = []

    def downloader(deck_number: str, source_filter: str | None = None):
        downloads.append(f"{deck_number}:{source_filter}")

    service = build_service(deck_repo=repo, deck_service=deck_service, deck_downloader=downloader)
    rows = [{"number": "a"}, {"number": "b"}]
    buffer = service.build_daily_average_buffer(
        rows,
        source_filter="both",
        on_progress=lambda index, total: progress_calls.append((index, total)),
    )

    assert buffer == {"Card": 0.5}
    assert downloads == ["a:both", "b:both"]
    assert progress_calls == [(1, 2), (2, 2)]
    assert deck_service.buffer_calls == 1
    assert repo.daily_average_rows == [rows]


def test_save_deck_persists_file_and_db(tmp_path):
    repo = FakeDeckRepo()
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
    assert deck_id == 123
    assert repo.saved_payload["deck_name"] == "Dimir Control!"
    assert repo.saved_payload["format_type"] == "Legacy"
    assert repo.saved_payload["archetype"] == "Dimir Control"
    assert repo.saved_payload["player"] == "Test"
    assert repo.saved_payload["source"] == "mtggoldfish"
    assert repo.saved_payload["metadata"] == deck_info


def test_build_deck_text_prefers_existing_values():
    repo = FakeDeckRepo()
    repo.current_deck_text = "existing deck"
    service = build_service(deck_repo=repo)
    assert service.build_deck_text({"main": []}) == "existing deck"

    repo.current_deck_text = ""
    repo.set_current_deck({"deck_text": "cached deck"})
    assert service.build_deck_text({}) == "cached deck"


def test_build_deck_text_uses_zone_cards_when_needed():
    repo = FakeDeckRepo()
    deck_service = FakeDeckService()
    repo.current_deck_text = ""
    repo.set_current_deck({})
    service = build_service(deck_repo=repo, deck_service=deck_service)

    text = service.build_deck_text({"main": [{"name": "Card", "qty": 4}]})

    assert text == "from zones"
    assert deck_service.zone_calls
