"""Integration tests for CollectionService against a real CardRepository.

These exercise the service<->real-repo collaboration end to end. The
``CardRepository.load_collection_from_file`` parsing rules are covered
exhaustively in ``test_card_repository.py`` and are not re-tested here.
"""

from __future__ import annotations

import json
from pathlib import Path

from repositories.card_repository import CardRepository
from services.collection_service import CollectionService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_collection_export.json"


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
    # Spell Pierce is stored with a numeric-string quantity in the fixture; the
    # real parser coerces "2" -> 2 (string-quantity coercion).
    assert service.get_owned_count("Spell Pierce") == 2
    # Lookups are case-insensitive regardless of caller casing.
    assert service.get_owned_count("lightning bolt") == 5


def test_collection_service_short_circuits_when_already_loaded(tmp_path):
    repo = CardRepository()
    service = CollectionService(card_repository=repo)

    temp_file = tmp_path / "collection.json"

    def write(quantity: int) -> None:
        temp_file.write_text(
            json.dumps([{"name": "Island", "quantity": quantity}]), encoding="utf-8"
        )

    write(7)
    assert service.load_collection(temp_file)
    assert service.get_owned_count("Island") == 7

    # Mutate the file on disk, then load again without force: the cached
    # inventory is reused, so the new quantity is *not* observed.
    write(20)
    assert service.load_collection(temp_file)
    assert service.get_owned_count("Island") == 7

    # force=True re-reads the file and the new quantity becomes visible.
    assert service.load_collection(temp_file, force=True)
    assert service.get_owned_count("Island") == 20


def test_collection_service_returns_false_on_bad_filepath():
    repo = CardRepository()
    service = CollectionService(card_repository=repo)

    # Passing a non-Path object makes the real ``filepath.exists()`` probe raise
    # inside ``load_collection``; the except branch must swallow it and report
    # failure rather than propagate. No internal method is replaced.
    assert service.load_collection("not-a-path-object") is False  # type: ignore[arg-type]
