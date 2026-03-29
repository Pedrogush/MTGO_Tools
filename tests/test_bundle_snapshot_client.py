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

from repositories.format_card_pool_repository import FormatCardPoolRepository
from repositories.radar_repository import RadarRepository
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
    deck_texts: list[dict[str, Any]] | None = None,
    card_pools: list[dict[str, Any]] | None = None,
    radars: list[dict[str, Any]] | None = None,
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
    if deck_texts is None:
        deck_texts = [
            {
                "schema_version": "1",
                "kind": "deck_text_blob",
                "format": _FORMAT,
                "source": "mtggoldfish",
                "deck_id": "1234",
                "deck_text": "4 Lightning Bolt\n\nSideboard\n2 Smash to Smithereens\n",
            }
        ]
    if card_pools is None:
        card_pools = [
            {
                "schema_version": "1",
                "kind": "format_card_pool",
                "format": _FORMAT,
                "generated_at": "2026-03-26T12:00:00Z",
                "source": "published-deck-texts",
                "total_decks_analyzed": 50,
                "decks_failed": 0,
                "cards": ["Lightning Bolt", "Counterspell"],
                "copy_totals": [
                    {"card_name": "Lightning Bolt", "copies_played": 200},
                    {"card_name": "Counterspell", "copies_played": 75},
                ],
            }
        ]
    if radars is None:
        radars = [
            {
                "schema_version": "1",
                "kind": "archetype_radar",
                "format": _FORMAT,
                "generated_at": "2026-03-26T12:00:00Z",
                "source": "published-deck-texts",
                "archetype": {"name": "Boros Energy", "href": _SLUG},
                "total_decks_analyzed": 50,
                "decks_failed": 0,
                "mainboard_cards": [
                    {
                        "card_name": "Lightning Bolt",
                        "appearances": 50,
                        "total_copies": 200,
                        "max_copies": 4,
                        "avg_copies": 4.0,
                        "inclusion_rate": 100.0,
                        "expected_copies": 4.0,
                        "copy_distribution": {"4": 50},
                    }
                ],
                "sideboard_cards": [
                    {
                        "card_name": "Counterspell",
                        "appearances": 25,
                        "total_copies": 50,
                        "max_copies": 2,
                        "avg_copies": 2.0,
                        "inclusion_rate": 50.0,
                        "expected_copies": 1.0,
                        "copy_distribution": {"2": 25, "0": 25},
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
        for dt in deck_texts:
            fmt = dt.get("format", "modern")
            deck_id = dt.get("deck_id", "0")
            _add(f"archive/deck-texts/{fmt}/{deck_id}.json", dt)
        for card_pool in card_pools:
            fmt = card_pool.get("format", "modern")
            _add(f"latest/card-pools/{fmt}.json", card_pool)
        for radar in radars:
            fmt = radar.get("format", "modern")
            href = radar.get("archetype", {}).get("href", "unknown")
            _add(f"latest/radars/{fmt}/{href}.json", radar)

    return buf.getvalue()


@pytest.fixture
def tmp_client(tmp_path: Path) -> BundleSnapshotClient:
    """Return a BundleSnapshotClient wired to tmp_path files."""
    return BundleSnapshotClient(
        base_url="https://example.com",
        bundle_path="data/latest/client-bundle.tar.gz",
        archetype_list_cache_file=tmp_path / "archetype_list.json",
        archetype_decks_cache_file=tmp_path / "archetype_decks.json",
        format_card_pool_db_file=tmp_path / "format_card_pool.db",
        radar_db_file=tmp_path / "radar_cache.db",
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
    updated, archetypes_by_format = result
    assert updated is False
    assert archetypes_by_format is None


def test_stale_stamp_triggers_download(tmp_client: BundleSnapshotClient) -> None:
    tmp_client.stamp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_client.stamp_file.write_text(
        json.dumps({"applied_at": time.time() - 9999, "generated_at": "old"}),
        encoding="utf-8",
    )
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        result = tmp_client.apply()
    updated, _ = result
    assert updated is True


def test_missing_stamp_triggers_download(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        result = tmp_client.apply()
    updated, _ = result
    assert updated is True


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


def test_apply_writes_format_card_pool_db(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    repo = FormatCardPoolRepository(tmp_client.format_card_pool_db_file)
    summary = repo.get_summary(_FORMAT)
    assert summary is not None
    assert summary.total_decks_analyzed == 50
    assert "Lightning Bolt" in repo.get_card_names(_FORMAT)
    assert repo.get_top_cards(_FORMAT, limit=1)[0].copies_played == 200


def test_apply_writes_radar_db(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()

    repo = RadarRepository(tmp_client.radar_db_file)
    radar = repo.get_radar(_FORMAT, _SLUG)
    assert radar is not None
    assert radar.archetype_name == "Boros Energy"
    assert radar.mainboard_cards[0].card_name == "Lightning Bolt"
    assert radar.sideboard_cards[0].card_name == "Counterspell"


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
# Deck text hydration
# ---------------------------------------------------------------------------


def test_apply_hydrates_deck_text_cache(tmp_client: BundleSnapshotClient, tmp_path: Path) -> None:
    from utils.deck_text_cache import DeckTextCache

    db_path = tmp_path / "deck_cache.db"
    cache = DeckTextCache(db_path=db_path)

    bundle = _make_bundle()
    with (
        patch.object(tmp_client, "_http_get_bytes", return_value=bundle),
        patch("utils.deck_text_cache.get_deck_cache", return_value=cache),
    ):
        tmp_client.apply()

    result = cache.get("1234")
    assert result is not None
    assert "Lightning Bolt" in result


def test_deck_text_hydration_skips_existing(
    tmp_client: BundleSnapshotClient, tmp_path: Path
) -> None:
    from utils.deck_text_cache import DeckTextCache

    db_path = tmp_path / "deck_cache.db"
    cache = DeckTextCache(db_path=db_path)
    cache.set("1234", "4 Existing Card\n", source="mtggoldfish")

    bundle = _make_bundle()
    with (
        patch.object(tmp_client, "_http_get_bytes", return_value=bundle),
        patch("utils.deck_text_cache.get_deck_cache", return_value=cache),
    ):
        tmp_client._hydrate_deck_texts([("1234", "4 Lightning Bolt\n", "mtggoldfish")])

    # Original entry preserved (INSERT OR IGNORE)
    assert cache.get("1234") == "4 Existing Card\n"


def test_deck_text_entry_missing_deck_id_skipped(tmp_client: BundleSnapshotClient) -> None:
    deck_texts = [
        {
            "schema_version": "1",
            "kind": "deck_text_blob",
            "format": "modern",
            "source": "mtggoldfish",
            "deck_id": "",  # empty
            "deck_text": "4 Lightning Bolt\n",
        }
    ]
    bundle = _make_bundle(deck_texts=deck_texts)
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        tmp_client.apply()  # should not raise


# ---------------------------------------------------------------------------
# apply() return value — archetypes_by_format
# ---------------------------------------------------------------------------


def test_apply_returns_archetypes_by_format(tmp_client: BundleSnapshotClient) -> None:
    bundle = _make_bundle()
    with patch.object(tmp_client, "_http_get_bytes", return_value=bundle):
        updated, archetypes_by_format = tmp_client.apply()

    assert updated is True
    assert archetypes_by_format is not None
    assert _FORMAT in archetypes_by_format
    items = archetypes_by_format[_FORMAT]
    assert len(items) == 1
    assert items[0]["href"] == _SLUG


def test_apply_returns_archetypes_for_all_formats(tmp_client: BundleSnapshotClient) -> None:
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
        updated, archetypes_by_format = tmp_client.apply()

    assert updated is True
    assert archetypes_by_format is not None
    assert "modern" in archetypes_by_format
    assert "legacy" in archetypes_by_format
    assert archetypes_by_format["modern"][0]["href"] == "x"
    assert archetypes_by_format["legacy"][0]["href"] == "y"


def test_apply_returns_none_archetypes_when_stamp_fresh(tmp_client: BundleSnapshotClient) -> None:
    tmp_client.stamp_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_client.stamp_file.write_text(
        json.dumps({"applied_at": time.time(), "generated_at": "2026-03-26T12:00:00Z"}),
        encoding="utf-8",
    )
    updated, archetypes_by_format = tmp_client.apply()
    assert updated is False
    assert archetypes_by_format is None


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
