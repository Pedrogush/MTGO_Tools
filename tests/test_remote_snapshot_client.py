"""Tests for RemoteSnapshotClient.

These drive the public API through the *real* manifest -> artifact -> disk ->
cache stack and stub only ``_http_get_json`` — the network boundary the client
owns (guideline 2: mock only network/scraping, never the UUT's own internals).
A small URL->payload routing table stands in for the remote server, so every
test exercises real key lookups, ``.lower()`` casing, on-disk staging, and
cache-vs-fetch decisions.
"""

from __future__ import annotations

import json
import time

import pytest

from repositories.remote_snapshot_client import (
    RemoteSnapshotClient,
    get_remote_snapshot_client,
    reset_remote_snapshot_client,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SCHEMA = "1"
_BASE_URL = "https://example.invalid"


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
        base_url=_BASE_URL,
        cache_dir=cache_dir,
        manifest_file=manifest_file,
        max_age=3600,
    )


class _FakeServer:
    """Stands in for the remote HTTP server.

    Routes URLs (``{base}/{path}``) to canned JSON payloads and records how many
    times each URL was fetched, so tests can assert real cache behaviour through
    the live stack instead of stubbing the client's own internals.
    """

    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")
        self.payloads: dict[str, dict | None] = {}
        self.calls: dict[str, int] = {}

    def serve(self, path: str, payload: dict | None) -> None:
        self.payloads[f"{self._base}/{path}"] = payload

    def get(self, url: str) -> dict | None:
        self.calls[url] = self.calls.get(url, 0) + 1
        return self.payloads.get(url)

    def call_count(self, path: str) -> int:
        return self.calls.get(f"{self._base}/{path}", 0)


@pytest.fixture
def server(client, monkeypatch):
    """A fake remote server wired into the real ``_http_get_json`` seam."""
    fake = _FakeServer(client.base_url)
    monkeypatch.setattr(client, "_http_get_json", fake.get)
    return fake


_MANIFEST_PATH = "data/latest/manifest.json"


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


def test_get_manifest_caches_across_calls(client, server):
    """The real ``_get_manifest`` should fetch once, then serve from disk."""
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": "x"}}))

    first = client._get_manifest()
    second = client._get_manifest()

    assert first is not None
    assert second is not None
    assert "modern" in second["formats"]
    assert server.call_count(_MANIFEST_PATH) == 1, "fresh cached manifest must not refetch"


# ---------------------------------------------------------------------------
# get_archetypes_for_format — through the real manifest+artifact stack
# ---------------------------------------------------------------------------


def test_get_archetypes_returns_none_when_manifest_unavailable(client, server):
    server.serve(_MANIFEST_PATH, None)  # network returns nothing

    assert client.get_archetypes_for_format("modern") is None


def test_get_archetypes_returns_none_for_unknown_format(client, server):
    server.serve(_MANIFEST_PATH, _manifest({}))

    assert client.get_archetypes_for_format("vintage") is None


def test_get_archetypes_returns_list_through_full_stack(client, server):
    artifact_path = "data/latest/modern/archetypes.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": artifact_path}}))

    expected = [{"name": "UR Murktide", "href": "/archetype/modern-ur-murktide"}]
    server.serve(artifact_path, _archetypes_artifact(expected))

    result = client.get_archetypes_for_format("modern")

    assert result == expected
    # The artifact must have been staged to disk by the real download path.
    assert client._local_artifact_path(artifact_path).exists()


def test_get_archetypes_is_case_insensitive(client, server):
    artifact_path = "data/latest/modern/archetypes.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": artifact_path}}))

    archetypes = [{"name": "UR Murktide"}]
    server.serve(artifact_path, _archetypes_artifact(archetypes))

    assert client.get_archetypes_for_format("Modern") == archetypes
    assert client.get_archetypes_for_format("MODERN") == archetypes


def test_get_archetypes_returns_none_when_artifact_unavailable(client, server):
    artifact_path = "data/latest/modern/archetypes.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": artifact_path}}))
    server.serve(artifact_path, None)  # artifact fetch fails

    assert client.get_archetypes_for_format("modern") is None


def test_get_archetypes_returns_none_when_url_missing(client, server):
    # Format entry exists but has no archetypes_url.
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"metagame_stats_url": "x"}}))

    assert client.get_archetypes_for_format("modern") is None


@pytest.mark.parametrize("bad_archetypes", [{"UR Murktide": {}}, "not-a-list", 42])
def test_get_archetypes_returns_none_on_unexpected_shape(client, server, bad_archetypes):
    artifact_path = "data/latest/modern/archetypes.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": artifact_path}}))
    server.serve(artifact_path, _archetypes_artifact(bad_archetypes))

    assert client.get_archetypes_for_format("modern") is None


# ---------------------------------------------------------------------------
# get_metagame_stats_for_format — through the real manifest+artifact stack
# ---------------------------------------------------------------------------


def test_get_stats_returns_none_when_no_stats_url(client, server):
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": "x"}}))

    assert client.get_metagame_stats_for_format("modern") is None


