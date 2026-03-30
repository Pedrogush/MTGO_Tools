"""Tests for CardRepository data access layer."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from repositories.card_repository import CardRepository


@pytest.fixture
def mock_card_manager():
    """Mock CardDataManager for testing."""
    manager = SimpleNamespace()
    manager._cards = {"Lightning Bolt": {"name": "Lightning Bolt", "cmc": 1}}
    manager.is_loaded = True
    manager.get_card = Mock(return_value={"name": "Lightning Bolt", "mana_cost": "{R}", "cmc": 1})
    manager.search_cards = Mock(
        return_value=[
            {"name": "Lightning Bolt"},
            {"name": "Lightning Strike"},
        ]
    )
    manager.get_printings = Mock(
        return_value=[
            {"set": "LEA", "name": "Lightning Bolt"},
            {"set": "M11", "name": "Lightning Bolt"},
        ]
    )
    manager.ensure_latest = Mock(return_value=True)
    return manager


@pytest.fixture
def card_repository(mock_card_manager):
    """CardRepository with mock manager."""
    return CardRepository(card_data_manager=mock_card_manager)


# ============= Card Metadata Tests =============


def test_get_card_metadata_success(card_repository, mock_card_manager):
    """Test getting card metadata successfully."""
    metadata = card_repository.get_card_metadata("Lightning Bolt")

    assert metadata is not None
    assert metadata["name"] == "Lightning Bolt"
    mock_card_manager.get_card.assert_called_once_with("Lightning Bolt")


def test_get_card_metadata_runtime_error(card_repository, mock_card_manager):
    """Test getting metadata when card data not loaded."""
    mock_card_manager.get_card = Mock(side_effect=RuntimeError("Card data not loaded"))

    metadata = card_repository.get_card_metadata("Lightning Bolt")

    assert metadata is None


def test_get_card_metadata_exception(card_repository, mock_card_manager):
    """Test getting metadata with generic exception."""
    mock_card_manager.get_card = Mock(side_effect=Exception("Some error"))

    metadata = card_repository.get_card_metadata("Lightning Bolt")

    assert metadata is None


# ============= Card Search Tests =============


def test_search_cards_success(card_repository, mock_card_manager):
    """Test searching cards successfully."""
    results = card_repository.search_cards(query="Lightning")

    assert len(results) == 2
    assert results[0]["name"] == "Lightning Bolt"
    mock_card_manager.search_cards.assert_called_once()


def test_search_cards_with_filters(card_repository, mock_card_manager):
    """Test searching with filters."""
    card_repository.search_cards(query="Bolt", colors=["R"], types=["Instant"])

    mock_card_manager.search_cards.assert_called_once()


def test_search_cards_runtime_error(card_repository, mock_card_manager):
    """Test searching when card data not loaded."""
    mock_card_manager.search_cards = Mock(side_effect=RuntimeError("Card data not loaded"))

    results = card_repository.search_cards(query="Lightning")

    assert results == []


def test_search_cards_exception(card_repository, mock_card_manager):
    """Test searching with generic exception."""
    mock_card_manager.search_cards = Mock(side_effect=Exception("Some error"))

    results = card_repository.search_cards(query="Lightning")

    assert results == []


# ============= Card Data Loading Tests =============


def test_is_card_data_loaded_true(card_repository):
    """Test checking if card data is loaded."""
    assert card_repository.is_card_data_loaded() is True


def test_is_card_data_loaded_false():
    """Test checking when card data is not loaded."""
    manager = SimpleNamespace()
    manager._cards = None
    manager.is_loaded = False
    repo = CardRepository(card_data_manager=manager)

    assert repo.is_card_data_loaded() is False


# ============= Collection Loading Tests =============


def test_load_collection_from_file_success(card_repository, tmp_path):
    """Test loading collection from file."""
    collection_data = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "Island", "quantity": 20},
    ]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 2
    assert cards[0]["name"] == "Lightning Bolt"
    assert cards[0]["quantity"] == 4


def test_load_collection_from_file_nested_structure(card_repository, tmp_path):
    """Test loading collection from file with nested structure."""
    collection_data = {"cards": [{"name": "Lightning Bolt", "quantity": 4}]}
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["name"] == "Lightning Bolt"


def test_load_collection_from_file_nonexistent(card_repository, tmp_path):
    """Test loading from nonexistent file."""
    filepath = tmp_path / "nonexistent.json"

    cards = card_repository.load_collection_from_file(filepath)

    assert cards == []


def test_load_collection_from_file_invalid_json(card_repository, tmp_path):
    """Test loading from file with invalid JSON."""
    filepath = tmp_path / "invalid.json"
    filepath.write_text("not valid json", encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert cards == []


def test_load_collection_from_file_invalid_quantity(card_repository, tmp_path):
    """Test loading with invalid quantity values."""
    collection_data = [
        {"name": "Valid Card", "quantity": 4},
        {"name": "Invalid Quantity", "quantity": "not a number"},
        {"name": "Negative Quantity", "quantity": -5},
    ]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    # Only valid card should be loaded
    assert len(cards) == 1
    assert cards[0]["name"] == "Valid Card"


def test_load_collection_from_file_float_quantity(card_repository, tmp_path):
    """Test loading with float quantity (should be converted to int)."""
    collection_data = [{"name": "Card", "quantity": 4.5}]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["quantity"] == 4  # Should be truncated to int


def test_load_collection_from_file_preserves_id(card_repository, tmp_path):
    """Test that loading preserves card IDs."""
    collection_data = [{"name": "Lightning Bolt", "quantity": 4, "id": "12345"}]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["id"] == "12345"


# ============= State Management Tests =============


def test_is_card_data_loading_initially_false(card_repository):
    """Test that loading state is initially false."""
    assert card_repository.is_card_data_loading() is False


def test_set_card_data_loading(card_repository):
    """Test setting card data loading state."""
    card_repository.set_card_data_loading(True)
    assert card_repository.is_card_data_loading() is True

    card_repository.set_card_data_loading(False)
    assert card_repository.is_card_data_loading() is False


def test_is_card_data_ready_initially_false():
    """Test that ready state is initially false."""
    repo = CardRepository()
    assert repo.is_card_data_ready() is False


def test_set_card_data_ready(card_repository):
    """Test setting card data ready state."""
    card_repository.set_card_data_ready(True)
    assert card_repository.is_card_data_ready() is True

    card_repository.set_card_data_ready(False)
    assert card_repository.is_card_data_ready() is False


def test_get_card_manager(card_repository, mock_card_manager):
    """Test getting card manager."""
    manager = card_repository.get_card_manager()
    assert manager == mock_card_manager


def test_set_card_manager(card_repository):
    """Test setting card manager."""
    new_manager = SimpleNamespace()
    card_repository.set_card_manager(new_manager)

    assert card_repository.get_card_manager() == new_manager
    assert card_repository.is_card_data_ready() is True


def test_set_card_manager_none(card_repository):
    """Test setting card manager to None."""
    card_repository.set_card_data_ready(True)
    card_repository.set_card_manager(None)

    assert card_repository.get_card_manager() is None
