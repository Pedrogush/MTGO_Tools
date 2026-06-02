"""Additional tests for card image cache behavior."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from services import image_service as card_images
from services.image_service import schemas as card_images_schemas


def test_card_image_cache_migrates_face_index_column(tmp_path):
    """Existing databases without face_index should be migrated safely."""
    cache_dir = tmp_path / "cache"
    db_path = cache_dir / "images.db"
    cache_dir.mkdir(parents=True, exist_ok=True)

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
        conn.execute(
            """
            INSERT INTO card_images (
                uuid, name, set_code, collector_number, image_size, file_path, downloaded_at,
                scryfall_uri, artist
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "uuid-old",
                "Legacy Entry",
                "SET",
                "001",
                "normal",
                "legacy/path.jpg",
                datetime.now(card_images_schemas.UTC).isoformat(),
                None,
                None,
            ),
        )
        conn.commit()

    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=db_path)
    assert cache.db_path.exists()  # ensure initialization succeeded

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(card_images)")}
        assert "face_index" in columns
        migrated_row = conn.execute("SELECT uuid, face_index, name FROM card_images").fetchone()

    assert migrated_row == ("uuid-old", 0, "Legacy Entry")


def test_resolves_windows_style_relative_paths(tmp_path):
    """Backslash-separated cache entries should be normalized and resolved."""
    cache_dir = tmp_path / "cache"
    db_path = cache_dir / "images.db"
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=db_path)

    expected_path = cache.cache_dir / "normal" / "uuid-win.png"
    expected_path.write_bytes(b"image")

    with sqlite3.connect(cache.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO card_images (
                uuid, face_index, name, set_code, collector_number, image_size, file_path,
                downloaded_at, scryfall_uri, artist
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "uuid-win",
                0,
                "Windows Path",
                "SET",
                "007",
                "normal",
                "normal\\uuid-win.png",
                datetime.now(card_images_schemas.UTC).isoformat(),
                None,
                None,
            ),
        )
        conn.commit()

    resolved = cache.get_image_by_uuid("uuid-win", size="normal")
    assert resolved == expected_path


def test_is_bulk_data_outdated_respects_cached_metadata(tmp_path, monkeypatch):
    """Bulk metadata comparison should rely on cached DB entries when present."""
    cache_dir = tmp_path / "card_images"
    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.parent.mkdir(parents=True, exist_ok=True)
    bulk_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)

    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)

    metadata = {
        "updated_at": "2024-01-01T00:00:00Z",
        "download_uri": "http://example.com/bulk",
    }
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: metadata)

    with sqlite3.connect(cache.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO bulk_data_meta (id, downloaded_at, total_cards, bulk_data_uri)
            VALUES (1, ?, ?, ?)
            """,
            (metadata["updated_at"], 0, metadata["download_uri"]),
        )
        conn.commit()

    is_outdated, returned_metadata = downloader.is_bulk_data_outdated()

    assert is_outdated is False
    assert returned_metadata["download_uri"] == metadata["download_uri"]


def test_get_image_path_caches_first_db_hit(tmp_path):
    """get_image_path() should serve repeated lookups from the in-memory cache.

    Behavioural proof: after the first lookup populates the cache, deleting the
    underlying DB row must not change the result of a second lookup — the only
    way the path can still resolve is from the cached value, not a fresh query.
    """
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "test.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")

    # Seed the DB directly so the first lookup succeeds
    cache.add_image(
        uuid="uuid-once",
        name="Test Card",
        set_code="SET",
        collector_number="001",
        image_size="normal",
        file_path=image_file,
    )
    # Clear path cache so the first real call goes to DB
    cache._path_cache.clear()

    result1 = cache.get_image_path("Test Card", "normal")
    assert result1 == image_file

    # Remove the row the first lookup read; a DB-backed second lookup would now
    # miss, so a matching result proves the value came from the in-memory cache.
    with sqlite3.connect(cache.db_path) as conn:
        conn.execute("DELETE FROM card_images")
        conn.commit()

    result2 = cache.get_image_path("Test Card", "normal")
    assert result2 == image_file


def test_get_image_path_returns_path_after_add_image_when_initial_miss(tmp_path):
    """After a None lookup, add_image() must invalidate the cache so next call returns the path."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )

    # First lookup returns None (card not yet downloaded)
    result_before = cache.get_image_path("New Card", "normal")
    assert result_before is None
    # None hits must not be stored — a subsequent download must be visible.
    # (add_image() is responsible for invalidating the key, not the test.)
    assert ("new card", "normal") not in cache._path_cache

    # Simulate download completing
    image_file = cache.cache_dir / "normal" / "uuid-new.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-new",
        name="New Card",
        set_code="SET",
        collector_number="002",
        image_size="normal",
        file_path=image_file,
    )

    # Lookup after add_image() must return the path
    result_after = cache.get_image_path("New Card", "normal")
    assert result_after == image_file


