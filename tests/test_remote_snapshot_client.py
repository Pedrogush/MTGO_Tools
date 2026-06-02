"""Tests for RemoteSnapshotClient."""

from __future__ import annotations

import json
import time

import pytest

from repositories.remote_snapshot_client import RemoteSnapshotClient, reset_remote_snapshot_client

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


def test_load_cached_manifest_returns_none_when_corrupt(client):
    client.cache_dir.mkdir(parents=True, exist_ok=True)
    client.manifest_file.write_text("{not valid json", encoding="utf-8")

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


def test_get_archetypes_returns_none_when_url_missing(client, monkeypatch):
    # Format entry exists but has no archetypes_url.
    manifest = _manifest({"modern": {"metagame_stats_url": "x"}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)

    assert client.get_archetypes_for_format("modern") is None


@pytest.mark.parametrize("bad_archetypes", [{"UR Murktide": {}}, "not-a-list", 42])
def test_get_archetypes_returns_none_on_unexpected_shape(client, monkeypatch, bad_archetypes):
    artifact_path = "data/latest/modern/archetypes.json"
    manifest = _manifest({"modern": {"archetypes_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)
    monkeypatch.setattr(client, "_get_artifact", lambda _p: _archetypes_artifact(bad_archetypes))

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


def test_get_stats_returns_none_when_manifest_unavailable(client, monkeypatch):
    monkeypatch.setattr(client, "_get_manifest", lambda: None)

    assert client.get_metagame_stats_for_format("modern") is None


def test_get_stats_returns_none_for_unknown_format(client, monkeypatch):
    monkeypatch.setattr(client, "_get_manifest", lambda: _manifest({}))

    assert client.get_metagame_stats_for_format("vintage") is None


def test_get_stats_returns_none_when_artifact_unavailable(client, monkeypatch):
    artifact_path = "data/latest/modern/metagame_stats.json"
    manifest = _manifest({"modern": {"metagame_stats_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)
    monkeypatch.setattr(client, "_get_artifact", lambda _p: None)

    assert client.get_metagame_stats_for_format("modern") is None


@pytest.mark.parametrize("bad_archetypes", [[], "not-a-dict", 42])
def test_get_stats_returns_none_on_unexpected_shape(client, monkeypatch, bad_archetypes):
    artifact_path = "data/latest/modern/metagame_stats.json"
    manifest = _manifest({"modern": {"metagame_stats_url": artifact_path}})
    monkeypatch.setattr(client, "_get_manifest", lambda: manifest)
    monkeypatch.setattr(client, "_get_artifact", lambda _p: _stats_artifact(bad_archetypes))

    assert client.get_metagame_stats_for_format("modern") is None


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
    import os

    artifact_path = "data/latest/modern/archetypes.json"
    # On-disk (stale) payload differs from the freshly downloaded one, so the
    # returned value can only have come from the download path.
    stale_artifact = _archetypes_artifact([{"name": "Living End"}])
    fresh_artifact = _archetypes_artifact([{"name": "UR Murktide"}])
    local = client._local_artifact_path(artifact_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(stale_artifact), encoding="utf-8")

    # make it look stale
    old_time = time.time() - client.max_age - 1
    os.utime(local, (old_time, old_time))

    calls = []

    def fake_download(_path, _local):
        calls.append(1)
        return fresh_artifact

    monkeypatch.setattr(client, "_download_artifact", fake_download)

    result = client._get_artifact(artifact_path)

    assert calls == [1], "stale artifact should trigger exactly one re-download"
    assert result == fresh_artifact


def test_artifact_redownloaded_when_cache_corrupt(client, monkeypatch):
    # A fresh-but-corrupt cached artifact must fall through to a re-download.
    artifact_path = "data/latest/modern/archetypes.json"
    local = client._local_artifact_path(artifact_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("{not valid json", encoding="utf-8")  # fresh mtime, invalid body

    fresh_artifact = _archetypes_artifact([{"name": "UR Murktide"}])
    calls = []

    def fake_download(_path, _local):
        calls.append(1)
        return fresh_artifact

    monkeypatch.setattr(client, "_download_artifact", fake_download)

    result = client._get_artifact(artifact_path)

    assert calls == [1], "corrupt cached artifact should trigger a re-download"
    assert result == fresh_artifact


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
# HTTP transport (HttpMixin._http_get_json)
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal context-manager standin for urllib's HTTPResponse."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


@pytest.fixture
def _force_urllib(monkeypatch):
    """Make ``import curl_cffi.requests`` raise ImportError so the urllib
    fallback path in ``_http_get_json`` is exercised deterministically,
    regardless of whether curl_cffi happens to be installed."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "curl_cffi.requests" or name.startswith("curl_cffi"):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_http_get_json_urllib_decodes_body(client, monkeypatch, _force_urllib):
    payload = {"schema_version": "1", "formats": {}}

    def fake_urlopen(url, timeout=None):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert client._http_get_json("https://example.invalid/x.json") == payload


def test_http_get_json_rejects_bad_scheme(client, monkeypatch, _force_urllib):
    # A non-http(s) scheme must be rejected before urlopen is ever called.
    def boom(*_a, **_k):
        raise AssertionError("urlopen should not be reached for a bad scheme")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    assert client._http_get_json("file:///etc/passwd") is None


def test_http_get_json_returns_none_on_network_error(client, monkeypatch, _force_urllib):
    def fake_urlopen(url, timeout=None):
        raise OSError("connection refused")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert client._http_get_json("https://example.invalid/x.json") is None
