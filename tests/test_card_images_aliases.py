"""Tests for card image alias handling and printing index generation."""

from __future__ import annotations

import json

import pytest

from services import image_service as card_images
from services.image_service import printing_index as printing_index_module
from services.image_service import schemas as card_images_schemas


def test_ensure_printing_index_cache_includes_face_aliases(tmp_path, monkeypatch):
    """Double-faced cards should expose each face as a lookup key."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    printings_path = cache_dir / "printings.json"
    payload = [
        {
            "name": "Delver of Secrets // Insectile Aberration",
            "id": "uuid-delver",
            "set": "isd",
            "set_name": "Innistrad",
            "collector_number": "51",
            "released_at": "2011-09-30",
            "card_faces": [
                {"name": "Delver of Secrets"},
                {"name": "Insectile Aberration"},
            ],
        }
    ]
    bulk_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(card_images_schemas, "PRINTING_INDEX_CACHE", printings_path, raising=False)

    data = card_images.ensure_printing_index_cache(force=True)["data"]

    canonical_key = "delver of secrets // insectile aberration"
    assert canonical_key in data
    assert "delver of secrets" in data
    assert "insectile aberration" in data
    # Face aliases should reuse the same printings entries
    assert data["delver of secrets"] == data[canonical_key]
    assert data["insectile aberration"] == data[canonical_key]


def test_ensure_printing_index_cache_splits_face_aliases_without_card_faces(tmp_path, monkeypatch):
    """A '//' display name with no card_faces must still expose each half.

    Isolates the ``"//" in display_name`` branch of ``_collect_face_aliases``,
    which is the only alias source when bulk data omits ``card_faces``.
    """
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    printings_path = cache_dir / "printings.json"
    payload = [
        {
            "name": "Wear // Tear",
            "id": "uuid-wear-tear",
            "set": "dgm",
            "set_name": "Dragon's Maze",
            "collector_number": "135",
            "released_at": "2013-05-03",
            # Deliberately no "card_faces" key.
        }
    ]
    bulk_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(card_images_schemas, "PRINTING_INDEX_CACHE", printings_path, raising=False)

    data = card_images.ensure_printing_index_cache(force=True)["data"]

    canonical_key = "wear // tear"
    assert data["wear"] == data[canonical_key]
    assert data["tear"] == data[canonical_key]


def test_build_printing_index_sorts_and_counts():
    cards = [
        {
            "name": "Test Card",
            "id": "uuid-1",
            "set": "abc",
            "set_name": "Alpha",
            "collector_number": "1",
            "released_at": "2001-01-01",
        },
        {
            "name": "Test Card",
            "id": "uuid-2",
            "set": "def",
            "set_name": "Delta",
            "collector_number": "2",
            "released_at": "2010-01-01",
        },
        {"name": "", "id": "missing"},
    ]

    by_name, stats = card_images.build_printing_index(cards)

    assert stats["unique_names"] == 1
    assert stats["total_printings"] == 2
    entries = by_name["test card"]
    assert [entry["id"] for entry in entries] == ["uuid-2", "uuid-1"]


def test_face_alias_does_not_pollute_a_real_standalone_card():
    """An adventure/DFC face name that is also a real card must not be aliased.

    "Emeritus of Conflict // Lightning Bolt" has a "Lightning Bolt" face, but the
    genuine Lightning Bolt printings must stay clean — otherwise the inspector
    and printing dropdown would offer the adventure card as a Bolt printing
    (issue #792 regression).
    """
    cards = [
        {
            "name": "Lightning Bolt",
            "id": "bolt-real",
            "set": "lea",
            "released_at": "1993-08-05",
        },
        {
            "name": "Emeritus of Conflict // Lightning Bolt",
            "id": "emeritus-combined",
            "set": "sos",
            "released_at": "2026-04-24",
            "card_faces": [
                {"name": "Emeritus of Conflict"},
                {"name": "Lightning Bolt"},
            ],
        },
    ]

    by_name, _stats = card_images.build_printing_index(cards)

    # The real Lightning Bolt list is untouched by the adventure card.
    assert [e["id"] for e in by_name["lightning bolt"]] == ["bolt-real"]
    # The non-colliding face name still resolves to the combined card.
    assert [e["id"] for e in by_name["emeritus of conflict"]] == ["emeritus-combined"]
    assert by_name["emeritus of conflict // lightning bolt"][0]["id"] == "emeritus-combined"


def _write_bulk_payload(cache_dir, monkeypatch, printings_path):
    """Write a minimal bulk-data cache and point the schema constants at tmp."""
    bulk_path = cache_dir / "bulk_data.json"
    payload = [
        {
            "name": "Test Card",
            "id": "uuid-1",
            "set": "abc",
            "set_name": "Alpha",
            "collector_number": "1",
            "released_at": "2001-01-01",
        }
    ]
    bulk_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(card_images_schemas, "PRINTING_INDEX_CACHE", printings_path, raising=False)
    return bulk_path


def test_ensure_printing_index_cache_reuses_cache_without_rebuild(tmp_path, monkeypatch):
    """A second call with force=False should return the persisted payload as-is."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    printings_path = cache_dir / "printings.json"
    _write_bulk_payload(cache_dir, monkeypatch, printings_path)

    built = card_images.ensure_printing_index_cache(force=True)
    assert printings_path.exists()

    # Force a rebuild to fail loudly if it is unexpectedly triggered.
    def _fail(*_args, **_kwargs):
        raise AssertionError("build_printing_index should not be called on cache reuse")

    monkeypatch.setattr(printing_index_module, "build_printing_index", _fail)

    reused = card_images.ensure_printing_index_cache(force=False)
    assert reused["generated_at"] == built["generated_at"]
    assert reused["data"] == built["data"]


def test_ensure_printing_index_cache_rebuilds_when_bulk_data_newer(tmp_path, monkeypatch):
    """force=False must rebuild when bulk data is newer than the cached index."""
    import os

    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    printings_path = cache_dir / "printings.json"
    bulk_path = _write_bulk_payload(cache_dir, monkeypatch, printings_path)

    built = card_images.ensure_printing_index_cache(force=True)
    assert "test card" in built["data"]
    assert "fresh card" not in built["data"]

    # Replace the bulk data with a different card and bump its mtime past the
    # mtime recorded in the persisted index, exercising the staleness branch.
    bulk_path.write_text(
        json.dumps(
            [
                {
                    "name": "Fresh Card",
                    "id": "uuid-fresh",
                    "set": "xyz",
                    "set_name": "Omega",
                    "collector_number": "9",
                    "released_at": "2020-01-01",
                }
            ]
        ),
        encoding="utf-8",
    )
    newer = built["bulk_mtime"] + 100
    os.utime(bulk_path, (newer, newer))

    rebuilt = card_images.ensure_printing_index_cache(force=False)
    assert "fresh card" in rebuilt["data"]
    assert "test card" not in rebuilt["data"]
    assert rebuilt["bulk_mtime"] >= newer


def test_ensure_printing_index_cache_round_trips_to_disk(tmp_path, monkeypatch):
    """The persisted payload should be readable via load_printing_index_payload."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    printings_path = cache_dir / "printings.json"
    _write_bulk_payload(cache_dir, monkeypatch, printings_path)

    built = card_images.ensure_printing_index_cache(force=True)

    loaded = card_images.load_printing_index_payload()
    assert loaded is not None
    assert loaded["data"] == built["data"]
    assert loaded["version"] == card_images.PRINTING_INDEX_VERSION

    # A version bump must discard the on-disk cache.
    monkeypatch.setattr(
        printing_index_module,
        "PRINTING_INDEX_VERSION",
        card_images.PRINTING_INDEX_VERSION + 1,
    )
    assert card_images.load_printing_index_payload() is None


def test_ensure_printing_index_cache_raises_without_bulk_data(tmp_path, monkeypatch):
    """Missing bulk data should raise rather than build an empty index."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    printings_path = cache_dir / "printings.json"
    missing_bulk = cache_dir / "bulk_data.json"  # intentionally not created

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", missing_bulk, raising=False)
    monkeypatch.setattr(card_images_schemas, "PRINTING_INDEX_CACHE", printings_path, raising=False)

    with pytest.raises(FileNotFoundError):
        card_images.ensure_printing_index_cache(force=True)
