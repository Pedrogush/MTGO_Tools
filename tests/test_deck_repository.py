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
