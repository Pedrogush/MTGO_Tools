"""Tests for RemoteSnapshotClient."""

from __future__ import annotations

import json
import time

import pytest

from services.remote_snapshot_client import RemoteSnapshotClient, reset_remote_snapshot_client

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SCHEMA = "1"


def _manifest(formats: dict | None = None) -> dict:
    return {
        "schema_version": _SCHEMA,
        "generated_at": "2025-03-24T00:00:00Z",
        "formats": formats or {},
    }


def _archetypes_artifact(archetypes: list) -> dict:
    return {
        "schema_version": _SCHEMA,
        "format": "modern",
        "generated_at": "2025-03-24T00:00:00Z",
        "archetypes": archetypes,
    }


def _stats_artifact(archetypes: dict) -> dict:
    return {
        "schema_version": _SCHEMA,
        "format": "modern",
        "generated_at": "2025-03-24T00:00:00Z",
        "archetypes": archetypes,
    }


@pytest.fixture(autouse=True)
def reset_singleton():
    yield
    reset_remote_snapshot_client()


@pytest.fixture
def client(tmp_path):
    cache_dir = tmp_path / "snap"
    manifest_file = cache_dir / "manifest.json"
    return RemoteSnapshotClient(
        base_url="https://example.invalid",
        cache_dir=cache_dir,
        manifest_file=manifest_file,
        max_age=3600,
    )


def _write_manifest_cache(client: RemoteSnapshotClient, manifest: dict) -> None:
    client.cache_dir.mkdir(parents=True, exist_ok=True)
    envelope = {"_cached_at": time.time(), "manifest": manifest}
    client.manifest_file.write_text(json.dumps(envelope), encoding="utf-8")


