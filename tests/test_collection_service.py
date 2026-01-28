"""Tests for CollectionService business logic."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.collection_service import CollectionService


@pytest.fixture
def mock_card_repo(tmp_path):
    """Mock CardRepository for testing."""
    repo = SimpleNamespace()
    repo.get_collection_cache_path = Mock(return_value=tmp_path / "collection.json")
    repo.load_collection_from_file = Mock(
        return_value=[
            {"name": "Lightning Bolt", "quantity": 4},
            {"name": "Island", "quantity": 20},
            {"name": "Mountain", "quantity": 10},
        ]
    )
    repo.get_card_metadata = Mock(
        side_effect=lambda name: {
            "Lightning Bolt": {"rarity": "common"},
            "Island": {"rarity": "basic"},
            "Mountain": {"rarity": "basic"},
        }.get(name)
    )
    return repo


@pytest.fixture
def collection_service(mock_card_repo):
    """CollectionService with mock repository."""
    return CollectionService(card_repository=mock_card_repo)


@pytest.fixture
def temp_collection_file(tmp_path):
    """Create a temporary collection file for testing."""
    collection_data = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "Island", "quantity": 20},
        {"name": "Counterspell", "quantity": 3},
    ]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")
    return filepath


# ============= Collection Loading Tests =============


def test_load_collection_from_file(collection_service, mock_card_repo, temp_collection_file):
    """Test loading collection from file."""
    mock_card_repo.load_collection_from_file = Mock(
        return_value=[
            {"name": "Lightning Bolt", "quantity": 4},
            {"name": "Island", "quantity": 20},
        ]
    )

    success = collection_service.load_collection(temp_collection_file)

    assert success is True
    assert collection_service.is_loaded() is True
    assert collection_service.get_collection_size() == 2
    assert collection_service.get_owned_count("Lightning Bolt") == 4
    assert collection_service.get_owned_count("Island") == 20


def test_load_collection_nonexistent_file(collection_service, tmp_path):
    """Test loading collection from nonexistent file."""
    nonexistent = tmp_path / "nonexistent_collection.json"
    success = collection_service.load_collection(nonexistent)

    assert success is True
    assert collection_service.is_loaded() is True
    assert collection_service.get_collection_size() == 0


def test_load_collection_force_reload(collection_service, mock_card_repo, temp_collection_file):
    """Test force reloading collection."""
    mock_card_repo.load_collection_from_file = Mock(
        return_value=[{"name": "Island", "quantity": 5}]
    )

    # First load
    collection_service.load_collection(temp_collection_file)
    assert collection_service.get_owned_count("Island") == 5

    # Update mock to return different data
    mock_card_repo.load_collection_from_file = Mock(
        return_value=[{"name": "Island", "quantity": 10}]
    )

    # Load without force - should not reload
    collection_service.load_collection(temp_collection_file)
    assert collection_service.get_owned_count("Island") == 5

    # Load with force - should reload
    collection_service.load_collection(temp_collection_file, force=True)
    assert collection_service.get_owned_count("Island") == 10


def test_find_latest_cached_file(collection_service, tmp_path):
    """Test finding the most recent cached collection file."""
    # Create multiple collection files
    (tmp_path / "collection_full_trade_20240101.json").touch()
    (tmp_path / "collection_full_trade_20240102.json").touch()
    (tmp_path / "collection_full_trade_20240103.json").touch()

    latest = collection_service.find_latest_cached_file(tmp_path)

    assert latest is not None
    assert latest.name == "collection_full_trade_20240103.json"


def test_find_latest_cached_file_no_files(collection_service, tmp_path):
    """Test finding cached file when none exist."""
    latest = collection_service.find_latest_cached_file(tmp_path)
    assert latest is None


def test_load_from_cached_file_success(collection_service, tmp_path):
    """Test loading from cached collection file."""
    collection_data = [
        {"name": "lightning bolt", "quantity": 4},
        {"name": "island", "quantity": 10},
    ]
    filepath = tmp_path / "collection_full_trade_20240101.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    info = collection_service.load_from_cached_file(tmp_path)

    assert info["card_count"] == 2
    assert info["filepath"] == filepath
    assert "age_hours" in info
    assert collection_service.get_owned_count("lightning bolt") == 4


def test_load_from_cached_file_no_files(collection_service, tmp_path):
    """Test loading from cached file when none exist."""
    with pytest.raises(FileNotFoundError, match="No cached collection files found"):
        collection_service.load_from_cached_file(tmp_path)

    assert collection_service.get_collection_size() == 0


def test_load_from_card_list(collection_service):
    """Test loading collection from card list."""
    cards = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "Island", "quantity": 20},
    ]

    info = collection_service.load_from_card_list(cards)

    assert info["card_count"] == 2
    assert collection_service.get_owned_count("lightning bolt") == 4
    assert collection_service.get_owned_count("island") == 20


def test_export_to_file(collection_service, tmp_path):
    """Test exporting collection to file."""
    cards = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "Island", "quantity": 20},
    ]

    filepath = collection_service.export_to_file(cards, tmp_path)

    assert filepath is not None
    assert filepath.exists()
    assert "collection_full_trade_" in filepath.name

    # Verify file contents
    loaded_data = json.loads(filepath.read_text(encoding="utf-8"))
    assert len(loaded_data) == 2
    assert loaded_data[0]["name"] == "Lightning Bolt"


# ============= Ownership Checking Tests =============


def test_owns_card_sufficient_copies(collection_service):
    """Test checking ownership with sufficient copies."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 10})

    assert collection_service.owns_card("Lightning Bolt", 1) is True
    assert collection_service.owns_card("Lightning Bolt", 4) is True
    assert collection_service.owns_card("Island", 5) is True


