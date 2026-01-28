"""Characterization tests for the card printing index module.

Covers collect_face_aliases edge cases and the ensure_printing_index_cache
build/load/version-mismatch lifecycle.
"""

from __future__ import annotations

import json

import pytest

from utils.card_printing_index import (
    PRINTING_INDEX_VERSION,
    collect_face_aliases,
    ensure_printing_index_cache,
)


# ---------------------------------------------------------------------------
# collect_face_aliases
# ---------------------------------------------------------------------------


def test_collect_face_aliases_mdfc():
    """A double-faced card should yield both face names as aliases."""
    card = {
        "card_faces": [
            {"name": "Front Face"},
            {"name": "Back Face"},
        ]
    }
    aliases = collect_face_aliases(card, "Front Face // Back Face")
    assert "Front Face" in aliases
    assert "Back Face" in aliases
    # The canonical combined name itself should NOT be in the set
    assert "Front Face // Back Face" not in aliases


def test_collect_face_aliases_excludes_canonical_name():
    """The canonical display_name should never appear in the alias set."""
    card = {"card_faces": [{"name": "Delver of Secrets"}]}
    aliases = collect_face_aliases(card, "Delver of Secrets")
    assert "Delver of Secrets" not in aliases


def test_collect_face_aliases_split_card_no_faces_key():
    """A card with '//' in name but no card_faces should still split."""
    card = {}  # no card_faces key
    aliases = collect_face_aliases(card, "Split Left // Split Right")
    assert "Split Left" in aliases
    assert "Split Right" in aliases


def test_collect_face_aliases_single_faced_card():
    """A single-faced card with no '//' should produce no aliases."""
    card = {"card_faces": []}
    aliases = collect_face_aliases(card, "Lightning Bolt")
    assert aliases == set()


def test_collect_face_aliases_strips_whitespace():
    """Face names with surrounding whitespace should be trimmed."""
    card = {
        "card_faces": [
            {"name": "  Left  "},
            {"name": "  Right  "},
        ]
    }
    aliases = collect_face_aliases(card, "Left // Right")
    assert "Left" in aliases
    assert "Right" in aliases


def test_collect_face_aliases_skips_empty_face_names():
    """Empty or whitespace-only face name entries should be ignored."""
    card = {
        "card_faces": [
            {"name": ""},
            {"name": "   "},
            {"name": "Real Face"},
        ]
    }
    aliases = collect_face_aliases(card, "Real Face // Other")
    assert "" not in aliases
    assert "Real Face" in aliases
    assert "Other" in aliases


def test_collect_face_aliases_case_sensitive_exclusion():
    """Exclusion of the canonical name should be case-insensitive."""
    card = {"card_faces": [{"name": "lightning bolt"}]}
    aliases = collect_face_aliases(card, "Lightning Bolt")
    # "lightning bolt" matches "Lightning Bolt" case-insensitively -> excluded
    assert aliases == set()


# ---------------------------------------------------------------------------
# ensure_printing_index_cache -- build path
# ---------------------------------------------------------------------------


def _write_bulk(path, cards):
    """Helper to write a bulk data JSON file."""
    path.write_text(json.dumps(cards), encoding="utf-8")


def test_ensure_printing_index_cache_builds_from_bulk(tmp_path):
    """A fresh cache should be built from bulk data and written to disk."""
    bulk = tmp_path / "bulk.json"
    index = tmp_path / "index.json"

    _write_bulk(
        bulk,
        [
            {
                "name": "Lightning Bolt",
                "id": "uuid-bolt",
                "set": "m11",
                "set_name": "Magic 2011",
                "collector_number": "97",
                "released_at": "2010-08-13",
            }
        ],
    )

    payload = ensure_printing_index_cache(
        force=True,
        image_cache_dir=tmp_path,
        bulk_data_cache=bulk,
        printing_index_cache=index,
    )

    assert payload["version"] == PRINTING_INDEX_VERSION
    assert "lightning bolt" in payload["data"]
    assert payload["data"]["lightning bolt"][0]["id"] == "uuid-bolt"
    assert payload["total_printings"] == 1
    # Index file should be persisted
    assert index.exists()


