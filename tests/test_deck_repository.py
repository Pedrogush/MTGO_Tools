from __future__ import annotations

import pymongo

from repositories.deck_db_store import DeckDbStore
from repositories.deck_file_store import DeckFileStore
from repositories.deck_repository import DeckRepository
from repositories.deck_side_data_store import DeckSideDataStore
from repositories.deck_workspace_state import DeckWorkspaceState

SAMPLE_DECK = """4 Lightning Bolt
4 Counterspell
4 Opt

3 Duress
"""


class FakeInsertResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeDeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class FakeUpdateResult:
    def __init__(self, modified_count: int) -> None:
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, rows: list[dict], collection: FakeDeckCollection) -> None:
        self.rows = rows
        self.collection = collection

    def sort(self, sort_by: str, direction: int) -> FakeCursor:
        self.collection.last_sort = (sort_by, direction)
        return self

    def __iter__(self):
        return iter(self.rows)


class FakeDeckCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.last_find_query: dict | None = None
        self.last_sort: tuple[str, int] | None = None

    def insert_one(self, doc: dict) -> FakeInsertResult:
        self.docs.append(doc)
        return FakeInsertResult("deck-id")

    def find(self, query: dict) -> FakeCursor:
        self.last_find_query = query
        rows = [
            doc for doc in self.docs if all(doc.get(key) == value for key, value in query.items())
        ]
        return FakeCursor(rows, self)

    def find_one(self, query: dict) -> dict | None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    def delete_one(self, query: dict) -> FakeDeleteResult:
        original_len = len(self.docs)
        self.docs = [
            doc
            for doc in self.docs
            if not all(doc.get(key) == value for key, value in query.items())
        ]
        return FakeDeleteResult(original_len - len(self.docs))

    def update_one(self, query: dict, update: dict) -> FakeUpdateResult:
        doc = self.find_one(query)
        if doc is None:
            return FakeUpdateResult(0)
        doc.update(update["$set"])
        return FakeUpdateResult(1)


class FakeDb:
    def __init__(self) -> None:
        self.decks = FakeDeckCollection()


class FakeMongoClient:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self.database_name: str | None = None

    def get_database(self, name: str) -> FakeDb:
        self.database_name = name
        return self.db


def make_side_data_store(tmp_path) -> DeckSideDataStore:
    return DeckSideDataStore(
        notes_store=tmp_path / "notes.json",
        outboard_store=tmp_path / "outboard.json",
        guide_store=tmp_path / "guide.json",
    )


def test_deck_db_store_saves_and_filters_decks():
    db = FakeDb()
    store = DeckDbStore(FakeMongoClient(db))

    inserted_id = store.save_to_db(
        deck_name="Burn",
        deck_content=SAMPLE_DECK,
        format_type="Modern",
        archetype="Burn",
        player="Tester",
        source="manual",
        metadata={"source_id": 1},
    )
    result = store.get_decks(format_type="Modern", archetype="Burn", sort_by="name")

    assert inserted_id == "deck-id"
    assert result == db.decks.docs
    assert db.decks.docs[0]["date_saved"] is not None
    assert db.decks.last_find_query == {"format": "Modern", "archetype": "Burn"}
    assert db.decks.last_sort == ("name", pymongo.DESCENDING)


def test_deck_db_store_update_merges_metadata():
    db = FakeDb()
    deck_id = object()
    db.decks.docs.append({"_id": deck_id, "metadata": {"existing": True}, "name": "Old"})
    store = DeckDbStore(FakeMongoClient(db))

    updated = store.update_in_db(deck_id, deck_name="New", metadata={"new": True})

    assert updated is True
    assert db.decks.docs[0]["name"] == "New"
    assert db.decks.docs[0]["metadata"] == {"existing": True, "new": True}
    assert db.decks.docs[0]["date_modified"] is not None


def test_file_store_save_deck_with_blank_name_uses_fallback(tmp_path):
    store = DeckFileStore(decks_dir=tmp_path)

    result_path = store.save_deck_to_file("", SAMPLE_DECK)

    assert result_path.name == "saved_deck.txt"
    assert result_path.exists()
    assert result_path.read_text() == SAMPLE_DECK


def test_file_store_save_deck_with_valid_name(tmp_path):
    store = DeckFileStore(decks_dir=tmp_path)

    result_path = store.save_deck_to_file("My Awesome Deck", SAMPLE_DECK)

    assert result_path.name == "My Awesome Deck.txt"
    assert result_path.exists()