def test_owns_card_insufficient_copies(collection_service):
    """Test checking ownership with insufficient copies."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    assert collection_service.owns_card("Lightning Bolt", 4) is False
    assert collection_service.owns_card("Island", 1) is False


def test_get_owned_count(collection_service):
    """Test getting owned count for cards."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 10})

    assert collection_service.get_owned_count("Lightning Bolt") == 4
    assert collection_service.get_owned_count("Island") == 10
    assert collection_service.get_owned_count("Mountain") == 0


def test_get_ownership_status_fully_owned(collection_service):
    """Test ownership status for fully owned cards."""
    collection_service.set_inventory({"Lightning Bolt": 4})

    status, color = collection_service.get_ownership_status("Lightning Bolt", 3)

    assert status == "Owned 4/3"
    assert color == (120, 200, 120)  # Green


def test_get_ownership_status_partially_owned(collection_service):
    """Test ownership status for partially owned cards."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    status, color = collection_service.get_ownership_status("Lightning Bolt", 4)

    assert status == "Owned 2/4"
    assert color == (230, 200, 90)  # Orange


def test_get_ownership_status_not_owned(collection_service):
    """Test ownership status for not owned cards."""
    collection_service.set_inventory({})

    status, color = collection_service.get_ownership_status("Lightning Bolt", 4)

    assert status == "Owned 0/4"
    assert color == (230, 120, 120)  # Red


# ============= Deck Analysis Tests =============


def test_analyze_deck_ownership(collection_service):
    """Test analyzing deck ownership."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 20, "Counterspell": 2})

    deck_text = """4 Lightning Bolt
20 Island
4 Counterspell
4 Mountain"""

    analysis = collection_service.analyze_deck_ownership(deck_text)

    assert analysis["total_unique"] == 4
    assert analysis["fully_owned"] == 2  # Lightning Bolt and Island
    assert analysis["partially_owned"] == 1  # Counterspell (2/4)
    assert analysis["not_owned"] == 1  # Mountain
    assert analysis["ownership_percentage"] == 50.0
    assert len(analysis["missing_cards"]) == 2  # Counterspell and Mountain


def test_analyze_deck_ownership_with_sideboard(collection_service):
    """Test analyzing deck ownership with sideboard cards."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Dismember": 3})

    deck_text = """4 Lightning Bolt

Sideboard
4 Dismember"""

    analysis = collection_service.analyze_deck_ownership(deck_text)

    assert analysis["total_unique"] == 2
    assert analysis["fully_owned"] == 1  # Lightning Bolt
    assert analysis["partially_owned"] == 1  # Dismember (3/4)


def test_get_missing_cards_list(collection_service):
    """Test getting list of missing cards."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    deck_text = """4 Lightning Bolt