def _write_artifact(client: RemoteSnapshotClient, artifact_path: str, data: dict) -> None:
    local = client._local_artifact_path(artifact_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Manifest caching
# ---------------------------------------------------------------------------


def test_load_cached_manifest_returns_none_when_missing(client):
    assert client._load_cached_manifest() is None


def test_load_cached_manifest_returns_none_when_stale(client):
    client.cache_dir.mkdir(parents=True, exist_ok=True)
    stale = {"_cached_at": time.time() - 7200, "manifest": _manifest()}
    client.manifest_file.write_text(json.dumps(stale), encoding="utf-8")

    assert client._load_cached_manifest() is None


def test_load_cached_manifest_returns_data_when_fresh(client):
    manifest = _manifest({"modern": {"archetypes_url": "data/latest/modern/archetypes.json"}})
    _write_manifest_cache(client, manifest)

    result = client._load_cached_manifest()

    assert result is not None
    assert "modern" in result["formats"]


def test_fetch_manifest_rejects_wrong_schema_version(client, monkeypatch):
    bad_manifest = {"schema_version": "99", "formats": {}}
    monkeypatch.setattr(client, "_http_get_json", lambda _url: bad_manifest)

    assert client._fetch_and_cache_manifest() is None


def test_fetch_manifest_caches_on_success(client, monkeypatch):
    manifest = _manifest({"modern": {"archetypes_url": "x"}})
    monkeypatch.setattr(client, "_http_get_json", lambda _url: manifest)

    result = client._fetch_and_cache_manifest()

    assert result is not None
    assert client.manifest_file.exists()
    cached = json.loads(client.manifest_file.read_text(encoding="utf-8"))
    assert cached["manifest"]["formats"]["modern"]["archetypes_url"] == "x"


# ---------------------------------------------------------------------------
# get_archetypes_for_format
# ---------------------------------------------------------------------------


def test_get_archetypes_returns_none_when_manifest_unavailable(client, monkeypatch):
    monkeypatch.setattr(client, "_get_manifest", lambda: None)

    assert client.get_archetypes_for_format("modern") is None


def test_get_archetypes_returns_none_for_unknown_format(client, monkeypatch):
    monkeypatch.setattr(client, "_get_manifest", lambda: _manifest({}))

    assert client.get_archetypes_for_format("vintage") is None


def test_get_archetypes_returns_list_from_artifact(client, monkeypatch):
    artifact_path = "data/latest/modern/archetypes.json"
    manifest = _manifest({"modern": {"archetypes_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)

    expected = [{"name": "UR Murktide", "href": "/archetype/modern-ur-murktide"}]
    artifact = _archetypes_artifact(expected)
    monkeypatch.setattr(client, "_get_artifact", lambda _path: artifact)

    result = client.get_archetypes_for_format("modern")

    assert result == expected


def test_get_archetypes_is_case_insensitive(client, monkeypatch):
    artifact_path = "data/latest/modern/archetypes.json"
    manifest = _manifest({"modern": {"archetypes_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)

    archetypes = [{"name": "UR Murktide"}]
    monkeypatch.setattr(client, "_get_artifact", lambda _p: _archetypes_artifact(archetypes))

    assert client.get_archetypes_for_format("Modern") == archetypes
    assert client.get_archetypes_for_format("MODERN") == archetypes


def test_get_archetypes_returns_none_when_artifact_unavailable(client, monkeypatch):
    artifact_path = "data/latest/modern/archetypes.json"
    manifest = _manifest({"modern": {"archetypes_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)
    monkeypatch.setattr(client, "_get_artifact", lambda _p: None)

    assert client.get_archetypes_for_format("modern") is None


# ---------------------------------------------------------------------------
# get_metagame_stats_for_format
# ---------------------------------------------------------------------------


def test_get_stats_returns_none_when_no_stats_url(client, monkeypatch):
    manifest = _manifest({"modern": {"archetypes_url": "x"}})  # no metagame_stats_url
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)

    assert client.get_metagame_stats_for_format("modern") is None


def test_get_stats_normalises_to_expected_shape(client, monkeypatch):
    artifact_path = "data/latest/modern/metagame_stats.json"
    manifest = _manifest({"modern": {"metagame_stats_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)

    raw_archetypes = {
        "UR Murktide": {"results": {"2025-03-24": 5, "2025-03-23": 3}},
        "Amulet Titan": {"results": {"2025-03-24": 2}},
    }
    monkeypatch.setattr(client, "_get_artifact", lambda _p: _stats_artifact(raw_archetypes))

    result = client.get_metagame_stats_for_format("modern")

    assert result is not None
    assert "modern" in result
    fmt_data = result["modern"]
    assert "timestamp" in fmt_data
    assert fmt_data["UR Murktide"]["results"]["2025-03-24"] == 5
    assert fmt_data["Amulet Titan"]["results"]["2025-03-24"] == 2


# ---------------------------------------------------------------------------
# Artifact caching
# ---------------------------------------------------------------------------


def test_artifact_served_from_disk_cache_when_fresh(client, monkeypatch):
    artifact_path = "data/latest/modern/archetypes.json"
    artifact = _archetypes_artifact([{"name": "Living End"}])
    _write_artifact(client, artifact_path, artifact)

    calls = []
    monkeypatch.setattr(client, "_download_artifact", lambda *_: calls.append(1) or None)

    result = client._get_artifact(artifact_path)

    assert result is not None
    assert calls == [], "should not re-download a fresh artifact"


def test_artifact_redownloaded_when_stale(client, monkeypatch):
    artifact_path = "data/latest/modern/archetypes.json"
    artifact = _archetypes_artifact([{"name": "Living End"}])
    local = client._local_artifact_path(artifact_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(artifact), encoding="utf-8")

    # make it look stale
    old_time = time.time() - client.max_age - 1
    import os

    os.utime(local, (old_time, old_time))

    downloaded = [artifact]

    def fake_download(_path, _local):
        return downloaded[0]

    monkeypatch.setattr(client, "_download_artifact", fake_download)

    result = client._get_artifact(artifact_path)
    assert result == artifact


def test_download_artifact_rejects_wrong_schema(client, monkeypatch):
    bad = {"schema_version": "99", "archetypes": []}
    monkeypatch.setattr(client, "_http_get_json", lambda _url: bad)

    result = client._download_artifact(
        "data/latest/modern/archetypes.json",
        client._local_artifact_path("data/latest/modern/archetypes.json"),
    )

    assert result is None


def test_download_artifact_writes_to_disk(client, monkeypatch):
    artifact = _archetypes_artifact([{"name": "UR Murktide"}])
    monkeypatch.setattr(client, "_http_get_json", lambda _url: artifact)

    local = client._local_artifact_path("data/latest/modern/archetypes.json")
    result = client._download_artifact("data/latest/modern/archetypes.json", local)

    assert result is not None
    assert local.exists()
    assert json.loads(local.read_text())["archetypes"][0]["name"] == "UR Murktide"


# ---------------------------------------------------------------------------
# get_decks_for_archetype
# ---------------------------------------------------------------------------

_SAMPLE_DECKS = [
    {
        "date": "2025-03-24",
        "number": "123456",
        "player": "SomePlayer",
        "event": "Modern Challenge",
        "result": "4-0",
        "name": "modern-ur-murktide",
        "source": "mtggoldfish",
        "deck_text": "4 Murktide Regent\n",
    }
]


def _decks_artifact(decks: list, slug: str = "modern-ur-murktide") -> dict:
    return {
        "schema_version": _SCHEMA,
        "format": "modern",
        "archetype": slug,
        "generated_at": "2025-03-24T00:00:00Z",
        "decks": decks,
    }


def test_get_decks_returns_list_from_artifact(client, monkeypatch):
    monkeypatch.setattr(client, "_get_artifact", lambda _path: _decks_artifact(_SAMPLE_DECKS))

    result = client.get_decks_for_archetype("modern", "modern-ur-murktide")

    assert result == _SAMPLE_DECKS


def test_get_decks_is_case_insensitive(client, monkeypatch):
    monkeypatch.setattr(client, "_get_artifact", lambda _path: _decks_artifact(_SAMPLE_DECKS))

    assert client.get_decks_for_archetype("Modern", "modern-ur-murktide") == _SAMPLE_DECKS
    assert client.get_decks_for_archetype("MODERN", "modern-ur-murktide") == _SAMPLE_DECKS


def test_get_decks_returns_none_when_artifact_unavailable(client, monkeypatch):
    monkeypatch.setattr(client, "_get_artifact", lambda _path: None)

    assert client.get_decks_for_archetype("modern", "modern-ur-murktide") is None


def test_get_decks_returns_none_on_unexpected_shape(client, monkeypatch):
    bad_artifact = {"schema_version": _SCHEMA, "format": "modern", "decks": "not-a-list"}
    monkeypatch.setattr(client, "_get_artifact", lambda _path: bad_artifact)

    assert client.get_decks_for_archetype("modern", "modern-ur-murktide") is None


def test_get_decks_constructs_path_from_format_and_slug(client, monkeypatch):
    captured = []

    def capture_path(path):
        captured.append(path)
        return _decks_artifact(_SAMPLE_DECKS)

    monkeypatch.setattr(client, "_get_artifact", capture_path)
    client.get_decks_for_archetype("legacy", "legacy-eldrazi-post")

    assert captured == ["data/latest/legacy/decks/legacy-eldrazi-post.json"]


def test_get_decks_artifact_is_cached_on_disk(client, monkeypatch):
    artifact = _decks_artifact(_SAMPLE_DECKS)
    _write_artifact(client, "data/latest/modern/decks/modern-ur-murktide.json", artifact)

    download_calls = []
    monkeypatch.setattr(client, "_download_artifact", lambda *_: download_calls.append(1) or None)

    result = client.get_decks_for_archetype("modern", "modern-ur-murktide")

    assert result == _SAMPLE_DECKS
    assert download_calls == [], "should serve from disk cache without re-downloading"
