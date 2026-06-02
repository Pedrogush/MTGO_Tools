"""Integration tests for CollectionService against a real CardRepository.

These exercise the service<->real-repo collaboration end to end. The
``CardRepository.load_collection_from_file`` parsing rules are covered
exhaustively in ``test_card_repository.py`` and are not re-tested here.
"""

from __future__ import annotations

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
    assert service.get_owned_count("Spell Pierce") == 2
    # Lookups are case-insensitive regardless of caller casing.
    assert service.get_owned_count("lightning bolt") == 5


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
