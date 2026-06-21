"""Tests for the msgpack-backed atomic-cards index storage layer."""

from __future__ import annotations

from pathlib import Path

import msgspec.json
import msgspec.msgpack

from repositories.card_repository import storage
from repositories.card_repository.schemas import CardEntry


def _card(name: str, color: str) -> CardEntry:
    return CardEntry(
        name=name,
        name_lower=name.lower(),
        aliases=[],
        colors=[color],
        color_identity=[color],
        legalities={"modern": "Legal"},
        mana_cost=f"{{{color}}}",
    )


def _sample_index() -> dict:
    return {"cards": [_card("Opt", "U")], "cards_by_name": {"opt": 0}}


def test_resolve_paths_uses_msgpack_extension(tmp_path: Path) -> None:
    # The first element is the (created) data dir; the index is binary msgpack.
    base, index_path, meta_path = storage.resolve_paths(tmp_path / "data")
    assert base == tmp_path / "data"
    assert base.is_dir()  # resolve_paths must create the directory.
    assert index_path.name == "atomic_cards_index_v3.msgpack"
    assert meta_path.name == "atomic_cards_meta.json"


def test_write_then_load_index_round_trip(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    # Two cards with an alias mapping to index 1 so non-zero index resolution
    # is exercised (a bug that returned ``cards[0]`` would pass otherwise).
    index = {
        "cards": [_card("Opt", "U"), _card("Shock", "R")],
        "cards_by_name": {"opt": 0, "shock": 1},
    }
    storage.write_index(index_path, index)

    loaded = storage.load_index(index_path)
    assert loaded.cards[0].name == "Opt"
    # ``cards_by_name`` maps an alias to the index of its record in ``cards``.
    assert loaded.cards[loaded.cards_by_name["opt"]].mana_cost == "{U}"
    assert loaded.cards[loaded.cards_by_name["shock"]].name == "Shock"
    assert loaded.cards[loaded.cards_by_name["shock"]].mana_cost == "{R}"


def test_load_index_missing_raises(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    try:
        storage.load_index(index_path)
    except RuntimeError as exc:
        assert "missing or invalid" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("expected RuntimeError for missing index")


def test_load_index_corrupt_raises_with_detail(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    # A present-but-garbage file must hit the decode-error branch (not the
    # missing-file guard) and wrap the underlying msgspec.DecodeError detail.
    index_path.write_bytes(b"\xff\xff not msgpack")
    try:
        storage.load_index(index_path)
    except RuntimeError as exc:
        message = str(exc)
        assert "missing or invalid" in message
        # The bare missing-file guard has no trailing detail; the decode-error
        # branch appends ``: <exc>`` so a non-empty suffix proves we took it.
        assert message != "Card data index missing or invalid"
        assert message.startswith("Card data index missing or invalid: ")
    else:  # pragma: no cover - failure path
        raise AssertionError("expected RuntimeError for corrupt index")


def test_migrate_legacy_index_converts_json_to_msgpack(tmp_path: Path) -> None:
    _, index_path, _ = storage.resolve_paths(tmp_path)
    legacy_path = storage.legacy_index_path(tmp_path)
    legacy_path.write_bytes(msgspec.json.encode(_sample_index()))

    assert storage.migrate_legacy_index(index_path, legacy_path) is True
    # Legacy JSON removed, msgpack written, and decodable.
    assert index_path.exists()
    assert not legacy_path.exists()
    # Confirm the migrated payload is genuine msgpack (not coincidentally
    # JSON-readable): decode it raw before the typed load_index round-trip.
    raw = msgspec.msgpack.decode(index_path.read_bytes())
    assert raw["cards_by_name"]["opt"] == 0
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


def test_load_meta_missing_returns_none(tmp_path: Path) -> None:
    _, _, meta_path = storage.resolve_paths(tmp_path)
    assert storage.load_meta(meta_path) is None


def test_write_then_load_meta_round_trip(tmp_path: Path) -> None:
    _, _, meta_path = storage.resolve_paths(tmp_path)
    # Includes a non-ASCII value to confirm a clean UTF-8 round-trip.
    # (``write_meta`` forwards ``ensure_ascii=False``, but ``atomic_write_json``
    # ignores it: msgspec always emits UTF-8 without escaping, so the byte never
    # depends on that flag.)
    meta = {"etag": "abc123", "source": "Æther Vial", "count": 34000}
    storage.write_meta(meta_path, meta)
    assert storage.load_meta(meta_path) == meta


def test_load_meta_invalid_json_returns_none(tmp_path: Path) -> None:
    _, _, meta_path = storage.resolve_paths(tmp_path)
    meta_path.write_text("{not valid json", encoding="utf-8")
    assert storage.load_meta(meta_path) is None
