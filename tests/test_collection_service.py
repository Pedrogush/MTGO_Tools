"""Tests for CollectionService business logic.

These tests wire a *real* ``CardRepository`` against the service so the real
collection-file parser (``load_collection_from_file`` — msgspec decode,
multi-shape ``_extract_cards``, OSError/DecodeError handling) and the real
metadata aggregation path are exercised. Only the one seam we don't own — the
``CardDataManager`` in-memory MTGJSON index, which would otherwise load bulk
card data off disk/network — is faked. See ``tests/README.md`` §1–§2.
"""

import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from repositories.card_repository import CardRepository
from services.collection_service import CollectionService
from services.collection_service.cache import CollectionStatus
from services.collection_service.parsing import build_inventory


class _FakeCardDataManager:
    """Stand-in for the MTGJSON-backed card index (the seam we don't own).

    Holds a small in-memory ``{name: metadata}`` map (looked up by exact name,
    matching the real ``CardDataManager.get_card``) so
    ``CardRepository.get_card_metadata`` runs for real against deterministic data
    instead of a network/disk load. Tests mutate ``cards`` directly.
    """

    def __init__(self, cards: dict[str, dict] | None = None):
        self.cards = cards or {}
        self.is_loaded = True

    def get_card(self, name: str) -> dict | None:
        return self.cards.get(name)


@pytest.fixture
def card_data():
    """Default fake card metadata used by the statistics tests."""
    return _FakeCardDataManager(
        {
            "Lightning Bolt": {"rarity": "common"},
            "Island": {"rarity": "basic"},
            "Mountain": {"rarity": "basic"},
        }
    )


@pytest.fixture
def card_repo(tmp_path, card_data):
    """Real CardRepository pointed at ``tmp_path`` with a faked data manager.

    Overriding ``get_collection_cache_path`` is path relocation of real file
    I/O (README §3), not a mock of internal logic: the real
    ``load_collection_from_file`` parser still runs against whatever is written
    to the returned path.
    """
    repo = CardRepository(card_data_manager=card_data)
    repo.get_collection_cache_path = lambda: tmp_path / "collection.json"  # type: ignore[method-assign]
    return repo


@pytest.fixture
def collection_service(card_repo):
    """CollectionService backed by a real CardRepository."""
    return CollectionService(card_repository=card_repo)


# ============= Collection Loading Tests =============


def test_load_collection_from_file(collection_service, tmp_path):
    """Loading a real collection file runs the msgspec parser end to end."""
    filepath = tmp_path / "collection.json"
    filepath.write_text(
        json.dumps(
            [
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Island", "quantity": 20},
            ]
        ),
        encoding="utf-8",
    )

    success = collection_service.load_collection(filepath)

    assert success is True
    assert collection_service.is_loaded() is True
    assert collection_service.get_collection_size() == 2
    assert collection_service.get_owned_count("Lightning Bolt") == 4
    assert collection_service.get_owned_count("Island") == 20


def test_load_collection_from_nested_cards_payload(collection_service, tmp_path):
    """The real parser unwraps the ``{"cards": [...]}`` MTGO shape.

    Drives ``_extract_cards`` against a non-list wrapper — a branch the old
    fully-mocked repo could never reach.
    """
    filepath = tmp_path / "collection.json"
    filepath.write_text(
        json.dumps({"cards": [{"name": "Counterspell", "quantity": "3"}]}),
        encoding="utf-8",
    )

    success = collection_service.load_collection(filepath)

    assert success is True
    # Numeric-string quantity is coerced to int by the real parser.
    assert collection_service.get_owned_count("Counterspell") == 3


def test_load_collection_malformed_json_yields_empty(collection_service, tmp_path):
    """A corrupt collection file is swallowed by the parser as an empty load."""
    filepath = tmp_path / "collection.json"
    filepath.write_text("{not valid json", encoding="utf-8")

    success = collection_service.load_collection(filepath)

    assert success is True
    assert collection_service.get_collection_size() == 0


def test_load_collection_nonexistent_file(collection_service, tmp_path):
    """Test loading collection from nonexistent file."""
    nonexistent = tmp_path / "nonexistent_collection.json"
    success = collection_service.load_collection(nonexistent)

    assert success is True
    assert collection_service.is_loaded() is True
    assert collection_service.get_collection_size() == 0