def test_get_image_path_cache_key_is_case_insensitive(tmp_path):
    """get_image_path() must treat card names case-insensitively for cache hits.

    The first uppercase lookup populates the cache under the lowercased key.
    Deleting the DB row afterwards proves the second (also uppercase) lookup is
    served from that case-folded cache entry rather than a fresh query.
    """
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-case.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-case",
        name="Lightning Bolt",
        set_code="LEB",
        collector_number="161",
        image_size="normal",
        file_path=image_file,
    )
    # Clear path cache to force a DB hit on the first lookup
    cache._path_cache.clear()

    result = cache.get_image_path("LIGHTNING BOLT", "normal")
    assert result == image_file

    # Remove the row; a DB-backed second lookup would now miss, so a matching
    # result proves the cache key was case-folded on insert and on lookup.
    with sqlite3.connect(cache.db_path) as conn:
        conn.execute("DELETE FROM card_images")
        conn.commit()

    result2 = cache.get_image_path("LIGHTNING BOLT", "normal")
    assert result2 == image_file


def test_add_image_invalidates_only_matching_size_key(tmp_path):
    """add_image() must evict only the key for the updated size, leaving other sizes intact."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    small_file = cache.cache_dir / "small" / "uuid-size-small.jpg"
    normal_file = cache.cache_dir / "normal" / "uuid-size-normal.jpg"
    small_file.parent.mkdir(parents=True, exist_ok=True)
    normal_file.parent.mkdir(parents=True, exist_ok=True)
    small_file.write_bytes(b"small")
    normal_file.write_bytes(b"normal")

    cache.add_image(
        uuid="uuid-size",
        name="Test Card",
        set_code="SET",
        collector_number="1",
        image_size="small",
        file_path=small_file,
    )
    cache.add_image(
        uuid="uuid-size",
        name="Test Card",
        set_code="SET",
        collector_number="1",
        image_size="normal",
        file_path=normal_file,
    )

    # Populate both size entries in the path cache
    assert cache.get_image_path("Test Card", "small") == small_file
    assert cache.get_image_path("Test Card", "normal") == normal_file
    assert ("test card", "small") in cache._path_cache
    assert ("test card", "normal") in cache._path_cache

    # add_image() for "normal" must only invalidate the normal key
    cache.add_image(
        uuid="uuid-size-v2",
        name="Test Card",
        set_code="SET",
        collector_number="1",
        image_size="normal",
        file_path=normal_file,
    )

    assert ("test card", "normal") not in cache._path_cache, "normal key must be invalidated"
    assert ("test card", "small") in cache._path_cache, "small key must remain untouched"


def test_add_image_with_none_optional_params_does_not_raise(tmp_path):
    """add_image() must succeed when scryfall_uri and artist are omitted."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-opt.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")

    # Must not raise even without the optional scryfall_uri and artist kwargs
    cache.add_image(
        uuid="u1",
        name="Opt Card",
        set_code="SET",
        collector_number="1",
        image_size="normal",
        file_path=image_file,
    )

    result = cache.get_image_path("Opt Card", "normal")
    assert result == image_file


