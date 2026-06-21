"""Tests for CardRepository data access layer."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from repositories.card_repository import CardRepository, storage
from repositories.card_repository.builder import build_index
from repositories.card_repository.card_data_manager import CardDataManager

# A tiny but realistic AtomicCards ``data`` payload. Built through the real
# ``build_index`` -> on-disk index -> ``CardDataManager`` pipeline so tests
# assert against real ``CardEntry`` values instead of mocked interactions.
_ATOMIC_PAYLOAD = {
    "Lightning Bolt": [
        {
            "name": "Lightning Bolt",
            "manaCost": "{R}",
            "manaValue": 1,
            "type": "Instant",
            "text": "Lightning Bolt deals 3 damage to any target.",
            "colors": ["R"],
            "colorIdentity": ["R"],
            "legalities": {"modern": "Legal"},
        }
    ],
    "Lightning Strike": [
        {
            "name": "Lightning Strike",
            "manaCost": "{1}{R}",
            "manaValue": 2,
            "type": "Instant",
            "text": "Lightning Strike deals 3 damage to any target.",
            "colors": ["R"],
            "colorIdentity": ["R"],
            "legalities": {"standard": "Legal"},
        }
    ],
    "Island": [
        {
            "name": "Island",
            "type": "Basic Land — Island",
            "text": "({T}: Add {U}.)",
            "colors": [],
            "colorIdentity": ["U"],
            "legalities": {"modern": "Legal"},
        }
    ],
}


@pytest.fixture
def card_manager(tmp_path):
    """A real, loaded ``CardDataManager`` backed by a small on-disk index.

    Exercises the genuine ``build_index`` -> ``write_index`` -> ``_load_index``
    pipeline so callers see real ``CardEntry`` records, not test doubles.
    """
    manager = CardDataManager(tmp_path)
    storage.write_index(manager.index_path, build_index(_ATOMIC_PAYLOAD))
    manager._load_index()
    return manager


@pytest.fixture
def card_repository(card_manager):
    """CardRepository backed by the real card manager."""
    return CardRepository(card_data_manager=card_manager)


# ============= Card Metadata Tests =============


def test_get_card_metadata_success(card_repository):
    """Test getting card metadata returns the real card record."""
    metadata = card_repository.get_card_metadata("Lightning Bolt")

    assert metadata is not None
    assert metadata["name"] == "Lightning Bolt"
    assert metadata["mana_cost"] == "{R}"
    assert metadata["mana_value"] == 1


def test_get_card_metadata_case_insensitive(card_repository):
    """Lookup is case-insensitive (manager indexes by lowercased name)."""
    metadata = card_repository.get_card_metadata("lightning bolt")

    assert metadata is not None
    assert metadata["name"] == "Lightning Bolt"


def test_get_card_metadata_missing_card(card_repository):
    """An unknown card name yields ``None`` (manager returns no record)."""
    assert card_repository.get_card_metadata("Black Lotus") is None


def test_get_card_metadata_runtime_error_when_not_loaded():
    """Test getting metadata when card data is not loaded returns None.

    The unloaded manager raises ``RuntimeError`` from ``get_card``; the
    repository swallows it and returns ``None``.
    """
    repo = CardRepository(card_data_manager=CardDataManager())

    assert repo.get_card_metadata("Lightning Bolt") is None


def test_get_card_metadata_generic_exception_returns_none(card_repository):
    """A non-RuntimeError from lookup is also swallowed and returns None.

    A ``None`` name makes the loaded manager raise ``AttributeError`` (from
    ``name.lower()``), exercising the generic ``except Exception`` branch.
    """
    assert card_repository.get_card_metadata(None) is None


# ============= Card Search Tests =============


def test_search_cards_success(card_repository):
    """Test searching cards matches against name/type/text substrings."""
    results = card_repository.search_cards(query="Lightning")

    names = sorted(card["name"] for card in results)
    assert names == ["Lightning Bolt", "Lightning Strike"]


def test_search_cards_color_filter(card_repository):
    """``colors`` maps to ``color_identity`` and filters real records.

    A blue color filter must drop the red instants and keep only the land,
    proving colors hit ``color_identity`` (not the type line) and are not
    dropped on the way to the manager.
    """
    results = card_repository.search_cards(colors=["U"])

    assert [card["name"] for card in results] == ["Island"]


def test_search_cards_colors_not_swapped(card_repository):
    """A red color filter keeps both red instants and drops the blue land."""
    results = card_repository.search_cards(colors=["R"])

    assert sorted(card["name"] for card in results) == ["Lightning Bolt", "Lightning Strike"]


def test_search_cards_query_none_returns_all(card_repository):
    """A None query is forwarded as '' so every card matches."""
    results = card_repository.search_cards(query=None)

    assert sorted(card["name"] for card in results) == [
        "Island",
        "Lightning Bolt",
        "Lightning Strike",
    ]


def test_search_cards_types_list_currently_yields_nothing(card_repository):
    """Pin current behavior: a ``types`` *list* is forwarded but never matches.

    The repository forwards ``types`` straight through as the manager's
    ``type_filter`` argument, but the manager treats ``type_filter`` as a
    *string* (``(type_filter or "").strip().lower()``). A list therefore raises
    ``AttributeError`` inside the manager, which the generic ``except`` swallows,
    so passing ``types`` as a list returns ``[]`` rather than the matching
    instants. This documents the latent list/str mismatch; if the plumbing is
    ever fixed to accept a list, update this expectation.
    """
    assert card_repository.search_cards(types=["Instant"]) == []


def test_search_cards_types_string_filters_by_type_line(card_repository):
    """A *string* ``types`` reaches the manager's type-line substring filter.

    Passing the type as a bare string (what the manager actually expects) keeps
    only the instants and drops the land, proving the type filter is wired to
    the manager and applied against the type line.
    """
    results = card_repository.search_cards(types="Instant")

    assert sorted(card["name"] for card in results) == [
        "Lightning Bolt",
        "Lightning Strike",
    ]


def test_search_cards_colors_and_types_combine(card_repository):
    """Colors and a string type filter intersect (AND), not union."""
    both = card_repository.search_cards(colors=["R"], types="Instant")
    assert sorted(card["name"] for card in both) == [
        "Lightning Bolt",
        "Lightning Strike",
    ]

    # The land is blue, so a red color filter excludes it even though its type
    # line would otherwise match a "Land" type filter.
    none = card_repository.search_cards(colors=["R"], types="Land")
    assert none == []


def test_search_cards_mana_value_param_is_currently_ignored(card_repository):
    """Pin current behavior: ``mana_value`` is accepted but never applied.

    ``search_cards`` declares a ``mana_value`` parameter that it does not
    forward to the manager (which has no mana-value filter), so passing it has
    no effect. This test documents that latent dead parameter; if mana-value
    filtering is ever wired up, update this expectation.
    """
    unfiltered = card_repository.search_cards(query="Lightning")
    filtered = card_repository.search_cards(query="Lightning", mana_value=1)

    assert [c["name"] for c in filtered] == [c["name"] for c in unfiltered]
    assert sorted(c["name"] for c in filtered) == ["Lightning Bolt", "Lightning Strike"]


def test_search_cards_runtime_error_when_not_loaded():
    """Searching an unloaded manager returns [] (RuntimeError swallowed)."""
    repo = CardRepository(card_data_manager=CardDataManager())

    assert repo.search_cards(query="Lightning") == []


def test_search_cards_generic_exception_returns_empty(card_repository):
    """A non-RuntimeError during search is swallowed and returns [].

    A non-iterable ``colors`` makes the loaded manager raise ``TypeError``,
    exercising the generic ``except Exception`` branch.
    """
    assert card_repository.search_cards(query="Lightning", colors=5) == []


# ============= Card Data Loading Tests =============


def test_is_card_data_loaded_true(card_repository):
    """Test checking if card data is loaded."""
    assert card_repository.is_card_data_loaded() is True


def test_is_card_data_loaded_false():
    """Test checking when card data is not loaded."""
    repo = CardRepository(card_data_manager=CardDataManager())

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


def test_load_collection_from_file_omits_id_when_absent(card_repository, tmp_path):
    """An entry without an 'id' key produces a normalized dict without 'id'.

    Covers the absent-branch of the ``if "id" in entry`` guard: ``id`` is only
    copied through when present, so a bare entry must not gain a null ``id``.
    """
    collection_data = [{"name": "Lightning Bolt", "quantity": 4}]
    filepath = tmp_path / "collection.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    cards = card_repository.load_collection_from_file(filepath)

    assert len(cards) == 1
    assert "id" not in cards[0]


def test_get_collection_cache_path(card_repository):
    """``get_collection_cache_path`` points at collection.json under CACHE_DIR."""
    from utils.constants import CACHE_DIR

    path = card_repository.get_collection_cache_path()

    assert path == CACHE_DIR / "collection.json"
    assert path.name == "collection.json"


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


def test_get_card_manager(card_repository, card_manager):
    """Test getting card manager."""
    manager = card_repository.get_card_manager()
    assert manager is card_manager


def test_set_card_manager(card_repository):
    """Test setting card manager."""
    new_manager = SimpleNamespace()
    card_repository.set_card_manager(new_manager)

    assert card_repository.get_card_manager() is new_manager
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


def test_ensure_card_data_loaded_uses_cached_manager(card_repository, card_manager):
    """Test cached fast-path returns existing manager without reloading."""
    with patch("repositories.card_repository.state.load_card_manager") as mock_load:
        result = card_repository.ensure_card_data_loaded()

    assert result is card_manager
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


def test_ensure_card_data_loaded_loads_when_manager_present_but_not_loaded():
    """A present-but-unloaded manager falls through to ``load_card_manager``.

    The cached fast-path is gated on ``is_loaded``; when a manager exists but
    has not finished loading, ``ensure_card_data_loaded`` must reload rather
    than hand back the stale, empty manager.
    """
    repo = CardRepository(card_data_manager=SimpleNamespace(is_loaded=False))
    loaded = SimpleNamespace(is_loaded=True)

    with patch(
        "repositories.card_repository.state.load_card_manager", return_value=loaded
    ) as mock_load:
        result = repo.ensure_card_data_loaded()

    assert result is loaded
    mock_load.assert_called_once_with()
    assert repo.get_card_manager() is loaded
    assert repo.is_card_data_ready() is True


def test_ensure_card_data_loaded_force_reloads(card_repository):
    """Test force=True reloads even when a loaded manager is present."""
    reloaded = SimpleNamespace(is_loaded=True)

    with patch(
        "repositories.card_repository.state.load_card_manager", return_value=reloaded
    ) as mock_load:
        result = card_repository.ensure_card_data_loaded(force=True)

    assert result is reloaded
    mock_load.assert_called_once_with()
    assert card_repository.get_card_manager() is reloaded
