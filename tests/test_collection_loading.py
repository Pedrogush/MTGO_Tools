from __future__ import annotations

import json
from pathlib import Path

from repositories.card_repository import CardRepository
from services.collection_service import CollectionService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_collection_export.json"


def test_card_repository_reads_collection_export():
    repo = CardRepository()

    cards = repo.load_collection_from_file(FIXTURE_PATH)

    assert len(cards) == 4

    names = [card["name"] for card in cards]
    assert names == ["Lightning Bolt", "Island", "Lightning Bolt", "Spell Pierce"]
    assert cards[-1]["quantity"] == 2
    # The normalized `id` field is preserved from the export entries.
    assert cards[0]["id"] == 1001


def test_card_repository_handles_flat_list_format(tmp_path):
    repo = CardRepository()
    list_path = tmp_path / "collection_list.json"
    payload = [
        {"name": "Opt", "quantity": 3},
        {"name": "Consider", "quantity": "2"},
    ]
    list_path.write_text(json.dumps(payload), encoding="utf-8")

    cards = repo.load_collection_from_file(list_path)

    assert len(cards) == 2
    assert [card["name"] for card in cards] == ["Opt", "Consider"]
    assert cards[1]["quantity"] == 2
    # Entries without an `id` key must not gain a spurious one.
    assert "id" not in cards[0]


def test_card_repository_returns_empty_for_missing_file(tmp_path):
    repo = CardRepository()

    cards = repo.load_collection_from_file(tmp_path / "does_not_exist.json")

    assert cards == []


def test_card_repository_returns_empty_for_invalid_json(tmp_path):
    repo = CardRepository()
    bad_path = tmp_path / "broken.json"
    bad_path.write_bytes(b"{not valid json")

    cards = repo.load_collection_from_file(bad_path)

    assert cards == []


def test_card_repository_returns_empty_for_no_entries(tmp_path):
    repo = CardRepository()

    empty_dict_path = tmp_path / "empty_collection.json"
    empty_dict_path.write_text(
        json.dumps({"collection": {"name": "Collection", "items": []}}),
        encoding="utf-8",
    )
    missing_list_path = tmp_path / "missing_list.json"
    missing_list_path.write_text(json.dumps({"mode": "Collection"}), encoding="utf-8")

    assert repo.load_collection_from_file(empty_dict_path) == []
    assert repo.load_collection_from_file(missing_list_path) == []


def test_card_repository_coerces_and_skips_quantities(tmp_path):
    repo = CardRepository()
    list_path = tmp_path / "quantities.json"
    payload = [
        {"name": "Float Down", "quantity": "2.5"},  # float-string -> int(float(...)) == 2
        {"name": "Float Round", "quantity": "3.0"},  # float-string -> 3
        {"name": "Bad String", "quantity": "abc"},  # non-numeric -> skipped
        {"name": "Null Qty", "quantity": None},  # None -> skipped
        {"name": "Negative", "quantity": -1},  # negative -> skipped
        {"name": "   ", "quantity": 5},  # blank name -> skipped
        {"name": "", "quantity": 5},  # empty name -> skipped
    ]
    list_path.write_text(json.dumps(payload), encoding="utf-8")

    cards = repo.load_collection_from_file(list_path)

    assert [card["name"] for card in cards] == ["Float Down", "Float Round"]
    assert [card["quantity"] for card in cards] == [2, 3]


def test_collection_service_loads_inventory_from_export(tmp_path):
    repo = CardRepository()
    service = CollectionService(card_repository=repo)

    # Copy to a temp location to emulate a freshly downloaded export
    temp_file = tmp_path / "collection_full_trade_20240101.json"
    temp_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    assert service.load_collection(temp_file)

    # Inventory keys are normalized to lowercase across all load paths so
    # that ownership lookups are case-insensitive (issue #469).
    assert service.get_owned_count("Lightning Bolt") == 5  # 4 + 1 duplicate entry
    assert service.get_owned_count("Island") == 12
    assert service.get_owned_count("Spell Pierce") == 2
    # Lookups are case-insensitive regardless of caller casing.
    assert service.get_owned_count("lightning bolt") == 5


def test_collection_service_load_missing_file_returns_empty(tmp_path):
    repo = CardRepository()
    service = CollectionService(card_repository=repo)

    assert service.load_collection(tmp_path / "nope.json")

    assert service.get_inventory() == {}
    assert service.is_loaded()


def test_collection_service_short_circuits_when_already_loaded(tmp_path):
    repo = CardRepository()
    service = CollectionService(card_repository=repo)

    temp_file = tmp_path / "collection.json"
    temp_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    calls = {"count": 0}
    original = repo.load_collection_from_file

    def counting_load(path):
        calls["count"] += 1
        return original(path)

    repo.load_collection_from_file = counting_load  # type: ignore[method-assign]

    assert service.load_collection(temp_file)
    assert calls["count"] == 1

    # A second load without force must not re-read the file.
    assert service.load_collection(temp_file)
    assert calls["count"] == 1

    # force=True triggers a fresh read.
    assert service.load_collection(temp_file, force=True)
    assert calls["count"] == 2


def test_collection_service_returns_false_on_read_error(tmp_path):
    repo = CardRepository()
    service = CollectionService(card_repository=repo)

    temp_file = tmp_path / "collection.json"
    temp_file.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    def boom(path):
        raise RuntimeError("disk on fire")

    repo.load_collection_from_file = boom  # type: ignore[method-assign]

    assert service.load_collection(temp_file) is False
