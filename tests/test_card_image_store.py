"""Characterization tests for CardImageStore.

Covers schema creation, migration from pre-face-index tables,
add_image/get_rows round-trips, bulk_data_meta operations, and
cache statistics.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from utils.card_image_store import CardImageStore


def _make_store(tmp_path: Path) -> CardImageStore:
    """Helper: create a CardImageStore backed by a fresh tmp database."""
    return CardImageStore(tmp_path / "images.db")


def test_schema_creation_produces_expected_tables(tmp_path):
    """A fresh store should have card_images and bulk_data_meta tables."""
    store = _make_store(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "card_images" in tables
    assert "bulk_data_meta" in tables


def test_schema_has_face_index_column(tmp_path):
    """The card_images table must include a face_index column."""
    store = _make_store(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(card_images)").fetchall()}
    assert "face_index" in columns


def test_migration_adds_face_index_to_legacy_table(tmp_path):
    """Opening a database without face_index should trigger migration."""
    db_path = tmp_path / "images.db"

    # Seed a legacy schema (no face_index column)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE card_images (
                uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                set_code TEXT,
                collector_number TEXT,
                image_size TEXT NOT NULL,
                file_path TEXT NOT NULL,
                downloaded_at TEXT NOT NULL,
                scryfall_uri TEXT,
                artist TEXT
            )
            """)
        conn.execute("""
            INSERT INTO card_images
            (uuid, name, set_code, collector_number, image_size, file_path, downloaded_at)
            VALUES ('uuid-legacy', 'Legacy Card', 'SET', '001', 'normal', '/tmp/legacy.jpg', '2024-01-01')
            """)
        conn.commit()

    # Opening the store should migrate the table
    store = CardImageStore(db_path)

    with sqlite3.connect(store.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(card_images)").fetchall()}
        assert "face_index" in columns

        row = conn.execute("SELECT uuid, face_index, name FROM card_images").fetchone()

    assert row == ("uuid-legacy", 0, "Legacy Card")


def test_add_image_and_get_rows_by_name_round_trip(tmp_path):
    """An image added via add_image should be retrievable by name."""
    store = _make_store(tmp_path)
    file_path = tmp_path / "normal" / "abc.jpg"

    store.add_image(
        uuid="uuid-abc",
        name="Lightning Bolt",
        set_code="M11",
        collector_number="97",
        image_size="normal",
        file_path=file_path,
        face_index=0,
    )

    rows = store.get_rows_by_name("Lightning Bolt", "normal")
    assert len(rows) == 1
    assert str(file_path.resolve()) in rows[0][0]


def test_get_rows_by_name_is_case_insensitive(tmp_path):
    """Name lookup should be case-insensitive."""
    store = _make_store(tmp_path)
    file_path = tmp_path / "normal" / "bolt.jpg"

    store.add_image(
        uuid="uuid-bolt",
        name="Lightning Bolt",
        set_code="M11",
        collector_number="97",
        image_size="normal",
        file_path=file_path,
    )

    assert len(store.get_rows_by_name("lightning bolt", "normal")) == 1
    assert len(store.get_rows_by_name("LIGHTNING BOLT", "normal")) == 1
    assert len(store.get_rows_by_name("Lightning Bolt", "normal")) == 1


def test_get_rows_by_name_returns_empty_for_unknown(tmp_path):
    """Querying a name not in the database should return an empty list."""
    store = _make_store(tmp_path)
    assert store.get_rows_by_name("Nonexistent Card", "normal") == []


def test_get_rows_by_uuid_round_trip(tmp_path):
    """An image should be retrievable by its UUID."""
    store = _make_store(tmp_path)
    file_path = tmp_path / "normal" / "uuid-test.jpg"

    store.add_image(
        uuid="uuid-test",
        name="Test Card",
        set_code="TST",
        collector_number="1",
        image_size="normal",
        file_path=file_path,
        face_index=0,
    )

    rows = store.get_rows_by_uuid("uuid-test", "normal", face_index=0)
    assert len(rows) == 1


def test_get_rows_by_uuid_face_index_none_returns_all_faces(tmp_path):
    """Passing face_index=None should return all faces for a UUID."""
    store = _make_store(tmp_path)

    for idx in (0, 1):
        store.add_image(
            uuid="uuid-multi",
            name=f"Face {idx}",
            set_code="TST",
            collector_number="1",
            image_size="normal",
            file_path=tmp_path / f"face{idx}.jpg",
            face_index=idx,
        )

    rows = store.get_rows_by_uuid("uuid-multi", "normal", face_index=None)
    assert len(rows) == 2


def test_get_all_face_rows_ordered_by_face_index(tmp_path):
    """get_all_face_rows should return faces ordered by face_index ascending."""
    store = _make_store(tmp_path)

    # Insert in reverse order to verify sorting
    for idx in (1, 0):
        store.add_image(
            uuid="uuid-order",
            name=f"Face {idx}",
            set_code="TST",
            collector_number="1",
            image_size="normal",
            file_path=tmp_path / f"face{idx}.jpg",
            face_index=idx,
        )

    rows = store.get_all_face_rows("uuid-order", "normal")
    assert len(rows) == 2
    assert rows[0][0] == 0  # face_index 0 first
    assert rows[1][0] == 1  # face_index 1 second


def test_get_rows_by_name_pattern_matches_like(tmp_path):
    """Pattern queries should support SQL LIKE wildcards."""
    store = _make_store(tmp_path)

    store.add_image(
        uuid="uuid-split",
        name="Front Face // Back Face",
        set_code="TST",
        collector_number="1",
        image_size="normal",
        file_path=tmp_path / "split.jpg",
    )

    # Match the back face via pattern
    rows = store.get_rows_by_name_pattern("% // back face", "normal")
    assert len(rows) == 1

    # Match the front face via pattern
    rows = store.get_rows_by_name_pattern("front face // %", "normal")
    assert len(rows) == 1


def test_upsert_and_get_bulk_data_record(tmp_path):
    """Bulk data metadata should survive a write/read round-trip."""
    store = _make_store(tmp_path)

    store.upsert_bulk_data_meta(
        downloaded_at="2024-06-15T12:00:00Z",
        total_cards=250000,
        bulk_data_uri="https://example.com/bulk.json",
    )

    downloaded_at, uri = store.get_bulk_data_record()
    assert downloaded_at == "2024-06-15T12:00:00Z"
    assert uri == "https://example.com/bulk.json"


def test_get_bulk_data_record_returns_none_when_empty(tmp_path):
    """An empty bulk_data_meta table should yield (None, None)."""
    store = _make_store(tmp_path)
    downloaded_at, uri = store.get_bulk_data_record()
    assert downloaded_at is None
    assert uri is None


def test_upsert_bulk_data_meta_overwrites_previous(tmp_path):
    """A second upsert should overwrite the singleton row."""
    store = _make_store(tmp_path)

    store.upsert_bulk_data_meta("2024-01-01T00:00:00Z", 100, "http://a.com")
    store.upsert_bulk_data_meta("2024-06-01T00:00:00Z", 200, "http://b.com")

    downloaded_at, uri = store.get_bulk_data_record()
    assert downloaded_at == "2024-06-01T00:00:00Z"
    assert uri == "http://b.com"


def test_get_cache_stats_counts_correctly(tmp_path):
    """Cache stats should reflect inserted records accurately."""
    store = _make_store(tmp_path)

    # Insert two normal images and one small image
    for i, size in enumerate(("normal", "normal", "small")):
        store.add_image(
            uuid=f"uuid-stat-{i}",
            name=f"Card {i}",
            set_code="TST",
            collector_number=str(i),
            image_size=size,
            file_path=tmp_path / f"{size}" / f"card{i}.jpg",
        )

    stats = store.get_cache_stats()
    assert stats["unique_cards"] == 3
    assert stats["by_size"]["normal"] == 2
    assert stats["by_size"]["small"] == 1
    assert stats["by_size"]["large"] == 0
    assert stats["by_size"]["png"] == 0


def test_get_cache_stats_includes_bulk_metadata(tmp_path):
    """Stats should report bulk data date when metadata is present."""
    store = _make_store(tmp_path)
    store.upsert_bulk_data_meta("2024-03-20T10:00:00Z", 150000, "http://x.com")

    stats = store.get_cache_stats()
    assert stats["bulk_data_date"] == "2024-03-20T10:00:00Z"
    assert stats["bulk_total_cards"] == 150000
