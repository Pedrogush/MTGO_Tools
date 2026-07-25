"""Tests for first-run bulk-data seeding from a bundled snapshot."""

from __future__ import annotations

import gzip

import services.image_service.schemas as schemas
from services.image_service.seed import seed_image_cache_if_needed


def _write_gz(path, payload: bytes) -> None:
    with gzip.open(path, "wb") as fh:
        fh.write(payload)


def test_seeds_bulk_data_when_absent(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "card_images"
    target = cache_dir / "bulk_data.json"
    monkeypatch.setattr(schemas, "BULK_DATA_CACHE", target)

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    payload = b'[{"name": "Lightning Bolt"}]'
    _write_gz(seed_dir / "bulk_data.json.gz", payload)

    written = seed_image_cache_if_needed(source_dir=seed_dir)

    assert written == [target]
    assert target.read_bytes() == payload


def test_does_not_overwrite_existing_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "card_images"
    cache_dir.mkdir(parents=True)
    target = cache_dir / "bulk_data.json"
    target.write_bytes(b'[{"name": "Existing"}]')
    monkeypatch.setattr(schemas, "BULK_DATA_CACHE", target)

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    _write_gz(seed_dir / "bulk_data.json.gz", b'[{"name": "Seed"}]')

    written = seed_image_cache_if_needed(source_dir=seed_dir)

    assert written == []  # existing cache is left untouched
    assert b"Existing" in target.read_bytes()


def test_no_seed_dir_is_noop(tmp_path, monkeypatch):
    target = tmp_path / "cache" / "card_images" / "bulk_data.json"
    monkeypatch.setattr(schemas, "BULK_DATA_CACHE", target)

    # Non-existent source directory → nothing to do, no error.
    assert seed_image_cache_if_needed(source_dir=tmp_path / "missing") == []
    assert not target.exists()


def test_missing_seed_file_is_skipped(tmp_path, monkeypatch):
    target = tmp_path / "cache" / "card_images" / "bulk_data.json"
    monkeypatch.setattr(schemas, "BULK_DATA_CACHE", target)

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()  # present but empty (no bulk_data.json.gz)

    assert seed_image_cache_if_needed(source_dir=seed_dir) == []
    assert not target.exists()


def test_corrupt_seed_does_not_raise_and_leaves_no_partial(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "card_images"
    target = cache_dir / "bulk_data.json"
    monkeypatch.setattr(schemas, "BULK_DATA_CACHE", target)

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    # Not valid gzip → decompression raises, must be swallowed and leave no file.
    (seed_dir / "bulk_data.json.gz").write_bytes(b"not gzip at all")

    written = seed_image_cache_if_needed(source_dir=seed_dir)

    assert written == []
    assert not target.exists()
    # No leftover temp files in the target directory.
    assert list(cache_dir.glob("*.seedtmp")) == []
