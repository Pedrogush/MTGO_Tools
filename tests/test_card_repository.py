"""Tests for CardRepository data access layer."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
    # No filters supplied -> colors/types pass through as None.
    mock_card_manager.search_cards.assert_called_once_with(
        query="Lightning", color_identity=None, type_filter=None
    )


def test_search_cards_with_filters(card_repository, mock_card_manager):
    """Test searching with filters maps args correctly.

    Guards the public->manager translation: colors->color_identity and
    types->type_filter must not be swapped or dropped.
    """
    card_repository.search_cards(query="Bolt", colors=["R"], types=["Instant"])

    mock_card_manager.search_cards.assert_called_once_with(
        query="Bolt", color_identity=["R"], type_filter=["Instant"]
    )


def test_search_cards_query_none_passed_as_empty_string(card_repository, mock_card_manager):
    """Test that a None query is forwarded to the manager as ''."""
    card_repository.search_cards(query=None)

    mock_card_manager.search_cards.assert_called_once_with(
        query="", color_identity=None, type_filter=None
    )


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


def test_load_collection_from_file_items_key(card_repository, tmp_path):
    """Test loading collection from a dict using the 'items' key."""
    collection_data = {"items": [{"name": "Lightning Bolt", "quantity": 4}]}
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["name"] == "Lightning Bolt"


def test_load_collection_from_file_nested_collection_dict(card_repository, tmp_path):
    """Test loading collection nested under a 'collection' dict (recursion)."""
    collection_data = {"collection": {"cards": [{"name": "Island", "quantity": 20}]}}
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["name"] == "Island"
    assert cards[0]["quantity"] == 20


def test_load_collection_from_file_nested_collection_list(card_repository, tmp_path):
    """Test loading collection nested under a 'collection' list (recursion)."""
    collection_data = {"collection": [{"name": "Forest", "quantity": 10}]}
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["name"] == "Forest"


def test_load_collection_from_file_skips_non_dict_and_empty_name(card_repository, tmp_path):
    """Test that non-dict entries and blank-name entries are filtered out."""
    collection_data = [
        "junk",
        None,
        {"name": "", "quantity": 1},
        {"name": "   ", "quantity": 1},
        {"name": "Real", "quantity": 2},
    ]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert cards[0]["name"] == "Real"
    assert cards[0]["quantity"] == 2


def test_load_collection_from_file_empty_list(card_repository, tmp_path):
    """Test loading an empty list returns [] via the no-entries path."""
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps([]), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert cards == []


def test_load_collection_from_file_empty_cards_dict(card_repository, tmp_path):
    """Test loading a dict with an empty 'cards' list returns []."""
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps({"cards": []}), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert cards == []


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


def test_card_data_manager_property_lazy_instantiation():
    """Test the lazy card_data_manager property creates a manager on demand."""
    repo = CardRepository()
    sentinel = SimpleNamespace()

    with patch(
        "repositories.card_repository.repository.CardDataManager", return_value=sentinel
    ) as mock_cls:
        manager = repo.card_data_manager
        # Second access should reuse the cached instance, not build a new one.
        again = repo.card_data_manager

    assert manager is sentinel
    assert again is sentinel
    mock_cls.assert_called_once_with()


# ============= ensure_card_data_loaded Tests =============


def test_ensure_card_data_loaded_uses_cached_manager(card_repository, mock_card_manager):
    """Test cached fast-path returns existing manager without reloading."""
    with patch("repositories.card_repository.state.load_card_manager") as mock_load:
        result = card_repository.ensure_card_data_loaded()

    assert result is mock_card_manager
    mock_load.assert_not_called()


def test_ensure_card_data_loaded_loads_when_no_manager():
    """Test load path runs when no manager is present yet."""
    repo = CardRepository()
    loaded = SimpleNamespace(is_loaded=True)

    with patch(
        "repositories.card_repository.state.load_card_manager", return_value=loaded
    ) as mock_load:
        result = repo.ensure_card_data_loaded()

    assert result is loaded
    mock_load.assert_called_once_with()
    assert repo.get_card_manager() is loaded
    assert repo.is_card_data_ready() is True


def test_ensure_card_data_loaded_force_reloads(card_repository, mock_card_manager):
    """Test force=True reloads even when a loaded manager is present."""
    reloaded = SimpleNamespace(is_loaded=True)

    with patch(
        "repositories.card_repository.state.load_card_manager", return_value=reloaded
    ) as mock_load:
        result = card_repository.ensure_card_data_loaded(force=True)

    assert result is reloaded
    mock_load.assert_called_once_with()
    assert card_repository.get_card_manager() is reloaded
