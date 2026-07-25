"""Tests for first-run bulk-data seeding from a bundled snapshot.

The cache stores the bulk file gzip-compressed, which is the seed's own format,
so seeding is a verbatim copy of ``bulk_data.json.gz`` onto ``bulk_data.json``;
readers decompress it in memory via ``bulk_store.decode_bulk_bytes``.
"""

from __future__ import annotations

import gzip

import services.image_service.schemas as schemas
import services.image_service.seed as seed_module
from services.image_service.bulk_store import decode_bulk_bytes
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
    gz = seed_dir / "bulk_data.json.gz"
    _write_gz(gz, payload)

    written = seed_image_cache_if_needed(source_dir=seed_dir)

    assert written == [target]
    # Copied verbatim (still gzip on disk) and decodes back to the payload.
    assert target.read_bytes() == gz.read_bytes()
    assert decode_bulk_bytes(target.read_bytes()) == payload


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


def test_copy_failure_is_swallowed_and_leaves_no_partial(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "card_images"
    target = cache_dir / "bulk_data.json"
    monkeypatch.setattr(schemas, "BULK_DATA_CACHE", target)

    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    _write_gz(seed_dir / "bulk_data.json.gz", b'[{"name": "Seed"}]')

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(seed_module.shutil, "copyfileobj", _boom)

    written = seed_image_cache_if_needed(source_dir=seed_dir)

    assert written == []
    assert not target.exists()
    # The temp file is cleaned up on failure.
    assert list(cache_dir.glob("*.seedtmp")) == []
