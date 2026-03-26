"""Tests for BundleSnapshotClient."""

from __future__ import annotations

import io
import json
import tarfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from services.bundle_snapshot_client import (
    BundleSnapshotClient,
    BundleSnapshotError,
    reset_bundle_snapshot_client,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORMAT = "modern"
_SLUG = "boros-energy"


def _make_bundle(
    manifest: dict[str, Any] | None = None,
    archetypes: list[dict[str, Any]] | None = None,
    decks: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build an in-memory client-bundle.tar.gz for testing."""
    if manifest is None:
        manifest = {
            "schema_version": "1",
            "kind": "latest_manifest",
            "generated_at": "2026-03-26T12:00:00Z",
        }
    if archetypes is None:
        archetypes = [
            {
                "schema_version": "1",
                "kind": "archetype_list",
                "format": _FORMAT,
                "archetypes": [{"name": "Boros Energy", "href": _SLUG}],
            }
        ]
    if decks is None:
        decks = [
            {
                "schema_version": "1",
                "kind": "archetype_decks",
                "format": _FORMAT,
                "archetype": {"name": "Boros Energy", "href": _SLUG},
                "decks": [
                    {
                        "date": "2026-03-25",
                        "number": "1234",
                        "player": "player1",
                        "event": "Modern League",
                        "result": "5-0",
                        "name": _SLUG,
                        "source": "mtggoldfish",
                    }
                ],
            }
        ]

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:

        def _add(name: str, data: dict) -> None:
            raw = json.dumps(data).encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))

        _add("latest/latest.json", manifest)
        for arch in archetypes:
            fmt = arch.get("format", "modern")
            _add(f"latest/archetypes/{fmt}.json", arch)
        for deck_entry in decks:
            fmt = deck_entry.get("format", "modern")
            href = deck_entry.get("archetype", {}).get("href", "unknown")
            _add(f"latest/decks/{fmt}/{href}.json", deck_entry)

    return buf.getvalue()


@pytest.fixture
def tmp_client(tmp_path: Path) -> BundleSnapshotClient:
    """Return a BundleSnapshotClient wired to tmp_path files."""
    return BundleSnapshotClient(
        base_url="https://example.com",
        bundle_path="data/latest/client-bundle.tar.gz",
        archetype_list_cache_file=tmp_path / "archetype_list.json",
        archetype_decks_cache_file=tmp_path / "archetype_decks.json",
        stamp_file=tmp_path / "bundle_stamp.json",
        max_age=3600,
        request_timeout=30,
    )


# ---------------------------------------------------------------------------
# Stamp freshness
# ---------------------------------------------------------------------------


def test_stamp_fresh_skips_download(tmp_client: BundleSnapshotClient) -> None:
    tmp_client.stamp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_client.stamp_file.write_text(
        json.dumps({"applied_at": time.time(), "generated_at": "2026-03-26T12:00:00Z"}),
        encoding="utf-8",
    )
    with patch.object(tmp_client, "_download_bundle") as mock_dl:
        result = tmp_client.apply()
    mock_dl.assert_not_called()
    assert result is False


def test_stale_stamp_triggers_download(tmp_client: BundleSnapshotClient) -> None:
    tmp_client.stamp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_client.stamp_file.write_text(
        json.dumps({"applied_at": time.time() - 9999, "generated_at": "old"}),
        encoding="utf-8",
    )
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        result = tmp_client.apply()
    assert result is True


def test_missing_stamp_triggers_download(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        result = tmp_client.apply()
    assert result is True


# ---------------------------------------------------------------------------
# Apply — cache hydration
# ---------------------------------------------------------------------------


def test_apply_writes_archetype_list_cache(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    data = json.loads(tmp_client.archetype_list_cache_file.read_text())
    assert _FORMAT in data
    items = data[_FORMAT]["items"]
    assert len(items) == 1
    assert items[0]["href"] == _SLUG


def test_apply_writes_archetype_decks_cache(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    data = json.loads(tmp_client.archetype_decks_cache_file.read_text())
    assert _SLUG in data
    items = data[_SLUG]["items"]
    assert len(items) == 1
    assert items[0]["number"] == "1234"


def test_apply_writes_stamp_file(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    stamp = json.loads(tmp_client.stamp_file.read_text())
    assert stamp["generated_at"] == "2026-03-26T12:00:00Z"
    assert "applied_at" in stamp


def test_apply_merges_with_existing_archetype_list_cache(tmp_client: BundleSnapshotClient) -> None:
    existing = {"legacy": {"timestamp": 1.0, "items": [{"name": "ANT", "href": "ant"}]}}
    tmp_client.archetype_list_cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_client.archetype_list_cache_file.write_text(json.dumps(existing), encoding="utf-8")

    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    data = json.loads(tmp_client.archetype_list_cache_file.read_text())
    assert "legacy" in data  # original preserved
    assert _FORMAT in data  # new entry added


def test_apply_multiple_formats(tmp_client: BundleSnapshotClient) -> None:
    archetypes = [
        {
            "schema_version": "1",
            "kind": "archetype_list",
            "format": "modern",
            "archetypes": [{"name": "X", "href": "x"}],
        },
        {
            "schema_version": "1",
            "kind": "archetype_list",
            "format": "legacy",
            "archetypes": [{"name": "Y", "href": "y"}],
        },
    ]
    bundle = _make_bundle(archetypes=archetypes, decks=[])
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    data = json.loads(tmp_client.archetype_list_cache_file.read_text())
    assert "modern" in data
    assert "legacy" in data


# ---------------------------------------------------------------------------
# Download failure
# ---------------------------------------------------------------------------


def test_download_failure_raises_bundle_error(tmp_client: BundleSnapshotClient) -> None:
    with patch.object(tmp_client, "_http_get_bytes", return_value=None):
        with pytest.raises(BundleSnapshotError):
            tmp_client.apply()


def test_stamp_not_written_on_download_failure(tmp_client: BundleSnapshotClient) -> None:
    with patch.object(tmp_client, "_http_get_bytes", return_value=None):
        with pytest.raises(BundleSnapshotError):
            tmp_client.apply()
    assert not tmp_client.stamp_file.exists()


# ---------------------------------------------------------------------------
# Malformed bundle entries are skipped gracefully
# ---------------------------------------------------------------------------


def test_malformed_archetype_entry_skipped(tmp_client: BundleSnapshotClient) -> None:
    archetypes = [
        {
            "schema_version": "1",
            "kind": "archetype_list",
            "format": "modern",
            "archetypes": [{"name": "X", "href": "x"}],
        },
        {"schema_version": "1", "kind": "archetype_list"},  # missing format
    ]
    bundle = _make_bundle(archetypes=archetypes, decks=[])
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()  # should not raise

    data = json.loads(tmp_client.archetype_list_cache_file.read_text())
    assert "modern" in data


def test_deck_entry_missing_href_skipped(tmp_client: BundleSnapshotClient) -> None:
    decks = [
        {
            "schema_version": "1",
            "kind": "archetype_decks",
            "format": "modern",
            "archetype": {},  # missing href
            "decks": [{"number": "1"}],
        }
    ]
    bundle = _make_bundle(decks=decks)
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()  # should not raise


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_singleton_reset() -> None:
    from services.bundle_snapshot_client import get_bundle_snapshot_client

    reset_bundle_snapshot_client()
    c1 = get_bundle_snapshot_client()
    c2 = get_bundle_snapshot_client()
    assert c1 is c2
    reset_bundle_snapshot_client()
