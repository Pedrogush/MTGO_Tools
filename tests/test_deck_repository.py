import json
import tempfile
import threading
from pathlib import Path

import pytest

from repositories.deck_repository import DeckRepository

SAMPLE_DECK = """4 Lightning Bolt
4 Counterspell
4 Opt

3 Duress
"""


@pytest.fixture
def temp_dir():
    """Create a temporary directory for deck files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def deck_repo():
    """Create a DeckRepository instance."""
    return DeckRepository()


@pytest.fixture
def db_repo(tmp_path):
    """DeckRepository whose SQLite saved-deck DB lives in a temp directory."""
    return DeckRepository(db_path=tmp_path / "saved_decks.db")


def test_save_to_db_returns_integer_id_and_loads_back(db_repo):
    deck_id = db_repo.save_to_db(
        deck_name="Dimir Control",
        deck_content=SAMPLE_DECK,
        format_type="Legacy",
        archetype="Control",
        player="Tester",
        source="manual",
        metadata={"foo": "bar"},
    )

    assert isinstance(deck_id, int)

    loaded = db_repo.load_from_db(deck_id)
    assert loaded is not None
    assert loaded["name"] == "Dimir Control"
    assert loaded["content"] == SAMPLE_DECK
    assert loaded["format"] == "Legacy"
    assert loaded["metadata"] == {"foo": "bar"}


def test_get_decks_filters_by_format_and_archetype(db_repo):
    db_repo.save_to_db("A", SAMPLE_DECK, format_type="Legacy", archetype="Control")
    db_repo.save_to_db("B", SAMPLE_DECK, format_type="Modern", archetype="Aggro")

    legacy = db_repo.get_decks(format_type="Legacy")
    assert [d["name"] for d in legacy] == ["A"]

    aggro = db_repo.get_decks(archetype="Aggro")
    assert [d["name"] for d in aggro] == ["B"]

    assert len(db_repo.get_decks()) == 2


def test_update_in_db_merges_metadata(db_repo):
    deck_id = db_repo.save_to_db("A", SAMPLE_DECK, metadata={"keep": 1})

    assert db_repo.update_in_db(deck_id, deck_name="A2", metadata={"added": 2}) is True

    loaded = db_repo.load_from_db(deck_id)
    assert loaded["name"] == "A2"
    assert loaded["metadata"] == {"keep": 1, "added": 2}


def test_delete_from_db(db_repo):
    deck_id = db_repo.save_to_db("A", SAMPLE_DECK)

    assert db_repo.delete_from_db(deck_id) is True
    assert db_repo.load_from_db(deck_id) is None
    assert db_repo.delete_from_db(deck_id) is False


def test_save_to_db_does_not_require_external_server(db_repo):
    """SQLite persistence must work with no running database server (issue #473)."""
    deck_id = db_repo.save_to_db("Offline", SAMPLE_DECK)
    assert isinstance(deck_id, int)


def test_save_deck_with_blank_name_uses_fallback(deck_repo, temp_dir):
    """Verify that blank deck names use the fallback 'saved_deck'."""
    result_path = deck_repo.save_deck_to_file("", SAMPLE_DECK, directory=temp_dir)

    assert result_path.name == "saved_deck.txt"
    assert result_path.exists()
    assert result_path.read_text() == SAMPLE_DECK


def test_save_deck_with_whitespace_name_uses_fallback(deck_repo, temp_dir):
    """Verify that whitespace-only deck names use the fallback."""
    result_path = deck_repo.save_deck_to_file("   ", SAMPLE_DECK, directory=temp_dir)

    assert result_path.name == "saved_deck.txt"
    assert result_path.exists()


def test_save_deck_with_special_chars_only_uses_fallback(deck_repo, temp_dir):
    """Verify that names with only special characters use the fallback."""
    result_path = deck_repo.save_deck_to_file("***///***", SAMPLE_DECK, directory=temp_dir)

    assert result_path.name == "saved_deck.txt"
    assert result_path.exists()


def test_save_deck_with_valid_name(deck_repo, temp_dir):
    """Verify that valid deck names are preserved."""
    result_path = deck_repo.save_deck_to_file("My Awesome Deck", SAMPLE_DECK, directory=temp_dir)

    assert result_path.name == "My Awesome Deck.txt"
    assert result_path.exists()


def test_save_deck_handles_duplicates_with_fallback(deck_repo, temp_dir):
    """Verify that duplicate blank deck names get unique filenames."""
    # Save first blank deck
    path1 = deck_repo.save_deck_to_file("", SAMPLE_DECK, directory=temp_dir)
    assert path1.name == "saved_deck.txt"

    # Save second blank deck - should get _1 suffix
    path2 = deck_repo.save_deck_to_file("", SAMPLE_DECK, directory=temp_dir)
    assert path2.name == "saved_deck_1.txt"

    # Save third blank deck - should get _2 suffix
    path3 = deck_repo.save_deck_to_file("   ", SAMPLE_DECK, directory=temp_dir)
    assert path3.name == "saved_deck_2.txt"

    # All files should exist and be distinct
    assert path1.exists() and path2.exists() and path3.exists()
    assert len({path1, path2, path3}) == 3


def test_save_deck_handles_duplicates_with_normal_names(deck_repo, temp_dir):
    """Verify that duplicate normal deck names get unique filenames."""
    # Save first deck
    path1 = deck_repo.save_deck_to_file("Test Deck", SAMPLE_DECK, directory=temp_dir)
    assert path1.name == "Test Deck.txt"

    # Save duplicate - should get _1 suffix
    path2 = deck_repo.save_deck_to_file("Test Deck", SAMPLE_DECK, directory=temp_dir)
    assert path2.name == "Test Deck_1.txt"

    assert path1.exists() and path2.exists()


def test_save_deck_sanitizes_invalid_chars(deck_repo, temp_dir):
    """Verify that invalid filename characters are replaced."""
    result_path = deck_repo.save_deck_to_file(
        "Deck:With/Invalid*Chars?", SAMPLE_DECK, directory=temp_dir
    )

    # Should replace invalid chars with underscores
    assert ":" not in result_path.name
    assert "/" not in result_path.name
    assert "*" not in result_path.name
    assert "?" not in result_path.name
    assert result_path.exists()


def test_save_deck_creates_directory(deck_repo, temp_dir):
    """Verify that save_deck_to_file creates the directory if it doesn't exist."""
    nested_dir = temp_dir / "nested" / "path"
    assert not nested_dir.exists()

    result_path = deck_repo.save_deck_to_file("Test", SAMPLE_DECK, directory=nested_dir)

    assert nested_dir.exists()
    assert result_path.exists()


def test_concurrent_save_notes_does_not_lose_updates(deck_repo, temp_dir, monkeypatch):
    """Concurrent save_notes calls for different decks must all persist (issue #470)."""
    notes_path = temp_dir / "deck_notes.json"
    # Route the notes store at every import site to our temp file.
    monkeypatch.setattr("repositories.deck_repository.metadata_store.NOTES_STORE", notes_path)

    deck_keys = [f"deck_{i}" for i in range(20)]
    barrier = threading.Barrier(len(deck_keys))

    def writer(key: str) -> None:
        barrier.wait()
        deck_repo.save_notes(key, f"notes for {key}")

    threads = [threading.Thread(target=writer, args=(k,)) for k in deck_keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = json.loads(notes_path.read_text(encoding="utf-8"))
    assert data == {k: f"notes for {k}" for k in deck_keys}


# ---------------------------------------------------------------------------
# DatabaseMixin: sort_by whitelist (SQL-injection guard)
# ---------------------------------------------------------------------------


def test_get_decks_sort_by_name_orders_descending(db_repo):
    db_repo.save_to_db("Alpha", SAMPLE_DECK)
    db_repo.save_to_db("Charlie", SAMPLE_DECK)
    db_repo.save_to_db("Bravo", SAMPLE_DECK)

    names = [d["name"] for d in db_repo.get_decks(sort_by="name")]
    assert names == ["Charlie", "Bravo", "Alpha"]


def test_get_decks_rejects_non_whitelisted_sort_by(db_repo):
    """A non-whitelisted sort_by must silently fall back to date_saved
    ordering rather than being interpolated into the SQL string."""
    db_repo.save_to_db("A", SAMPLE_DECK)
    db_repo.save_to_db("B", SAMPLE_DECK)

    # Malicious value must not raise and must not affect the schema.
    decks = db_repo.get_decks(sort_by="id; DROP TABLE decks")
    assert len(decks) == 2

    # The table still exists and remains queryable.
    assert len(db_repo.get_decks()) == 2


# ---------------------------------------------------------------------------
# DatabaseMixin: _row_to_deck corrupt-metadata fallback and _id aliasing
# ---------------------------------------------------------------------------


def test_load_from_db_aliases_id_and_handles_corrupt_metadata(db_repo):
    import sqlite3

    # Create the row (and schema) via the normal API, then corrupt the
    # stored metadata directly to exercise the _row_to_deck fallback.
    deck_id = db_repo.save_to_db("Corrupt", SAMPLE_DECK)

    with sqlite3.connect(db_repo._get_db_path()) as conn:
        conn.execute(
            "UPDATE decks SET metadata = ? WHERE id = ?",
            ("not-valid-json", deck_id),
        )
        conn.commit()

    loaded = db_repo.load_from_db(deck_id)
    assert loaded is not None
    assert loaded["metadata"] == {}
    assert loaded["_id"] == deck_id


# ---------------------------------------------------------------------------
# DatabaseMixin: update_in_db partial / empty / missing-row branches
# ---------------------------------------------------------------------------


def test_update_in_db_content_only_leaves_name(db_repo):
    deck_id = db_repo.save_to_db("Original", SAMPLE_DECK)
    new_content = "4 Brainstorm\n"

    assert db_repo.update_in_db(deck_id, deck_content=new_content) is True

    loaded = db_repo.load_from_db(deck_id)
    assert loaded["content"] == new_content
    assert loaded["name"] == "Original"


def test_update_in_db_nonexistent_id_returns_false(db_repo):
    assert db_repo.update_in_db(999999, deck_name="ghost") is False


def test_update_in_db_no_fields_touches_only_date_modified(db_repo):
    deck_id = db_repo.save_to_db("Stable", SAMPLE_DECK)

    assert db_repo.update_in_db(deck_id) is True

    loaded = db_repo.load_from_db(deck_id)
    assert loaded["name"] == "Stable"
    assert loaded["content"] == SAMPLE_DECK
    assert loaded["date_modified"] is not None


def test_update_in_db_merges_onto_corrupt_existing_metadata(db_repo):
    import sqlite3

    deck_id = db_repo.save_to_db("Merge", SAMPLE_DECK, metadata={"old": 1})

    # Corrupt the stored metadata so the merge must fall back to {}.
    with sqlite3.connect(db_repo._get_db_path()) as conn:
        conn.execute(
            "UPDATE decks SET metadata = ? WHERE id = ?",
            ("{not json", deck_id),
        )
        conn.commit()

    assert db_repo.update_in_db(deck_id, metadata={"new": 2}) is True

    loaded = db_repo.load_from_db(deck_id)
    assert loaded["metadata"] == {"new": 2}


def test_update_in_db_metadata_only_on_nonexistent_id_returns_false(db_repo):
    # Ensure schema exists, then target a missing id with metadata only.
    db_repo.save_to_db("Seed", SAMPLE_DECK)
    assert db_repo.update_in_db(999999, metadata={"x": 1}) is False


# ---------------------------------------------------------------------------
# MetadataStoreMixin: notes / outboard / sideboard-guide roundtrips
# ---------------------------------------------------------------------------


def _route_stores(monkeypatch, temp_dir):
    monkeypatch.setattr(
        "repositories.deck_repository.metadata_store.NOTES_STORE",
        temp_dir / "deck_notes.json",
    )
    monkeypatch.setattr(
        "repositories.deck_repository.metadata_store.OUTBOARD_STORE",
        temp_dir / "deck_outboard.json",
    )
    monkeypatch.setattr(
        "repositories.deck_repository.metadata_store.GUIDE_STORE",
        temp_dir / "deck_sbguides.json",
    )


def test_notes_roundtrip_and_default(deck_repo, temp_dir, monkeypatch):
    _route_stores(monkeypatch, temp_dir)

    assert deck_repo.load_notes("missing") == ""

    deck_repo.save_notes("deck_a", "some notes")
    assert deck_repo.load_notes("deck_a") == "some notes"


def test_outboard_roundtrip_and_default(deck_repo, temp_dir, monkeypatch):
    _route_stores(monkeypatch, temp_dir)

    assert deck_repo.load_outboard("missing") == []

    cards = [{"name": "Bolt", "qty": 4}]
    deck_repo.save_outboard("deck_a", cards)
    assert deck_repo.load_outboard("deck_a") == cards


def test_sideboard_guide_roundtrip_and_default(deck_repo, temp_dir, monkeypatch):
    _route_stores(monkeypatch, temp_dir)

    assert deck_repo.load_sideboard_guide("missing") == []

    guide = [{"vs": "Burn", "in": ["Leyline"], "out": ["Opt"]}]
    deck_repo.save_sideboard_guide("deck_a", guide)
    assert deck_repo.load_sideboard_guide("deck_a") == guide


def test_load_json_store_returns_empty_on_corrupt_file(deck_repo, temp_dir, monkeypatch):
    _route_stores(monkeypatch, temp_dir)
    notes_path = temp_dir / "deck_notes.json"
    notes_path.write_text("{ this is not valid json", encoding="utf-8")

    # Corrupt store must be tolerated: load returns the documented default.
    assert deck_repo.load_notes("anything") == ""


# ---------------------------------------------------------------------------
# FilesystemMixin: read_current_deck_file + list_deck_files
# ---------------------------------------------------------------------------


def test_read_current_deck_file_missing_raises(deck_repo, temp_dir, monkeypatch):
    monkeypatch.setattr(
        "repositories.deck_repository.filesystem.CURR_DECK_FILE",
        temp_dir / "curr_deck.txt",
    )
    monkeypatch.setattr(
        "repositories.deck_repository.filesystem.LEGACY_CURR_DECK_CACHE",
        temp_dir / "cache" / "curr_deck.txt",
    )
    monkeypatch.setattr(
        "repositories.deck_repository.filesystem.LEGACY_CURR_DECK_ROOT",
        temp_dir / "legacy_root_curr_deck.txt",
    )

    with pytest.raises(FileNotFoundError):
        deck_repo.read_current_deck_file()


def test_read_current_deck_file_reads_primary(deck_repo, temp_dir, monkeypatch):
    curr = temp_dir / "curr_deck.txt"
    curr.write_text(SAMPLE_DECK, encoding="utf-8")
    monkeypatch.setattr("repositories.deck_repository.filesystem.CURR_DECK_FILE", curr)

    assert deck_repo.read_current_deck_file() == SAMPLE_DECK


def test_read_current_deck_file_migrates_legacy(deck_repo, temp_dir, monkeypatch):
    curr = temp_dir / "curr_deck.txt"
    legacy = temp_dir / "cache" / "curr_deck.txt"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(SAMPLE_DECK, encoding="utf-8")

    monkeypatch.setattr("repositories.deck_repository.filesystem.CURR_DECK_FILE", curr)
    monkeypatch.setattr("repositories.deck_repository.filesystem.LEGACY_CURR_DECK_CACHE", legacy)
    monkeypatch.setattr(
        "repositories.deck_repository.filesystem.LEGACY_CURR_DECK_ROOT",
        temp_dir / "legacy_root_curr_deck.txt",
    )

    contents = deck_repo.read_current_deck_file()
    assert contents == SAMPLE_DECK
    # Migration copied to the primary path and removed the legacy file.
    assert curr.exists()
    assert curr.read_text(encoding="utf-8") == SAMPLE_DECK
    assert not legacy.exists()


def test_list_deck_files_missing_dir_returns_empty(deck_repo, temp_dir):
    missing = temp_dir / "does_not_exist"
    assert deck_repo.list_deck_files(directory=missing) == []


def test_list_deck_files_returns_sorted_txt(deck_repo, temp_dir):
    (temp_dir / "b.txt").write_text(SAMPLE_DECK, encoding="utf-8")
    (temp_dir / "a.txt").write_text(SAMPLE_DECK, encoding="utf-8")
    (temp_dir / "notes.md").write_text("ignore", encoding="utf-8")

    files = deck_repo.list_deck_files(directory=temp_dir)
    assert [p.name for p in files] == ["a.txt", "b.txt"]


# ---------------------------------------------------------------------------
# UIStateMixin: get_current_deck_key
# ---------------------------------------------------------------------------


def test_get_current_deck_key_defaults_to_manual_when_no_deck(deck_repo):
    assert deck_repo.get_current_deck() is None
    assert deck_repo.get_current_deck_key() == "manual"


def test_get_current_deck_key_prefers_href(deck_repo):
    deck_repo.set_current_deck({"href": "/decklist/42", "name": "Burn"})
    assert deck_repo.get_current_deck_key() == "/decklist/42"


def test_get_current_deck_key_falls_back_to_lowercased_name(deck_repo):
    deck_repo.set_current_deck({"name": "Mono Red Burn"})
    assert deck_repo.get_current_deck_key() == "mono red burn"


def test_get_current_deck_key_manual_when_deck_has_no_href_or_name(deck_repo):
    deck_repo.set_current_deck({"format": "Legacy"})
    assert deck_repo.get_current_deck_key() == "manual"


# ---------------------------------------------------------------------------
# UIStateMixin: get_current_decklist_hash
# ---------------------------------------------------------------------------


def test_get_current_decklist_hash_empty_when_no_text(deck_repo):
    assert deck_repo.get_current_deck_text() == ""
    assert deck_repo.get_current_decklist_hash() == "empty"


def test_get_current_decklist_hash_empty_for_whitespace_only_text(deck_repo):
    deck_repo.set_current_deck_text("   \n\t\n   ")
    assert deck_repo.get_current_decklist_hash() == "empty"


def test_get_current_decklist_hash_is_stable_and_short(deck_repo):
    deck_repo.set_current_deck_text(SAMPLE_DECK)
    first = deck_repo.get_current_decklist_hash()
    second = deck_repo.get_current_decklist_hash()

    assert first == second
    assert first != "empty"
    assert len(first) == 16


def test_get_current_decklist_hash_is_order_independent(deck_repo):
    deck_repo.set_current_deck_text("4 Lightning Bolt\n4 Counterspell\n3 Duress")
    ordered = deck_repo.get_current_decklist_hash()

    deck_repo.set_current_deck_text("3 Duress\n  4 Counterspell  \n4 Lightning Bolt\n")
    shuffled = deck_repo.get_current_decklist_hash()

    # Lines are stripped and sorted before hashing, so reordering and
    # surrounding whitespace must not change the hash.
    assert ordered == shuffled


def test_get_current_decklist_hash_differs_for_different_decks(deck_repo):
    deck_repo.set_current_deck_text("4 Lightning Bolt\n")
    a = deck_repo.get_current_decklist_hash()

    deck_repo.set_current_deck_text("4 Brainstorm\n")
    b = deck_repo.get_current_decklist_hash()

    assert a != b


# ---------------------------------------------------------------------------
# UIStateMixin: build_daily_average_deck
# ---------------------------------------------------------------------------


def test_build_daily_average_deck_accumulates_and_reports_progress(deck_repo):
    decks = [{"number": 1}, {"number": 2}, {"number": 3}]
    downloaded: list[int] = []
    progress: list[tuple[int, int]] = []

    def download_func(number):
        downloaded.append(number)

    def read_func():
        # Return the content for the most recently downloaded deck.
        return f"content-{downloaded[-1]}"

    def add_to_buffer_func(buffer, deck_content):
        merged = dict(buffer)
        merged[deck_content] = merged.get(deck_content, 0.0) + 1.0
        return merged

    def progress_callback(index, total):
        progress.append((index, total))

    result = deck_repo.build_daily_average_deck(
        decks,
        download_func,
        read_func,
        add_to_buffer_func,
        progress_callback,
    )

    assert downloaded == [1, 2, 3]
    assert result == {"content-1": 1.0, "content-2": 1.0, "content-3": 1.0}
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_build_daily_average_deck_empty_without_progress_callback(deck_repo):
    calls: list[int] = []

    result = deck_repo.build_daily_average_deck(
        [],
        download_func=lambda number: calls.append(number),
        read_func=lambda: "",
        add_to_buffer_func=lambda buffer, content: buffer,
    )

    assert result == {}
    assert calls == []