4 Island"""

    missing = collection_service.get_missing_cards_list(deck_text)

    assert len(missing) == 2
    assert ("Lightning Bolt", 2) in missing
    assert ("Island", 4) in missing


# ============= Collection Statistics Tests =============


def test_get_collection_statistics(collection_service, mock_card_repo):
    """Test getting collection statistics."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 20, "Mountain": 10})

    stats = collection_service.get_collection_statistics()

    assert stats["loaded"] is True
    assert stats["unique_cards"] == 3
    assert stats["total_cards"] == 34
    assert stats["average_copies"] == pytest.approx(34 / 3)
    assert "rarity_distribution" in stats


def test_get_collection_statistics_not_loaded(collection_service):
    """Test getting statistics when collection not loaded."""
    stats = collection_service.get_collection_statistics()

    assert stats["loaded"] is False
    assert "message" in stats


# ============= Collection Updates Tests =============


def test_add_cards(collection_service):
    """Test adding cards to collection."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    collection_service.add_cards("Lightning Bolt", 2)
    assert collection_service.get_owned_count("Lightning Bolt") == 4

    collection_service.add_cards("Island", 10)
    assert collection_service.get_owned_count("Island") == 10


def test_add_cards_zero_or_negative(collection_service):
    """Test adding zero or negative cards does nothing."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    collection_service.add_cards("Lightning Bolt", 0)
    assert collection_service.get_owned_count("Lightning Bolt") == 2

    collection_service.add_cards("Lightning Bolt", -5)
    assert collection_service.get_owned_count("Lightning Bolt") == 2


def test_remove_cards(collection_service):
    """Test removing cards from collection."""
    collection_service.set_inventory({"Lightning Bolt": 4})

    collection_service.remove_cards("Lightning Bolt", 2)
    assert collection_service.get_owned_count("Lightning Bolt") == 2

    collection_service.remove_cards("Lightning Bolt", 2)
    assert collection_service.get_owned_count("Lightning Bolt") == 0


def test_remove_cards_removes_entry_when_zero(collection_service):
    """Test that removing cards removes entry when count reaches zero."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    collection_service.remove_cards("Lightning Bolt", 2)

    assert "Lightning Bolt" not in collection_service.get_inventory()


def test_remove_cards_prevents_negative(collection_service):
    """Test removing more cards than owned."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    collection_service.remove_cards("Lightning Bolt", 5)
    assert collection_service.get_owned_count("Lightning Bolt") == 0


def test_set_card_count(collection_service):
    """Test setting card count directly."""
    collection_service.set_inventory({})

    collection_service.set_card_count("Lightning Bolt", 4)
    assert collection_service.get_owned_count("Lightning Bolt") == 4

    collection_service.set_card_count("Lightning Bolt", 10)
    assert collection_service.get_owned_count("Lightning Bolt") == 10


def test_set_card_count_zero_removes_card(collection_service):
    """Test that setting count to zero removes the card."""
    collection_service.set_inventory({"Lightning Bolt": 4})

    collection_service.set_card_count("Lightning Bolt", 0)

    assert "Lightning Bolt" not in collection_service.get_inventory()


# ============= State Management Tests =============


def test_get_inventory(collection_service):
    """Test getting inventory dictionary."""
    test_inventory = {"Lightning Bolt": 4, "Island": 20}
    collection_service.set_inventory(test_inventory)

    inventory = collection_service.get_inventory()

    assert inventory == test_inventory


def test_clear_inventory(collection_service, tmp_path):
    """Test clearing inventory."""
    collection_service.set_inventory({"Lightning Bolt": 4})
    collection_service.set_collection_path(tmp_path / "test.json")

    collection_service.clear_inventory()

    assert collection_service.get_collection_size() == 0
    assert collection_service.is_loaded() is False
    assert collection_service.get_collection_path() is None


def test_get_and_set_collection_path(collection_service, tmp_path):
    """Test getting and setting collection path."""
    test_path = tmp_path / "collection.json"

    collection_service.set_collection_path(test_path)
    assert collection_service.get_collection_path() == test_path


def test_get_collection_size(collection_service):
    """Test getting collection size."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 20, "Mountain": 10})

    assert collection_service.get_collection_size() == 3


def test_get_total_cards(collection_service):
    """Test getting total cards including duplicates."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 20, "Mountain": 10})

    assert collection_service.get_total_cards() == 34