def test_get_stats_normalises_to_expected_shape(client, server):
    artifact_path = "data/latest/modern/metagame_stats.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"metagame_stats_url": artifact_path}}))

    raw_archetypes = {
        "UR Murktide": {"results": {"2025-03-24": 5, "2025-03-23": 3}},
        "Amulet Titan": {"results": {"2025-03-24": 2}},
    }
    server.serve(artifact_path, _stats_artifact(raw_archetypes))

    before = time.time()
    result = client.get_metagame_stats_for_format("modern")
    after = time.time()

    assert result is not None
    assert "modern" in result
    fmt_data = result["modern"]
    timestamp = fmt_data["timestamp"]
    assert isinstance(timestamp, float)
    assert before <= timestamp <= after, "timestamp should be the current time"
    assert fmt_data["UR Murktide"]["results"]["2025-03-24"] == 5
    assert fmt_data["Amulet Titan"]["results"]["2025-03-24"] == 2


def test_get_stats_returns_none_when_manifest_unavailable(client, server):
    server.serve(_MANIFEST_PATH, None)

    assert client.get_metagame_stats_for_format("modern") is None


def test_get_stats_returns_none_for_unknown_format(client, server):
    server.serve(_MANIFEST_PATH, _manifest({}))

    assert client.get_metagame_stats_for_format("vintage") is None


def test_get_stats_returns_none_when_artifact_unavailable(client, server):
    artifact_path = "data/latest/modern/metagame_stats.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"metagame_stats_url": artifact_path}}))
    server.serve(artifact_path, None)

    assert client.get_metagame_stats_for_format("modern") is None


@pytest.mark.parametrize("bad_archetypes", [[], "not-a-dict", 42])
def test_get_stats_returns_none_on_unexpected_shape(client, server, bad_archetypes):
    artifact_path = "data/latest/modern/metagame_stats.json"
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"metagame_stats_url": artifact_path}}))
    server.serve(artifact_path, _stats_artifact(bad_archetypes))

    assert client.get_metagame_stats_for_format("modern") is None


# ---------------------------------------------------------------------------
# is_available — exercises the real manifest stack
# ---------------------------------------------------------------------------


def test_is_available_true_when_manifest_fetches(client, server):
    server.serve(_MANIFEST_PATH, _manifest({"modern": {"archetypes_url": "x"}}))

    assert client.is_available() is True


def test_is_available_false_when_manifest_missing(client, server):
    server.serve(_MANIFEST_PATH, None)

    assert client.is_available() is False


# ---------------------------------------------------------------------------
# Artifact caching
# ---------------------------------------------------------------------------


def test_artifact_served_from_disk_cache_when_fresh(client, server):
    artifact_path = "data/latest/modern/archetypes.json"
    artifact = _archetypes_artifact([{"name": "Living End"}])
    _write_artifact(client, artifact_path, artifact)

    # Serve a *different* body so any network hit would be detectable.
    server.serve(artifact_path, _archetypes_artifact([{"name": "UR Murktide"}]))

    result = client._get_artifact(artifact_path)

    assert result == artifact, "fresh on-disk artifact must be returned verbatim"
    assert server.call_count(artifact_path) == 0, "should not re-download a fresh artifact"


def test_artifact_redownloaded_when_stale(client, server):
    import os

    artifact_path = "data/latest/modern/archetypes.json"
    # On-disk (stale) payload differs from the served one, so the returned value
    # can only have come from the download path.
    stale_artifact = _archetypes_artifact([{"name": "Living End"}])
    fresh_artifact = _archetypes_artifact([{"name": "UR Murktide"}])
    local = client._local_artifact_path(artifact_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(stale_artifact), encoding="utf-8")

    # make it look stale
    old_time = time.time() - client.max_age - 1
    os.utime(local, (old_time, old_time))

    server.serve(artifact_path, fresh_artifact)

    result = client._get_artifact(artifact_path)

    assert server.call_count(artifact_path) == 1, "stale artifact should trigger one re-download"
    assert result == fresh_artifact


def test_artifact_redownloaded_when_cache_corrupt(client, server):
    # A fresh-but-corrupt cached artifact must fall through to a re-download.
    artifact_path = "data/latest/modern/archetypes.json"
    local = client._local_artifact_path(artifact_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("{not valid json", encoding="utf-8")  # fresh mtime, invalid body

    fresh_artifact = _archetypes_artifact([{"name": "UR Murktide"}])
    server.serve(artifact_path, fresh_artifact)

    result = client._get_artifact(artifact_path)

    assert server.call_count(artifact_path) == 1, "corrupt cached artifact should re-download"
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
# Singleton accessor
# ---------------------------------------------------------------------------


def test_get_remote_snapshot_client_returns_singleton():
    first = get_remote_snapshot_client()
    second = get_remote_snapshot_client()

    assert isinstance(first, RemoteSnapshotClient)
    assert first is second, "accessor should return the shared instance"


def test_reset_remote_snapshot_client_clears_singleton():
    first = get_remote_snapshot_client()
    reset_remote_snapshot_client()
    second = get_remote_snapshot_client()

    assert first is not second, "reset must force a fresh instance"


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