def test_get_image_path_is_thread_safe(tmp_path):
    """Concurrent calls to get_image_path() for the same key must not raise."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-thread.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-thread",
        name="Thread Card",
        set_code="SET",
        collector_number="003",
        image_size="normal",
        file_path=image_file,
    )
    cache._path_cache.clear()

    results: list[object] = []
    errors: list[Exception] = []

    def worker():
        try:
            results.append(cache.get_image_path("Thread Card", "normal"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    assert all(r == image_file for r in results)


def test_get_image_path_concurrent_add_and_get_is_race_free(tmp_path):
    """Concurrent add_image() writers and get_image_path() readers must not race.

    A threading.Barrier synchronises all threads to start simultaneously,
    maximising the probability of a writer and reader hitting the TOCTOU
    window that the _path_cache_lock was introduced to protect.
    """
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    files: dict[str, object] = {}
    for i in range(5):
        f = cache.cache_dir / "normal" / f"uuid-race-{i}.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"fake")
        files[f"Race Card {i}"] = f

    barrier = threading.Barrier(len(files) * 2)
    errors: list[Exception] = []

    def writer(name: str, path: object) -> None:
        try:
            barrier.wait()
            cache.add_image(
                uuid=f"uuid-race-{name}",
                name=name,
                set_code="SET",
                collector_number="1",
                image_size="normal",
                file_path=path,
            )
        except Exception as exc:
            errors.append(exc)

    def reader(name: str) -> None:
        try:
            barrier.wait()
            cache.get_image_path(name, "normal")
        except Exception as exc:
            errors.append(exc)

    threads = []
    for name, path in files.items():
        threads.append(threading.Thread(target=writer, args=(name, path)))
        threads.append(threading.Thread(target=reader, args=(name,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Race errors: {errors}"


def test_get_image_path_accent_normalized_fallback(tmp_path):
    """get_image_path() should find a card stored as 'Lórien Revealed' when queried as 'Lorien Revealed'."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-lorien.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")

    # Store the image under the accented Scryfall name
    cache.add_image(
        uuid="uuid-lorien",
        name="Lórien Revealed",
        set_code="LTR",
        collector_number="057",
        image_size="normal",
        file_path=image_file,
    )
    cache._path_cache.clear()

    # Querying without the accent should still find the image
    result = cache.get_image_path("Lorien Revealed", "normal")
    assert result == image_file


def test_get_image_path_exact_match_wins_over_accent_fallback(tmp_path):
    """An exact-name hit must short-circuit before the accent-stripping query.

    Behavioural proxy: store two rows whose names are identical once accents are
    stripped ("Lorien" vs "Lórien"). A query for the exact ASCII name must
    return *that* row, not the accented one. If the exact match did not
    short-circuit, the accent fallback could surface either row, so a stable,
    exact-name result proves the fast path ran first.
    """
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    ascii_file = cache.cache_dir / "normal" / "uuid-ascii.jpg"
    accent_file = cache.cache_dir / "normal" / "uuid-accent.jpg"
    ascii_file.parent.mkdir(parents=True, exist_ok=True)
    ascii_file.write_bytes(b"ascii")
    accent_file.write_bytes(b"accent")

    # Exact ASCII spelling.
    cache.add_image(
        uuid="uuid-ascii",
        name="Lorien Revealed",
        set_code="LTR",
        collector_number="060",
        image_size="normal",
        file_path=ascii_file,
    )
    # Accented spelling that collides only under accent-stripping.
    cache.add_image(
        uuid="uuid-accent",
        name="Lórien Revealed",
        set_code="LTR",
        collector_number="057",
        image_size="normal",
        file_path=accent_file,
    )
    cache._path_cache.clear()

    # The exact ASCII match must win and return its own file.
    assert cache.get_image_path("Lorien Revealed", "normal") == ascii_file