def test_load_collection_force_reload(collection_service, tmp_path):
    """Test force reloading collection re-reads the file on disk."""
    filepath = tmp_path / "collection.json"

    def write(quantity: int) -> None:
        filepath.write_text(
            json.dumps([{"name": "Island", "quantity": quantity}]), encoding="utf-8"
        )

    # First load
    write(5)
    collection_service.load_collection(filepath)
    assert collection_service.get_owned_count("Island") == 5

    # Change the file on disk.
    write(10)

    # Load without force - should not re-read the file.
    collection_service.load_collection(filepath)
    assert collection_service.get_owned_count("Island") == 5

    # Load with force - should re-read and pick up the new quantity.
    collection_service.load_collection(filepath, force=True)
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


def test_load_from_card_list_non_iterable_raises(collection_service):
    """A non-iterable cards arg is wrapped as ValueError (cache.py:141-143).

    ``build_inventory`` iterates ``cards``; an int raises TypeError there, which
    ``load_from_card_list`` translates into a descriptive ValueError.
    """
    with pytest.raises(ValueError, match="Failed to parse card list"):
        collection_service.load_from_card_list(42)  # type: ignore[arg-type]


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


def test_get_owned_count_mixed_case_lookup(collection_service):
    """Ownership lookups must be case-insensitive regardless of inventory casing.

    Regression test for issue #469: cached collections with title-cased keys
    used to under-report ownership when callers queried with a different casing.
    """
    # Inventory stored with title-case keys (legacy cached file shape).
    collection_service.set_inventory({"Lightning Bolt": 4, "Force of Will": 1})

    # Queries in any casing should resolve to the same count.
    assert collection_service.get_owned_count("Lightning Bolt") == 4
    assert collection_service.get_owned_count("lightning bolt") == 4
    assert collection_service.get_owned_count("LIGHTNING BOLT") == 4
    assert collection_service.get_owned_count("Force of Will") == 1
    assert collection_service.get_owned_count("force of will") == 1

    # Inventory stored with lowercase keys (canonical load-path shape).
    collection_service.set_inventory({"lightning bolt": 4})
    assert collection_service.get_owned_count("Lightning Bolt") == 4
    assert collection_service.get_owned_count("LIGHTNING BOLT") == 4
    assert collection_service.get_owned_count("lightning bolt") == 4


def test_load_collection_normalizes_mixed_case_keys(collection_service, tmp_path):
    """load_collection must normalize keys so later lookups are case-insensitive (#469)."""
    filepath = tmp_path / "collection.json"
    filepath.write_text(
        json.dumps(
            [
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Force of Will", "quantity": 1},
            ]
        ),
        encoding="utf-8",
    )

    success = collection_service.load_collection(filepath)

    assert success is True
    # Any casing should resolve to the loaded counts.
    assert collection_service.get_owned_count("Lightning Bolt") == 4
    assert collection_service.get_owned_count("lightning bolt") == 4
    assert collection_service.get_owned_count("LIGHTNING BOLT") == 4
    assert collection_service.get_owned_count("force of will") == 1


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

    # The bare "Sideboard" header line splits to a single token and is skipped,
    # leaving the two real card lines.
    assert analysis["total_unique"] == 2
    assert analysis["fully_owned"] == 1  # Lightning Bolt
    assert analysis["partially_owned"] == 1  # Dismember (3/4)


def test_analyze_deck_ownership_strips_sideboard_prefix(collection_service):
    """A card name literally prefixed with 'Sideboard ' is stripped (deck_analysis.py:34-35)."""
    collection_service.set_inventory({"Dismember": 4})

    deck_text = "4 Sideboard Dismember"

    analysis = collection_service.analyze_deck_ownership(deck_text)

    # The "Sideboard " prefix is stripped so the requirement keys on "Dismember"
    # and is fully owned (4/4) rather than reported as a missing raw name.
    assert analysis["total_unique"] == 1
    assert analysis["fully_owned"] == 1
    assert analysis["missing_cards"] == []
    # No requirement should retain the raw "Sideboard Dismember" name.
    missing = collection_service.get_missing_cards_list(deck_text)
    assert missing == []


def test_get_missing_cards_list(collection_service):
    """Test getting list of missing cards."""
    collection_service.set_inventory({"Lightning Bolt": 2})

    deck_text = """4 Lightning Bolt
4 Island"""

    missing = collection_service.get_missing_cards_list(deck_text)

    assert len(missing) == 2
    assert ("Lightning Bolt", 2) in missing
    assert ("Island", 4) in missing