def test_file_store_save_deck_handles_duplicates(tmp_path):
    store = DeckFileStore(decks_dir=tmp_path)

    path1 = store.save_deck_to_file("", SAMPLE_DECK)
    path2 = store.save_deck_to_file("", SAMPLE_DECK)
    path3 = store.save_deck_to_file("   ", SAMPLE_DECK)

    assert path1.name == "saved_deck.txt"
    assert path2.name == "saved_deck_1.txt"
    assert path3.name == "saved_deck_2.txt"
    assert len({path1, path2, path3}) == 3


def test_file_store_save_deck_sanitizes_invalid_chars(tmp_path):
    store = DeckFileStore(decks_dir=tmp_path)

    result_path = store.save_deck_to_file("Deck:With/Invalid*Chars?", SAMPLE_DECK)

    assert ":" not in result_path.name
    assert "/" not in result_path.name
    assert "*" not in result_path.name
    assert "?" not in result_path.name
    assert result_path.exists()


def test_file_store_save_deck_creates_directory(tmp_path):
    nested_dir = tmp_path / "nested" / "path"
    store = DeckFileStore(decks_dir=nested_dir)

    result_path = store.save_deck_to_file("Test", SAMPLE_DECK)

    assert nested_dir.exists()
    assert result_path.exists()


def test_file_store_reads_and_migrates_legacy_current_deck_file(tmp_path):
    current_file = tmp_path / "decks" / "curr_deck.txt"
    legacy_file = tmp_path / "curr_deck.txt"
    legacy_file.write_text(SAMPLE_DECK, encoding="utf-8")
    store = DeckFileStore(
        current_deck_file=current_file,
        legacy_current_deck_files=(legacy_file,),
    )

    contents = store.read_current_deck_file()

    assert contents == SAMPLE_DECK
    assert current_file.read_text(encoding="utf-8") == SAMPLE_DECK
    assert not legacy_file.exists()


def test_file_store_lists_deck_files(tmp_path):
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    (tmp_path / "ignore.json").write_text("", encoding="utf-8")
    store = DeckFileStore(decks_dir=tmp_path)

    result = store.list_deck_files()

    assert [path.name for path in result] == ["a.txt", "b.txt"]


def test_side_data_store_persists_notes_outboard_and_guides(tmp_path):
    store = make_side_data_store(tmp_path)

    store.save_notes("deck-key", "Mulligan notes")
    store.save_outboard("deck-key", [{"name": "Card", "qty": 2}])
    store.save_sideboard_guide("deck-key", [{"matchup": "Mirror"}])

    assert store.load_notes("deck-key") == "Mulligan notes"
    assert store.load_outboard("deck-key") == [{"name": "Card", "qty": 2}]
    assert store.load_sideboard_guide("deck-key") == [{"matchup": "Mirror"}]


def test_side_data_store_handles_invalid_json(tmp_path):
    notes_store = tmp_path / "notes.json"
    notes_store.write_text("{", encoding="utf-8")
    store = DeckSideDataStore(
        notes_store=notes_store,
        outboard_store=tmp_path / "outboard.json",
        guide_store=tmp_path / "guide.json",
    )

    assert store.load_notes("deck-key") == ""


def test_workspace_state_tracks_deck_selection_and_hash():
    state = DeckWorkspaceState()

    state.set_decks_list([{"name": "Deck"}])
    state.set_current_deck({"name": "Manual Deck"})
    state.set_current_deck_text("2 Island\n1 Mountain")
    first_hash = state.get_current_decklist_hash()
    state.set_current_deck_text("1 Mountain\n2 Island")

    assert state.get_decks_list() == [{"name": "Deck"}]
    assert state.get_current_deck_key() == "manual deck"
    assert state.get_current_decklist_hash() == first_hash
    state.clear_decks_list()
    assert state.get_decks_list() == []


def test_repository_facade_delegates_to_injected_stores(tmp_path):
    db = FakeDb()
    repo = DeckRepository(
        db_store=DeckDbStore(FakeMongoClient(db)),
        file_store=DeckFileStore(decks_dir=tmp_path),
        side_data_store=make_side_data_store(tmp_path),
        workspace_state=DeckWorkspaceState(),
    )

    file_path = repo.save_deck_to_file("Burn", SAMPLE_DECK)
    repo.save_notes("burn", "notes")
    repo.set_current_deck({"href": "burn"})
    inserted_id = repo.save_to_db("Burn", SAMPLE_DECK)

    assert file_path.exists()
    assert repo.load_notes("burn") == "notes"
    assert repo.get_current_deck_key() == "burn"
    assert inserted_id == "deck-id"