def test_ensure_printing_index_cache_returns_existing_when_current(tmp_path):
    """When the cached index is newer than bulk data, it should be reused."""
    bulk = tmp_path / "bulk.json"
    index = tmp_path / "index.json"

    _write_bulk(bulk, [{"name": "Card A", "id": "uuid-a", "set": "tst", "set_name": "Test", "collector_number": "1", "released_at": "2024-01-01"}])

    # Build initial index
    first = ensure_printing_index_cache(
        force=True,
        image_cache_dir=tmp_path,
        bulk_data_cache=bulk,
        printing_index_cache=index,
    )

    # Call again without force -- should return the cached version
    second = ensure_printing_index_cache(
        force=False,
        image_cache_dir=tmp_path,
        bulk_data_cache=bulk,
        printing_index_cache=index,
    )

    assert second["data"] == first["data"]


def test_ensure_printing_index_cache_rebuilds_on_version_mismatch(tmp_path):
    """A cached index with a wrong version should be discarded and rebuilt."""
    bulk = tmp_path / "bulk.json"
    index = tmp_path / "index.json"

    _write_bulk(bulk, [{"name": "Card B", "id": "uuid-b", "set": "tst", "set_name": "Test", "collector_number": "2", "released_at": "2024-02-01"}])

    # Write a stale index with wrong version
    stale = {"version": PRINTING_INDEX_VERSION - 1, "data": {}, "bulk_mtime": 0}
    index.write_text(json.dumps(stale), encoding="utf-8")

    payload = ensure_printing_index_cache(
        force=False,
        image_cache_dir=tmp_path,
        bulk_data_cache=bulk,
        printing_index_cache=index,
    )

    # Should have been rebuilt with current version
    assert payload["version"] == PRINTING_INDEX_VERSION
    assert "card b" in payload["data"]


def test_ensure_printing_index_cache_raises_when_no_bulk(tmp_path):
    """Should raise FileNotFoundError when bulk data does not exist."""
    bulk = tmp_path / "nonexistent_bulk.json"
    index = tmp_path / "index.json"

    with pytest.raises(FileNotFoundError, match="Bulk data cache not found"):
        ensure_printing_index_cache(
            force=True,
            image_cache_dir=tmp_path,
            bulk_data_cache=bulk,
            printing_index_cache=index,
        )


def test_ensure_printing_index_cache_includes_mdfc_aliases(tmp_path):
    """Double-faced cards should be indexed under each face name."""
    bulk = tmp_path / "bulk.json"
    index = tmp_path / "index.json"

    _write_bulk(
        bulk,
        [
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
        ],
    )

    payload = ensure_printing_index_cache(
        force=True,
        image_cache_dir=tmp_path,
        bulk_data_cache=bulk,
        printing_index_cache=index,
    )

    data = payload["data"]
    canonical = "delver of secrets // insectile aberration"
    assert canonical in data
    assert "delver of secrets" in data
    assert "insectile aberration" in data
    # All three keys should point to the same entry
    assert data["delver of secrets"] == data[canonical]
    assert data["insectile aberration"] == data[canonical]


def test_ensure_printing_index_cache_sorts_by_released_at_desc(tmp_path):
    """Multiple printings of the same card should be sorted newest first."""
    bulk = tmp_path / "bulk.json"
    index = tmp_path / "index.json"

    _write_bulk(
        bulk,
        [
            {
                "name": "Lightning Bolt",
                "id": "uuid-old",
                "set": "m10",
                "set_name": "Magic 2010",
                "collector_number": "130",
                "released_at": "2009-09-04",
            },
            {
                "name": "Lightning Bolt",
                "id": "uuid-new",
                "set": "m11",
                "set_name": "Magic 2011",
                "collector_number": "97",
                "released_at": "2010-08-13",
            },
        ],
    )

    payload = ensure_printing_index_cache(
        force=True,
        image_cache_dir=tmp_path,
        bulk_data_cache=bulk,
        printing_index_cache=index,
    )

    entries = payload["data"]["lightning bolt"]
    assert len(entries) == 2
    # Newest first
    assert entries[0]["id"] == "uuid-new"
    assert entries[1]["id"] == "uuid-old"