def test_analyze_deck_ownership_empty_deck(collection_service):
    """An empty deck text yields the zero-requirement branch (deck_analysis.py:58-59)."""
    collection_service.set_inventory({"Lightning Bolt": 4})

    analysis = collection_service.analyze_deck_ownership("")

    assert analysis["total_unique"] == 0
    assert analysis["fully_owned"] == 0
    assert analysis["partially_owned"] == 0
    assert analysis["not_owned"] == 0
    assert analysis["missing_cards"] == []
    # No requirements -> the percentage falls through to the 0.0 default.
    assert analysis["ownership_percentage"] == 0.0


def test_analyze_deck_ownership_decimal_count_and_junk_lines(collection_service):
    """Decimal counts are floored via int(float(...)) and junk lines are skipped.

    Exercises the ``int(float(parts[0]))`` parse (deck_analysis.py:31) and the
    ``except (ValueError, IndexError)`` skip path (deck_analysis.py:38) together.
    """
    collection_service.set_inventory({"Lightning Bolt": 4})

    deck_text = """4.0 Lightning Bolt
Mountain
not-a-count Island"""

    analysis = collection_service.analyze_deck_ownership(deck_text)

    # "4.0" -> 4 honored; the single-token "Mountain" line has no count and the
    # "not-a-count" line fails int(float(...)), so both are skipped.
    assert analysis["total_unique"] == 1
    assert analysis["fully_owned"] == 1
    assert analysis["missing_cards"] == []


# ============= Collection Statistics Tests =============


def test_get_collection_statistics(collection_service):
    """Stats flow through the real repo against the default fake card index."""
    collection_service.set_inventory({"Lightning Bolt": 4, "Island": 20, "Mountain": 10})

    stats = collection_service.get_collection_statistics()

    assert stats["loaded"] is True
    assert stats["unique_cards"] == 3
    assert stats["total_cards"] == 34
    assert stats["average_copies"] == pytest.approx(34 / 3)
    # Lightning Bolt (4, common) + Island (20, basic) + Mountain (10, basic).
    assert stats["rarity_distribution"] == {"common": 4, "basic": 30}


def test_get_collection_statistics_missing_metadata_skipped(collection_service, card_data):
    """Cards whose metadata is None are skipped from the rarity aggregation (stats.py if metadata)."""
    card_data.cards = {"Lightning Bolt": {"rarity": "common"}}
    collection_service.set_inventory({"Lightning Bolt": 4, "Unknown Card": 7})

    stats = collection_service.get_collection_statistics()

    # Unknown Card has no metadata -> excluded; only Lightning Bolt is counted.
    assert stats["rarity_distribution"] == {"common": 4}


def test_get_collection_statistics_default_unknown_rarity(collection_service, card_data):
    """Metadata lacking a 'rarity' key defaults to 'unknown' (stats.py:33)."""
    card_data.cards = {"Some Card": {"name": "Some Card"}}
    collection_service.set_inventory({"Some Card": 3})

    stats = collection_service.get_collection_statistics()

    assert stats["rarity_distribution"] == {"unknown": 3}


def test_get_collection_statistics_not_loaded(collection_service):
    """Test getting statistics when collection not loaded."""
    stats = collection_service.get_collection_statistics()

    assert stats["loaded"] is False
    assert "message" in stats


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


# ============= build_inventory Normalization Tests =============


def test_build_inventory_sums_duplicate_names():
    """Duplicate entries accumulate into a single normalized key (parsing.py:24)."""
    cards = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "lightning bolt", "quantity": 3},
    ]

    inventory = build_inventory(cards)

    assert inventory == {"lightning bolt": 7}


def test_build_inventory_skips_invalid_entries():
    """Non-dict entries and entries with missing/empty names are dropped."""
    cards = [
        "not a dict",
        {"quantity": 4},  # missing name
        {"name": "", "quantity": 4},  # empty name
        {"name": "Island", "quantity": 2},
    ]

    inventory = build_inventory(cards)

    assert inventory == {"island": 2}


def test_build_inventory_coerces_invalid_quantity():
    """A non-integer/None quantity coerces to 0 and is therefore dropped (parsing.py:17-22)."""
    cards = [
        {"name": "Island", "quantity": None},
        {"name": "Mountain", "quantity": "not a number"},
        {"name": "Forest", "quantity": "5"},  # numeric string is accepted
    ]

    inventory = build_inventory(cards)

    assert inventory == {"forest": 5}


def test_build_inventory_drops_zero_quantity():
    """Entries with quantity 0 are skipped (parsing.py:21)."""
    cards = [
        {"name": "Island", "quantity": 0},
        {"name": "Mountain", "quantity": 1},
    ]

    inventory = build_inventory(cards)

    assert inventory == {"mountain": 1}


