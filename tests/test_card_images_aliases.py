"""Tests for card image alias handling and printing index generation."""

from __future__ import annotations

import json

from utils import card_images


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

    monkeypatch.setattr(card_images, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(card_images, "PRINTING_INDEX_CACHE", printings_path, raising=False)

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