def _write_bulk_data(cache_dir, monkeypatch):
    """Seed a small bulk_data.json and point the schemas constant at it."""
    import json

    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.parent.mkdir(parents=True, exist_ok=True)
    bulk_path.write_text(
        json.dumps(
            [
                {
                    "name": "Lightning Bolt",
                    "id": "u-lea",
                    "set": "lea",
                    "collector_number": "161",
                    "image_uris": {"normal": "http://img/bolt-lea.jpg"},
                },
                {
                    "name": "Lightning Bolt",
                    "id": "u-m11",
                    "set": "m11",
                    "collector_number": "149",
                    "image_uris": {"normal": "http://img/bolt-m11.jpg"},
                },
                {
                    "name": "Fire // Ice",
                    "id": "u-fireice",
                    "set": "apc",
                    "card_faces": [{"name": "Fire"}, {"name": "Ice"}],
                    "image_uris": {"normal": "http://img/fireice.jpg"},
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    return bulk_path


def test_resolve_card_locally_returns_record_without_set(tmp_path, monkeypatch):
    """A name-only lookup resolves to a local printing and skips the API."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)

    card = downloader._resolve_card_locally("Lightning Bolt")
    assert card is not None
    assert card.get("id") in {"u-lea", "u-m11"}
    assert card.get("image_uris", {}).get("normal")


def test_resolve_card_locally_matches_requested_set(tmp_path, monkeypatch):
    """A set-qualified lookup returns the matching printing (case-insensitive)."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)

    card = downloader._resolve_card_locally("lightning bolt", set_code="M11")
    assert card is not None
    assert card.get("id") == "u-m11"


def test_resolve_card_locally_missing_set_defers_to_api(tmp_path, monkeypatch):
    """A set we lack locally returns None so the caller hits the API."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)

    assert downloader._resolve_card_locally("Lightning Bolt", set_code="ZZZ") is None
    assert downloader._resolve_card_locally("Unknown Card") is None


def test_resolve_card_locally_resolves_face_name(tmp_path, monkeypatch):
    """A single face name of a split/MDFC card resolves to the full card."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)

    card = downloader._resolve_card_locally("Fire")
    assert card is not None
    assert card.get("id") == "u-fireice"


def test_download_by_name_uses_local_index_before_api(tmp_path, monkeypatch):
    """A local hit must avoid the Scryfall /cards/named round-trip.

    Runs the real download pipeline against a ``_FakeSession`` so the local
    resolution is proven by the file/DB outcome (the LEA printing's image URL is
    fetched and persisted), not by spying on the private downloader method.
    """
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    def _no_api(*_args, **_kwargs):
        raise AssertionError("fetch_card_by_name should not be called on a local hit")

    monkeypatch.setattr(downloader, "fetch_card_by_name", _no_api)

    success, message = downloader.download_card_image_by_name(
        "Lightning Bolt", "normal", set_code="LEA"
    )
    assert success is True
    assert "Downloaded" in message
    # The locally-resolved LEA printing's image URL was fetched (not the M11 one).
    assert downloader.session.calls == ["http://img/bolt-lea.jpg"]
    # ...and the LEA printing was persisted under its uuid.
    stored = cache.get_image_by_uuid("u-lea", "normal", face_index=0)
    assert stored is not None and stored.exists()


def test_download_by_name_falls_back_to_api_on_local_miss(tmp_path, monkeypatch):
    """A name absent from local bulk data must fall back to the API."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)

    downloader.session = _FakeSession()
    api_calls = {"n": 0}

    def _api(name, set_code=None):
        api_calls["n"] += 1
        return {"id": "api-id", "name": name, "image_uris": {"normal": "http://api/img.jpg"}}

    monkeypatch.setattr(downloader, "fetch_card_by_name", _api)

    success, _ = downloader.download_card_image_by_name("Totally Unknown Card", "normal")
    assert success is True
    # The API was consulted exactly once and its image URL was fetched + stored.
    assert api_calls["n"] == 1
    assert downloader.session.calls == ["http://api/img.jpg"]
    stored = cache.get_image_by_uuid("api-id", "normal", face_index=0)
    assert stored is not None and stored.exists()


# ---------------------------------------------------------------------------
# is_bulk_data_outdated — outdated / mismatch / age-fallback branches
# ---------------------------------------------------------------------------


def _make_downloader(tmp_path, monkeypatch, bulk_contents="[]"):
    """Build a downloader with BULK_DATA_CACHE pointed at a temp bulk file."""
    cache_dir = tmp_path / "card_images"
    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.parent.mkdir(parents=True, exist_ok=True)
    if bulk_contents is not None:
        bulk_path.write_text(bulk_contents, encoding="utf-8")
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    return card_images.BulkImageDownloader(cache), bulk_path


def test_is_bulk_data_outdated_when_cache_file_missing(tmp_path, monkeypatch):
    """No on-disk bulk file => outdated, regardless of vendor metadata."""
    downloader, bulk_path = _make_downloader(tmp_path, monkeypatch, bulk_contents=None)
    metadata = {"updated_at": "2024-01-01T00:00:00Z", "download_uri": "http://example.com/bulk"}
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: metadata)

    assert not bulk_path.exists()
    is_outdated, returned = downloader.is_bulk_data_outdated()
    assert is_outdated is True
    assert returned is metadata


def test_is_bulk_data_outdated_when_metadata_mismatches_cache(tmp_path, monkeypatch):
    """A different updated_at/uri than the cached row => outdated."""
    downloader, _ = _make_downloader(tmp_path, monkeypatch)
    metadata = {"updated_at": "2024-02-02T00:00:00Z", "download_uri": "http://example.com/new"}
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: metadata)

    with sqlite3.connect(downloader.cache.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO bulk_data_meta (id, downloaded_at, total_cards, bulk_data_uri)
            VALUES (1, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", 0, "http://example.com/old"),
        )
        conn.commit()

    is_outdated, _ = downloader.is_bulk_data_outdated()
    assert is_outdated is True


def test_is_bulk_data_outdated_age_fallback_when_fresh(tmp_path, monkeypatch):
    """Vendor metadata lacking timestamps => age-based check; fresh file is not outdated."""
    downloader, _ = _make_downloader(tmp_path, monkeypatch)
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: {})

    # The file was just written, so its age is well under the freshness threshold.
    is_outdated, _ = downloader.is_bulk_data_outdated()
    assert is_outdated is False


def test_is_bulk_data_outdated_age_fallback_when_stale(tmp_path, monkeypatch):
    """Vendor metadata lacking timestamps + a stale file => outdated."""
    import os

    downloader, bulk_path = _make_downloader(tmp_path, monkeypatch)
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: {})

    # Backdate the file far past the freshness threshold to exercise the stale
    # branch of the age-based fallback.
    old = datetime.now().timestamp() - 10**9
    os.utime(bulk_path, (old, old))

    is_outdated, _ = downloader.is_bulk_data_outdated()
    assert is_outdated is True


# ---------------------------------------------------------------------------
# Disk-cache double-faced alias lookup via get_image_path
# ---------------------------------------------------------------------------


def test_get_image_path_resolves_split_card_by_either_face(tmp_path):
    """A row stored as 'Fire // Ice' resolves when queried by either half."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-fireice.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-fireice",
        name="Fire // Ice",
        set_code="APC",
        collector_number="128",
        image_size="normal",
        file_path=image_file,
    )
    cache._path_cache.clear()

    assert cache.get_image_path("Fire", "normal") == image_file
    assert cache.get_image_path("Ice", "normal") == image_file


def test_lookup_double_faced_alias_rejects_empty_and_combined_names(tmp_path):
    """Blank names and names already containing '//' must not alias-resolve."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-fireice2.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-fireice2",
        name="Fire // Ice",
        set_code="APC",
        collector_number="128",
        image_size="normal",
        file_path=image_file,
    )

    with sqlite3.connect(cache.db_path) as conn:
        assert cache._lookup_double_faced_alias(conn, "", "normal") is None
        assert cache._lookup_double_faced_alias(conn, "   ", "normal") is None
        # A name already containing '//' is treated as a full name, not a face.
        assert cache._lookup_double_faced_alias(conn, "Wear // Tear", "normal") is None


# ---------------------------------------------------------------------------
# Other public CardImageCache lookups
# ---------------------------------------------------------------------------


def test_get_image_path_for_printing_respects_set_code(tmp_path):
    """Set-qualified lookup returns the matching printing; no set falls back to name."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    lea = cache.cache_dir / "normal" / "uuid-bolt-lea.jpg"
    m11 = cache.cache_dir / "normal" / "uuid-bolt-m11.jpg"
    lea.parent.mkdir(parents=True, exist_ok=True)
    lea.write_bytes(b"lea")
    m11.write_bytes(b"m11")
    cache.add_image(
        uuid="uuid-bolt-lea",
        name="Lightning Bolt",
        set_code="LEA",
        collector_number="161",
        image_size="normal",
        file_path=lea,
    )
    cache.add_image(
        uuid="uuid-bolt-m11",
        name="Lightning Bolt",
        set_code="M11",
        collector_number="149",
        image_size="normal",
        file_path=m11,
    )

    assert cache.get_image_path_for_printing("Lightning Bolt", "m11", "normal") == m11
    assert cache.get_image_path_for_printing("lightning bolt", "LEA", "normal") == lea
    assert cache.get_image_path_for_printing("Lightning Bolt", "ZZZ", "normal") is None
    # No set_code delegates to the plain name lookup.
    assert cache.get_image_path_for_printing("Lightning Bolt", "", "normal") in {lea, m11}


def test_get_image_paths_by_uuid_excludes_combined_face(tmp_path):
    """Multi-face listing returns faces 0..N and excludes the combined face_index=-1 row."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    front = cache.cache_dir / "normal" / "uuid-dfc.jpg"
    back = cache.cache_dir / "normal" / "uuid-dfc-f1.jpg"
    front.parent.mkdir(parents=True, exist_ok=True)
    front.write_bytes(b"front")
    back.write_bytes(b"back")
    cache.add_image(
        uuid="uuid-dfc",
        name="Front Face",
        set_code="MID",
        collector_number="1",
        image_size="normal",
        file_path=front,
        face_index=0,
    )
    cache.add_image(
        uuid="uuid-dfc",
        name="Back Face",
        set_code="MID",
        collector_number="1",
        image_size="normal",
        file_path=back,
        face_index=1,
    )
    # Combined display row points at the front face but must be excluded.
    cache.add_image(
        uuid="uuid-dfc",
        name="Front Face // Back Face",
        set_code="MID",
        collector_number="1",
        image_size="normal",
        file_path=front,
        face_index=-1,
    )

    paths = cache.get_image_paths_by_uuid("uuid-dfc", "normal")
    assert paths == [front, back]


def test_get_image_by_uuid_face_index_none_returns_any_face(tmp_path):
    """face_index=None matches any face; works when face 0 is absent."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    back = cache.cache_dir / "normal" / "uuid-back-only-f1.jpg"
    back.parent.mkdir(parents=True, exist_ok=True)
    back.write_bytes(b"back")
    cache.add_image(
        uuid="uuid-back-only",
        name="Back Face",
        set_code="MID",
        collector_number="2",
        image_size="normal",
        file_path=back,
        face_index=1,
    )

    # face_index defaults to 0, which is absent here.
    assert cache.get_image_by_uuid("uuid-back-only", "normal") is None
    # face_index=None falls back to "any face for this uuid".
    assert cache.get_image_by_uuid("uuid-back-only", "normal", face_index=None) == back


def test_get_cache_stats_counts_uniques_sizes_and_bulk_meta(tmp_path):
    """get_cache_stats reports distinct uuids, per-size counts, and bulk metadata."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    normal = cache.cache_dir / "normal" / "uuid-stats.jpg"
    small = cache.cache_dir / "small" / "uuid-stats.jpg"
    normal.parent.mkdir(parents=True, exist_ok=True)
    small.parent.mkdir(parents=True, exist_ok=True)
    normal.write_bytes(b"n")
    small.write_bytes(b"s")
    cache.add_image(
        uuid="uuid-stats",
        name="Stat Card",
        set_code="SET",
        collector_number="1",
        image_size="normal",
        file_path=normal,
    )
    cache.add_image(
        uuid="uuid-stats",
        name="Stat Card",
        set_code="SET",
        collector_number="1",
        image_size="small",
        file_path=small,
    )
    with sqlite3.connect(cache.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO bulk_data_meta (id, downloaded_at, total_cards, bulk_data_uri)
            VALUES (1, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", 1234, "http://example.com/bulk"),
        )
        conn.commit()

    stats = cache.get_cache_stats()
    assert stats["unique_cards"] == 1
    assert stats["by_size"]["normal"] == 1
    assert stats["by_size"]["small"] == 1
    assert stats["bulk_data_date"] == "2024-01-01T00:00:00Z"
    assert stats["bulk_total_cards"] == 1234


# ---------------------------------------------------------------------------
# Download / persist pipeline (session stubbed)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content: bytes = b"img", status_ok: bool = True):
        self.content = content
        self._ok = status_ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("HTTP 404")

    def iter_content(self, chunk_size: int = 1):
        """Yield the body in chunks, mirroring requests' streaming API."""
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]


class _FakeSession:
    """Minimal requests.Session stand-in recording GET calls."""

    def __init__(self, responses=None):
        # responses: dict[url] -> _FakeResponse; default returns a 200 with bytes.
        self._responses = responses or {}
        self.calls: list[str] = []
        self.headers: dict[str, str] = {}

    def get(self, url, **_kwargs):
        self.calls.append(url)
        if url in self._responses:
            return self._responses[url]
        return _FakeResponse()


def test_build_face_filename_naming():
    """Face 0 (and the combined -1 row) use the bare uuid; later faces get a -fN suffix."""
    cls = card_images.BulkImageDownloader
    assert cls._build_face_filename("abc", 0, "jpg") == "abc.jpg"
    assert cls._build_face_filename("abc", -1, "png") == "abc.png"
    assert cls._build_face_filename("abc", 1, "jpg") == "abc-f1.jpg"
    assert cls._build_face_filename("abc", 2, "png") == "abc-f2.png"


def test_download_single_image_writes_file_and_db_row(tmp_path):
    """A single-faced card downloads, writes the file, and records a face_index=0 row."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    card = {
        "id": "uuid-dl",
        "name": "Downloaded Card",
        "set": "set",
        "collector_number": "1",
        "image_uris": {"normal": "http://img/dl.jpg"},
    }
    success, message = downloader._download_single_image(card, "normal")
    assert success is True
    assert "Downloaded" in message
    assert downloader.session.calls == ["http://img/dl.jpg"]

    stored = cache.get_image_by_uuid("uuid-dl", "normal", face_index=0)
    assert stored is not None and stored.exists()
    assert stored.read_bytes() == b"img"


def test_download_face_asset_short_circuits_when_already_cached(tmp_path):
    """An already-cached face must not trigger any network call."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    existing = cache.cache_dir / "normal" / "uuid-cached.jpg"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"already")
    cache.add_image(
        uuid="uuid-cached",
        name="Cached Card",
        set_code="set",
        collector_number="1",
        image_size="normal",
        file_path=existing,
    )

    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    success, message, path = downloader._download_face_asset(
        uuid="uuid-cached",
        face_index=0,
        name="Cached Card",
        image_uris={"normal": "http://img/should-not-fetch.jpg"},
        size="normal",
        card={"set": "set"},
    )
    assert success is True
    assert "Already cached" in message
    assert path == existing
    assert downloader.session.calls == []


def test_download_face_asset_falls_back_to_normal_size(tmp_path):
    """When the requested size is missing, the 'normal' image_uri is used."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    success, _, path = downloader._download_face_asset(
        uuid="uuid-fallback",
        face_index=0,
        name="Fallback Card",
        image_uris={"normal": "http://img/normal.jpg"},  # no "large"
        size="large",
        card={"set": "set"},
    )
    assert success is True
    assert path is not None and path.exists()
    assert downloader.session.calls == ["http://img/normal.jpg"]


def test_download_face_asset_reports_missing_url(tmp_path):
    """No usable image URL => failure with no network call."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    success, message, path = downloader._download_face_asset(
        uuid="uuid-nourl",
        face_index=0,
        name="No URL Card",
        image_uris={},
        size="normal",
        card={"set": "set"},
    )
    assert success is False
    assert "No normal image" in message
    assert path is None
    assert downloader.session.calls == []


def test_download_face_asset_handles_http_error(tmp_path):
    """A non-2xx response surfaces as a failure and writes nothing."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession(
        responses={"http://img/boom.jpg": _FakeResponse(status_ok=False)}
    )

    success, message, path = downloader._download_face_asset(
        uuid="uuid-err",
        face_index=0,
        name="Erroring Card",
        image_uris={"normal": "http://img/boom.jpg"},
        size="normal",
        card={"set": "set"},
    )
    assert success is False
    assert "Error" in message
    assert path is None
    assert cache.get_image_by_uuid("uuid-err", "normal") is None


def test_download_multi_face_two_image_card_stores_faces_and_combined(tmp_path):
    """A two-image DFC stores each face plus a combined face_index=-1 front pointer."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    card = {
        "id": "uuid-mdfc",
        "name": "Front // Back",
        "set": "mid",
        "collector_number": "1",
        "card_faces": [
            {"name": "Front", "image_uris": {"normal": "http://img/front.jpg"}},
            {"name": "Back", "image_uris": {"normal": "http://img/back.jpg"}},
        ],
    }
    success, message = downloader._download_single_image(card, "normal")
    assert success is True
    assert "2 faces" in message

    paths = cache.get_image_paths_by_uuid("uuid-mdfc", "normal")
    assert len(paths) == 2
    # Combined display name resolves to the front face.
    assert cache.get_image_path("Front // Back", "normal") == paths[0]