def test_build_inventory_preserves_casing_when_not_normalizing():
    """normalize_names=False keeps the original key casing (parsing.py:23)."""
    cards = [{"name": "Lightning Bolt", "quantity": 4}]

    inventory = build_inventory(cards, normalize_names=False)

    assert inventory == {"Lightning Bolt": 4}


# ============= get_owned_status Tests =============


def test_get_owned_status_empty_inventory(collection_service):
    """Empty inventory returns the subdued 'no collection loaded' display state (ownership.py:48-49)."""
    collection_service.set_inventory({})

    status, color = collection_service.get_owned_status("Lightning Bolt", 4)

    assert status == "Owned —"
    assert color == (185, 191, 202)


def test_get_owned_status_populated_matches_format(collection_service):
    """With a populated inventory, get_owned_status delegates to format_owned_status."""
    from services.collection_service.ownership import format_owned_status

    collection_service.set_inventory({"Lightning Bolt": 2})

    assert collection_service.get_owned_status("Lightning Bolt", 4) == format_owned_status(2, 4)
    assert collection_service.get_owned_status("Lightning Bolt", 2) == format_owned_status(2, 2)


# ============= Cache Error / Formatter Tests =============


def test_load_from_cached_file_malformed(collection_service, tmp_path):
    """A corrupt cache file raises ValueError and clears the inventory (cache.py:106-109)."""
    collection_service.set_inventory({"Island": 5})

    filepath = tmp_path / "collection_full_trade_20240101.json"
    filepath.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to parse collection file"):
        collection_service.load_from_cached_file(tmp_path)

    assert collection_service.get_collection_size() == 0
    assert collection_service.is_loaded() is False


def test_load_cached_status_recent(collection_service, tmp_path):
    """A fresh cache file produces a 'recent' label (cache.py:111-123)."""
    collection_data = [
        {"name": "Lightning Bolt", "quantity": 4},
        {"name": "Island", "quantity": 10},
    ]
    filepath = tmp_path / "collection_full_trade_20240101.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    status = collection_service.load_cached_status(tmp_path)

    assert isinstance(status, CollectionStatus)
    assert status.card_count == 2
    assert status.filepath == filepath
    assert status.age_hours == 0
    assert "recent" in status.label
    assert filepath.name in status.label


