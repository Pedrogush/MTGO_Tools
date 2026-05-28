"""Tests for the msgpack-backed atomic-cards index storage layer."""

from __future__ import annotations

from pathlib import Path

import msgspec.json

from repositories.card_repository import storage
from repositories.card_repository.schemas import CardEntry


def _sample_index() -> dict:
    entry = CardEntry(
        name="Opt",
        name_lower="opt",
        aliases=[],
        colors=["U"],
        color_identity=["U"],
        legalities={"modern": "Legal"},
        mana_cost="{U}",
    )
    return {"cards": [entry], "cards_by_name": {"opt": entry}}


def test_resolve_paths_uses_msgpack_extension(tmp_path: Path) -> None:
    _, index_path, meta_path = storage.resolve_paths(tmp_path)
    assert index_path.name == "atomic_cards_index_v2.msgpack"
    assert meta_path.name == "atomic_cards_meta.json"


def test_write_then_load_index_round_trip(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    storage.write_index(index_path, _sample_index())

    loaded = storage.load_index(index_path)
    assert loaded.cards[0].name == "Opt"
    assert loaded.cards_by_name["opt"].mana_cost == "{U}"


def test_load_index_missing_raises(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    try:
        storage.load_index(index_path)
    except RuntimeError as exc:
        assert "missing or invalid" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("expected RuntimeError for missing index")


def test_migrate_legacy_index_converts_json_to_msgpack(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    legacy_path = storage.legacy_index_path(tmp_path)
    legacy_path.write_bytes(msgspec.json.encode(_sample_index()))

    assert storage.migrate_legacy_index(index_path, legacy_path) is True
    # Legacy JSON removed, msgpack written, and decodable.
    assert index_path.exists()
    assert not legacy_path.exists()
    assert storage.load_index(index_path).cards[0].name == "Opt"


def test_migrate_legacy_index_noop_when_index_present(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    storage.write_index(index_path, _sample_index())
    legacy_path = storage.legacy_index_path(tmp_path)
    legacy_path.write_bytes(msgspec.json.encode(_sample_index()))

    # An existing msgpack index wins; the legacy file is left untouched.
    assert storage.migrate_legacy_index(index_path, legacy_path) is False
    assert legacy_path.exists()


def test_migrate_legacy_index_noop_when_no_legacy(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    legacy_path = storage.legacy_index_path(tmp_path)
    assert storage.migrate_legacy_index(index_path, legacy_path) is False


def test_migrate_legacy_index_leaves_corrupt_legacy(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    legacy_path = storage.legacy_index_path(tmp_path)
    legacy_path.write_bytes(b"not valid json")

    assert storage.migrate_legacy_index(index_path, legacy_path) is False
    assert not index_path.exists()
    assert legacy_path.exists()
