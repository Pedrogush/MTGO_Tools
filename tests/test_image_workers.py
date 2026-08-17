"""Tests for the image-service subprocess worker entrypoints.

These run in a spawned process in production (``ProcessWorker``), so they never
share the parent's imports or monkeypatches — every path they touch has to work
from the raw arguments alone. That isolation is exactly why the gzip regression
below went unnoticed: the in-process builder in ``printing_index`` was converted
to decode through ``bulk_store``, the worker's own copy of the read was not, and
no test covered the worker.
"""

from __future__ import annotations

import gzip
import json

import pytest

import services.image_service.schemas as schemas
from services.image_service.printing_index import load_printing_index_payload
from services.image_service.workers import build_printing_index_worker

CARDS = [
    {
        "id": "aaa",
        "name": "Lightning Bolt",
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "collector_number": "161",
        "released_at": "1993-08-05",
        "artist": "Christopher Rush",
    },
    {
        "id": "bbb",
        "name": "Lightning Bolt",
        "set": "m10",
        "set_name": "Magic 2010",
        "collector_number": "146",
        "released_at": "2009-07-17",
        "artist": "Christopher Moeller",
    },
    {
        "id": "ccc",
        "name": "Scalding Tarn",
        "set": "mh2",
        "set_name": "Modern Horizons 2",
        "collector_number": "254",
        "released_at": "2021-06-18",
        "artist": "Philip Straub",
    },
]


def _write_bulk(path, cards, *, compressed: bool) -> None:
    payload = json.dumps(cards).encode()
    if compressed:
        with gzip.open(path, "wb") as fh:
            fh.write(payload)
    else:
        path.write_bytes(payload)


def _run(tmp_path, *, compressed: bool):
    bulk = tmp_path / "bulk_data.json"
    _write_bulk(bulk, CARDS, compressed=compressed)
    printings = tmp_path / f"printings_v{schemas.PRINTING_INDEX_VERSION}.json"
    result = build_printing_index_worker(
        bulk_data_path=str(bulk),
        printings_path=str(printings),
        printings_version=schemas.PRINTING_INDEX_VERSION,
    )
    return result, printings


def test_builds_index_from_gzip_bulk_file(tmp_path):
    """Regression: the bulk file is gzip on disk, so the worker must decode it.

    A fresh install seeds the compressed file verbatim, so before the fix this
    raised ``msgspec.DecodeError: invalid character (byte 0)`` on every launch
    and the printings index never got built.
    """
    result, printings = _run(tmp_path, compressed=True)

    assert result["unique_names"] == 2
    assert result["total_printings"] == 3

    payload = json.loads(printings.read_bytes())
    assert [p["set"] for p in payload["data"]["lightning bolt"]] == ["M10", "LEA"]
    assert payload["data"]["scalding tarn"][0]["id"] == "ccc"


def test_builds_index_from_legacy_uncompressed_bulk_file(tmp_path):
    """An older install's uncompressed cache still loads — no forced re-download."""
    result, printings = _run(tmp_path, compressed=False)

    assert result["unique_names"] == 2
    assert result["total_printings"] == 3
    assert "lightning bolt" in json.loads(printings.read_bytes())["data"]


def test_written_index_is_readable_by_the_loader(tmp_path, monkeypatch):
    """The worker writes the format ``load_printing_index_payload`` expects.

    The worker builds the payload independently of the in-process path, so this
    pins the two together: a shape or version drift would otherwise only surface
    as a silently discarded cache at runtime.
    """
    _, printings = _run(tmp_path, compressed=True)
    monkeypatch.setattr(schemas, "PRINTING_INDEX_CACHE", printings)

    payload = load_printing_index_payload()

    assert payload is not None
    assert payload["version"] == schemas.PRINTING_INDEX_VERSION
    assert payload["unique_names"] == 2
    assert len(payload["data"]["lightning bolt"]) == 2


def test_missing_bulk_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_printing_index_worker(
            bulk_data_path=str(tmp_path / "absent.json"),
            printings_path=str(tmp_path / "printings.json"),
            printings_version=schemas.PRINTING_INDEX_VERSION,
        )