def test_download_single_image_multi_face_split_card_one_physical_image(tmp_path):
    """A split card (faces without image_uris, one top-level image) stores a single asset."""
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    card = {
        "id": "uuid-split",
        "name": "Fire // Ice",
        "set": "apc",
        "collector_number": "128",
        "image_uris": {"normal": "http://img/fireice.jpg"},
        "card_faces": [{"name": "Fire"}, {"name": "Ice"}],
    }
    success, _ = downloader._download_single_image(card, "normal")
    assert success is True

    # Exactly one physical image was fetched for the combined card.
    assert downloader.session.calls == ["http://img/fireice.jpg"]
    stored = cache.get_image_by_uuid("uuid-split", "normal", face_index=0)
    assert stored is not None and stored.exists()
    # Both face halves resolve to that single combined image.
    assert cache.get_image_path("Fire", "normal") == stored
    assert cache.get_image_path("Ice", "normal") == stored


def test_download_bulk_metadata_uses_cache_when_current(tmp_path, monkeypatch):
    """Matching vendor metadata short-circuits without downloading."""
    downloader, _ = _make_downloader(tmp_path, monkeypatch)
    metadata = {"updated_at": "2024-01-01T00:00:00Z", "download_uri": "http://example.com/bulk"}
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: metadata)
    downloader.session = _FakeSession()

    with sqlite3.connect(downloader.cache.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO bulk_data_meta (id, downloaded_at, total_cards, bulk_data_uri)
            VALUES (1, ?, ?, ?)
            """,
            (metadata["updated_at"], 0, metadata["download_uri"]),
        )
        conn.commit()

    success, message = downloader.download_bulk_metadata()
    assert success is True
    assert "cached" in message.lower()
    # No bulk file fetch happened.
    assert downloader.session.calls == []


def test_download_bulk_metadata_rejects_missing_download_uri(tmp_path, monkeypatch):
    """A metadata payload without download_uri is an error."""
    downloader, _ = _make_downloader(tmp_path, monkeypatch)
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: {"updated_at": "x"})

    success, message = downloader.download_bulk_metadata()
    assert success is False
    assert "download URI" in message


def test_download_all_images_errors_when_bulk_file_missing(tmp_path, monkeypatch):
    """download_all_images requires the bulk file to exist first."""
    downloader, bulk_path = _make_downloader(tmp_path, monkeypatch, bulk_contents=None)
    assert not bulk_path.exists()

    result = downloader.download_all_images("normal")
    assert result["success"] is False
    assert "Bulk data not downloaded" in result["error"]


def test_download_all_images_downloads_every_card_from_bulk_file(tmp_path, monkeypatch):
    """The success path downloads each card in the bulk file and reports counts."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    result = downloader.download_all_images("normal")

    assert result["success"] is True
    # The seeded bulk file holds three cards.
    assert result["total"] == 3
    assert result["downloaded"] == 3
    assert result["skipped"] == 0
    assert result["failed"] == 0
    # Every card's image URL was fetched and persisted to the cache.
    assert set(downloader.session.calls) == {
        "http://img/bolt-lea.jpg",
        "http://img/bolt-m11.jpg",
        "http://img/fireice.jpg",
    }
    assert cache.get_image_by_uuid("u-lea", "normal").exists()
    assert cache.get_image_by_uuid("u-m11", "normal").exists()
    assert cache.get_image_by_uuid("u-fireice", "normal").exists()


def test_download_all_images_skips_already_cached_cards(tmp_path, monkeypatch):
    """A re-run over the same bulk file reports the cards as skipped, not re-downloaded."""
    cache_dir = tmp_path / "card_images"
    _write_bulk_data(cache_dir, monkeypatch)
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = card_images.BulkImageDownloader(cache)
    downloader.session = _FakeSession()

    first = downloader.download_all_images("normal")
    assert first["downloaded"] == 3

    # Fresh session so any re-fetch would be visible in calls.
    downloader.session = _FakeSession()
    second = downloader.download_all_images("normal")

    assert second["success"] is True
    assert second["skipped"] == 3
    assert second["downloaded"] == 0
    assert downloader.session.calls == []


def test_download_bulk_metadata_streams_and_records_metadata(tmp_path, monkeypatch):
    """A fresh download streams the bulk file to disk and records vendor metadata."""
    downloader, bulk_path = _make_downloader(tmp_path, monkeypatch, bulk_contents=None)
    metadata = {
        "updated_at": "2024-03-03T00:00:00Z",
        "download_uri": "http://example.com/bulk.json",
        "size": 1024,
    }
    monkeypatch.setattr(downloader, "_fetch_bulk_metadata", lambda: metadata)
    downloader.session = _FakeSession(
        responses={metadata["download_uri"]: _FakeResponse(content=b"[]")}
    )

    success, message = downloader.download_bulk_metadata()

    assert success is True
    assert "downloaded" in message.lower()
    # The bulk file was streamed to disk with the served content.
    assert bulk_path.exists()
    assert bulk_path.read_bytes() == b"[]"
    assert downloader.session.calls == [metadata["download_uri"]]
    # The vendor metadata was persisted so a subsequent run can short-circuit.
    cached_updated, cached_uri = downloader._get_cached_bulk_data_record()
    assert cached_updated == metadata["updated_at"]
    assert cached_uri == metadata["download_uri"]
