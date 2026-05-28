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
