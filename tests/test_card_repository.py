"""Tests for CardRepository data access layer.

Uses a real CardDataManager backed by tests/fixtures/atomic_cards_mini.json so
that schema regressions surface instead of being hidden behind mocks.
"""

import json
from pathlib import Path

import pytest

from repositories.card_repository import CardRepository
from utils.card_data import CardDataManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_data_dir(tmp_path_factory):
    """Temp dir with the mini fixture placed as atomic_cards_index.json."""
    data_dir = tmp_path_factory.mktemp("card_data")
    src = FIXTURES_DIR / "atomic_cards_mini.json"
    (data_dir / "atomic_cards_index.json").write_bytes(src.read_bytes())
    return data_dir


@pytest.fixture(scope="module")
def real_card_manager(fixture_data_dir):
    """Real CardDataManager loaded from the mini fixture (no network required)."""
    manager = CardDataManager(fixture_data_dir)
    manager._load_index()
    return manager


@pytest.fixture
def card_repository(real_card_manager):
    """CardRepository backed by real fixture data."""
    return CardRepository(card_data_manager=real_card_manager)


@pytest.fixture
def unloaded_repository(fixture_data_dir):
    """CardRepository whose manager has _cards=None (index not yet loaded)."""
    manager = CardDataManager(fixture_data_dir)
    # _load_index() intentionally NOT called — _cards stays None
    return CardRepository(card_data_manager=manager)


# ============= Card Metadata Tests =============


def test_get_card_metadata_success(card_repository):
    """Real CardEntry is returned for a card present in the fixture."""
    metadata = card_repository.get_card_metadata("Lightning Bolt")

    assert metadata is not None
    assert metadata["name"] == "Lightning Bolt"
    assert metadata["mana_cost"] == "{R}"
    assert metadata["mana_value"] == 1.0


def test_get_card_metadata_missing_card(card_repository):
    """None is returned for a card not present in the fixture."""
    metadata = card_repository.get_card_metadata("Jace, the Mind Sculptor")

    assert metadata is None


def test_get_card_metadata_unloaded(unloaded_repository):
    """None is returned when card data has not been loaded."""
    metadata = unloaded_repository.get_card_metadata("Lightning Bolt")

    assert metadata is None


# ============= Card Search Tests =============


def test_search_cards_by_name(card_repository):
    """Name-based query returns matching real CardEntry objects."""
    results = card_repository.search_cards(query="Lightning")

    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "Lightning Bolt" in names


def test_search_cards_by_color(card_repository):
    """Color-identity filter returns only cards matching that color."""
    results = card_repository.search_cards(colors=["U"])

    assert len(results) >= 1
    for card in results:
        assert "U" in card["color_identity"], f"{card['name']} is not blue"


def test_search_cards_no_filters(card_repository):
    """Empty query returns all 20 cards in the fixture."""
    results = card_repository.search_cards()

    assert len(results) == 20


def test_search_cards_unloaded(unloaded_repository):
    """Empty list is returned when card data has not been loaded."""
    results = unloaded_repository.search_cards(query="Lightning")

    assert results == []


# ============= Card Data Loading Tests =============


def test_is_card_data_loaded_true(card_repository):
    """Returns True when the manager holds real card data."""
    assert card_repository.is_card_data_loaded() is True


def test_is_card_data_loaded_false(unloaded_repository):
    """Returns False when _cards is None."""
    assert unloaded_repository.is_card_data_loaded() is False


def test_load_card_data_already_loaded(card_repository):
    """Returns True immediately when data is already in memory."""
    success = card_repository.load_card_data()

    assert success is True


def test_load_card_data_force_reload(fixture_data_dir):
    """force=True triggers ensure_latest; falls back to existing cache when offline."""
    manager = CardDataManager(fixture_data_dir)
    manager._load_index()
    repo = CardRepository(card_data_manager=manager)

    # ensure_latest gracefully falls back to the cached index when the network
    # is unavailable (CI), so this must succeed.
    success = repo.load_card_data(force=True)

    assert success is True
    assert repo.is_card_data_loaded() is True


def test_load_card_data_exception(tmp_path, monkeypatch):
    """Returns False when ensure_latest raises and no data is in memory.

    _download_and_rebuild is monkeypatched (network stub) so the test is
    deterministic without requiring a live internet connection.
    """
    manager = CardDataManager(tmp_path)
    # No index file exists → missing_index=True → ensure_latest must download.
    # Stub the download to simulate a network failure.

    def _fail(_remote_meta):
        raise RuntimeError("Simulated network failure")

    monkeypatch.setattr(manager, "_download_and_rebuild", _fail)

    repo = CardRepository(card_data_manager=manager)
    success = repo.load_card_data(force=True)

    assert success is False


# ============= Card Printings Tests =============


def test_get_card_printings_returns_empty(card_repository):
    """get_card_printings returns [] because CardDataManager has no get_printings method.

    Printings are sourced from card_images, not card_data, so calling this on
    a bare CardDataManager always raises AttributeError and is caught gracefully.
    """
    printings = card_repository.get_card_printings("Lightning Bolt")

    assert printings == []


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


def test_get_card_manager(card_repository, real_card_manager):
    """get_card_manager returns the real CardDataManager instance."""
    manager = card_repository.get_card_manager()
    assert manager is real_card_manager


def test_set_card_manager(card_repository, fixture_data_dir):
    """Setting a new manager marks data as ready."""
    new_manager = CardDataManager(fixture_data_dir)
    new_manager._load_index()
    card_repository.set_card_manager(new_manager)

    assert card_repository.get_card_manager() is new_manager
    assert card_repository.is_card_data_ready() is True


def test_set_card_manager_none(card_repository):
    """Setting manager to None clears it without marking ready."""
    card_repository.set_card_data_ready(True)
    card_repository.set_card_manager(None)

    assert card_repository.get_card_manager() is None
