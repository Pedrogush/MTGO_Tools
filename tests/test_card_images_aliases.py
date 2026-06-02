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


def test_card_image_cache_resolves_double_faced_alias(tmp_path):
    """Image cache should find stored MDFC images via either face name."""
    cache_dir = tmp_path / "cache"
    db_path = cache_dir / "images.db"
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=db_path)
    front_path = cache.cache_dir / "normal" / "uuid-delver.jpg"
    back_path = cache.cache_dir / "normal" / "uuid-delver-f1.jpg"
    front_path.parent.mkdir(parents=True, exist_ok=True)
    front_path.write_bytes(b"front")
    back_path.write_bytes(b"back")

    cache.add_image(
        uuid="uuid-delver",
        name="Delver of Secrets",
        set_code="ISD",
        collector_number="51",
        image_size="normal",
        file_path=front_path,
        face_index=0,
    )
    cache.add_image(
        uuid="uuid-delver",
        name="Insectile Aberration",
        set_code="ISD",
        collector_number="51",
        image_size="normal",
        file_path=back_path,
        face_index=1,
    )
    cache.add_image(
        uuid="uuid-delver",
        name="Delver of Secrets // Insectile Aberration",
        set_code="ISD",
        collector_number="51",
        image_size="normal",
        file_path=front_path,
        face_index=-1,
    )

    assert cache.get_image_path("Delver of Secrets") == front_path
    assert cache.get_image_path("Insectile Aberration") == back_path
    assert cache.get_image_path("Delver of Secrets // Insectile Aberration") == front_path
    assert cache.get_image_paths_by_uuid("uuid-delver") == [front_path, back_path]


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


def test_card_image_cache_resolves_accent_insensitive(tmp_path):
    """Image cache should match across diacritics in either direction.

    Cards like "Lórien Revealed" may be stored under their accented Scryfall
    name but requested without accents (or vice-versa). SQLite's LOWER() does
    not strip combining characters, so the cache registers a custom
    strip_accents scalar as a fallback lookup.
    """
    cache_dir = tmp_path / "cache"
    db_path = cache_dir / "images.db"
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=db_path)

    accented_path = cache.cache_dir / "normal" / "uuid-lorien.jpg"
    unaccented_path = cache.cache_dir / "normal" / "uuid-other.jpg"
    accented_path.parent.mkdir(parents=True, exist_ok=True)
    accented_path.write_bytes(b"accented")
    unaccented_path.write_bytes(b"unaccented")

    # Stored with accents, queried without.
    cache.add_image(
        uuid="uuid-lorien",
        name="Lórien Revealed",
        set_code="MH3",
        collector_number="1",
        image_size="normal",
        file_path=accented_path,
        face_index=0,
    )
    assert cache.get_image_path("Lorien Revealed") == accented_path

    # Stored without accents, queried with.
    cache.add_image(
        uuid="uuid-other",
        name="Geralf, Visionary Stitcher",
        set_code="MID",
        collector_number="2",
        image_size="normal",
        file_path=unaccented_path,
        face_index=0,
    )
    assert cache.get_image_path("Géralf, Visionary Stitcher") == unaccented_path


def test_card_image_cache_path_cache_invalidated_on_add(tmp_path):
    """A miss must not be cached, and add_image must evict stale positive hits."""
    cache_dir = tmp_path / "cache"
    db_path = cache_dir / "images.db"
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=db_path)

    first_path = cache.cache_dir / "normal" / "uuid-card.jpg"
    second_path = cache.cache_dir / "normal" / "uuid-card-v2.jpg"
    first_path.parent.mkdir(parents=True, exist_ok=True)
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    # Miss before the image exists; None must not be cached.
    assert cache.get_image_path("Lightning Bolt") is None

    cache.add_image(
        uuid="uuid-card",
        name="Lightning Bolt",
        set_code="LEA",
        collector_number="161",
        image_size="normal",
        file_path=first_path,
        face_index=0,
    )
    # The earlier miss must not suppress the now-available path.
    assert cache.get_image_path("Lightning Bolt") == first_path

    # Re-adding to a different path must invalidate the cached positive hit.
    cache.add_image(
        uuid="uuid-card",
        name="Lightning Bolt",
        set_code="2ED",
        collector_number="162",
        image_size="normal",
        file_path=second_path,
        face_index=0,
    )
    assert cache.get_image_path("Lightning Bolt") == second_path


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