def test_load_cached_status_hours_ago(collection_service, tmp_path):
    """A backdated cache file produces an 'Nh ago' label (cache.py:116).

    Age is computed as ``datetime.now() - file mtime`` with int-hour
    truncation (cache.py:93-94). A live-clock version of this test flaked on
    CI (2h vs 3h) at the hour boundary, so we pin ``now`` to a fixed point
    anchored on the file's *actual* recorded mtime. That keeps age_hours
    exact and deterministic regardless of runner wall-clock, filesystem mtime
    granularity, or DST artifacts.
    """
    collection_data = [{"name": "Island", "quantity": 10}]
    filepath = tmp_path / "collection_full_trade_20240101.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    # Backdate, then read back the actual stored mtime and place a fixed "now"
    # exactly 3h05m later so the truncated age is unambiguously 3.
    backdated = time.time() - 3 * 60 * 60
    os.utime(filepath, (backdated, backdated))
    actual_mtime = filepath.stat().st_mtime
    fixed_now = datetime.fromtimestamp(actual_mtime) + timedelta(hours=3, minutes=5)

    with patch("services.collection_service.cache.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        status = collection_service.load_cached_status(tmp_path)

    assert status.age_hours == 3
    assert "3h ago" in status.label


# ============= Exporter Error Tests =============


def test_export_to_file_invalid_data(collection_service, tmp_path):
    """Non-serializable card data is wrapped as ValueError (exporter.py:43-45)."""
    cards = [{"name": "Lightning Bolt", "quantity": {1, 2, 3}}]  # set is not JSON serializable

    with pytest.raises(ValueError, match="Invalid card data for export"):
        collection_service.export_to_file(cards, tmp_path)


# ============= BridgeRefreshMixin Tests =============


def test_refresh_from_bridge_recent_cache_short_circuits(collection_service, tmp_path):
    """A recent cached file with force=False returns False and reports success with no cards."""
    collection_data = [{"name": "Island", "quantity": 10}]
    filepath = tmp_path / "collection_full_trade_20240101.json"
    filepath.write_text(json.dumps(collection_data), encoding="utf-8")

    fetch = Mock()
    successes: list[tuple] = []
    errors: list[str] = []

    result = collection_service.refresh_from_bridge_async(
        tmp_path,
        force=False,
        on_success=lambda path, cards: successes.append((path, cards)),
        on_error=errors.append,
        cache_max_age_seconds=10_000,
        fetch_collection=fetch,
    )

    assert result is False
    fetch.assert_not_called()
    assert successes == [(filepath, [])]
    assert errors == []


def _run_refresh_and_wait(service, tmp_path, **kwargs):
    """Drive refresh_from_bridge_async and join the worker thread before asserting."""
    import threading

    before = set(threading.enumerate())
    result = service.refresh_from_bridge_async(tmp_path, **kwargs)
    for thread in set(threading.enumerate()) - before:
        thread.join(timeout=5)
    return result


def test_refresh_from_bridge_force_exports_and_succeeds(collection_service, tmp_path):
    """force=True bypasses the cache, exports fetched cards and calls on_success with them."""
    cards = [{"name": "Lightning Bolt", "quantity": 4}]
    fetch = Mock(return_value={"cards": cards})
    successes: list[tuple] = []
    errors: list[str] = []

    result = _run_refresh_and_wait(
        collection_service,
        tmp_path,
        force=True,
        on_success=lambda path, c: successes.append((path, c)),
        on_error=errors.append,
        fetch_collection=fetch,
    )

    assert result is True
    fetch.assert_called_once()
    assert errors == []
    assert len(successes) == 1
    saved_path, saved_cards = successes[0]
    assert saved_cards == cards
    assert saved_path.exists()
    assert "collection_full_trade_" in saved_path.name


def test_refresh_from_bridge_empty_collection_routes_to_error(collection_service, tmp_path):
    """An empty dict from the bridge routes to on_error."""
    fetch = Mock(return_value={})
    errors: list[str] = []

    _run_refresh_and_wait(
        collection_service,
        tmp_path,
        force=True,
        on_error=errors.append,
        fetch_collection=fetch,
    )

    assert errors == ["Bridge returned empty collection"]


def test_refresh_from_bridge_empty_cards_routes_to_error(collection_service, tmp_path):
    """A payload with no cards routes to on_error."""
    fetch = Mock(return_value={"cards": []})
    errors: list[str] = []

    _run_refresh_and_wait(
        collection_service,
        tmp_path,
        force=True,
        on_error=errors.append,
        fetch_collection=fetch,
    )

    assert errors == ["No cards in collection data"]


def test_refresh_from_bridge_missing_bridge_routes_to_error(collection_service, tmp_path):
    """A FileNotFoundError from fetch reports the bridge-missing message."""
    fetch = Mock(side_effect=FileNotFoundError("bridge.exe missing"))
    errors: list[str] = []

    _run_refresh_and_wait(
        collection_service,
        tmp_path,
        force=True,
        on_error=errors.append,
        fetch_collection=fetch,
    )

    assert errors == ["MTGO Bridge not found. Build the bridge executable."]


def test_refresh_from_bridge_default_fetch_seam(collection_service, tmp_path, monkeypatch):
    """Omitting fetch_collection resolves the default bridge seam (bridge_refresh.py:40-43).

    Monkeypatches ``mtgo_bridge_service.get_collection_snapshot`` so the real
    default-binding branch runs without launching the bridge.
    """
    import services.mtgo_bridge_service as mtgo_bridge

    cards = [{"name": "Island", "quantity": 10}]
    fetch = Mock(return_value={"cards": cards})
    monkeypatch.setattr(mtgo_bridge, "get_collection_snapshot", fetch)

    successes: list[tuple] = []
    errors: list[str] = []

    result = _run_refresh_and_wait(
        collection_service,
        tmp_path,
        force=True,
        on_success=lambda path, c: successes.append((path, c)),
        on_error=errors.append,
    )

    assert result is True
    fetch.assert_called_once()
    assert errors == []
    assert len(successes) == 1
    assert successes[0][1] == cards


def test_refresh_from_bridge_generic_failure_routes_to_error(collection_service, tmp_path):
    """A generic fetch failure reports the exception text via on_error."""
    fetch = Mock(side_effect=RuntimeError("network down"))
    errors: list[str] = []

    _run_refresh_and_wait(
        collection_service,
        tmp_path,
        force=True,
        on_error=errors.append,
        fetch_collection=fetch,
    )

    assert errors == ["network down"]
