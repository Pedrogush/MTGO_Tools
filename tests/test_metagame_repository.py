"""Tests for MetagameRepository data access layer."""

import json
import time

import pytest

from repositories.metagame_repository import MetagameRepository, _parse_deck_date


def _write_cache(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def archetype_cache_file(tmp_path):
    """Create a temporary archetype cache file."""
    return tmp_path / "archetype_cache.json"


@pytest.fixture
def archetype_deck_cache_file(tmp_path):
    """Create a temporary archetype deck cache file."""
    return tmp_path / "archetype_decks_cache.json"


@pytest.fixture
def metagame_repo(archetype_cache_file, archetype_deck_cache_file):
    """MetagameRepository instance for testing."""
    return MetagameRepository(
        cache_ttl=3600,
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )


# ============= Cache Loading Tests =============


def test_load_cached_archetypes_no_file(metagame_repo):
    """Test loading archetypes when cache file doesn't exist."""
    result = metagame_repo._load_cached_archetypes("Modern")
    assert result is None


def test_load_cached_archetypes_success(metagame_repo, archetype_cache_file):
    """Test loading archetypes from cache successfully."""
    cache_data = {
        "Modern": {
            "timestamp": time.time(),
            "items": [
                {"name": "Archetype 1", "url": "url1"},
                {"name": "Archetype 2", "url": "url2"},
            ],
        }
    }
    archetype_cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    result = metagame_repo._load_cached_archetypes("Modern")

    assert result is not None
    assert len(result) == 2
    assert result[0]["name"] == "Archetype 1"


def test_load_cached_archetypes_expired(metagame_repo, archetype_cache_file):
    """Test loading expired archetypes returns None."""
    cache_data = {
        "Modern": {
            "timestamp": time.time() - 7200,  # 2 hours ago
            "items": [{"name": "Archetype 1"}],
        }
    }
    archetype_cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    result = metagame_repo._load_cached_archetypes("Modern", max_age=3600)

    assert result is None


def test_load_cached_archetypes_ignore_age(metagame_repo, archetype_cache_file):
    """Test loading expired archetypes with max_age=None."""
    cache_data = {
        "Modern": {
            "timestamp": time.time() - 7200,  # 2 hours ago
            "items": [{"name": "Archetype 1"}],
        }
    }
    archetype_cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    result = metagame_repo._load_cached_archetypes("Modern", max_age=None)

    assert result is not None
    assert len(result) == 1


def test_load_cached_archetypes_invalid_json(metagame_repo, archetype_cache_file):
    """Test loading archetypes with invalid JSON."""
    archetype_cache_file.write_text("invalid json", encoding="utf-8")

    result = metagame_repo._load_cached_archetypes("Modern")

    assert result is None


def test_load_cached_archetypes_missing_format(metagame_repo, archetype_cache_file):
    """Test loading archetypes for format not in cache."""
    cache_data = {
        "Modern": {
            "timestamp": time.time(),
            "items": [{"name": "Archetype 1"}],
        }
    }
    archetype_cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    result = metagame_repo._load_cached_archetypes("Standard")

    assert result is None


# ============= Cache Saving Tests =============


def test_save_cached_archetypes_new_file(metagame_repo, archetype_cache_file):
    """Test saving archetypes to new cache file."""
    archetypes = [
        {"name": "Archetype 1", "url": "url1"},
        {"name": "Archetype 2", "url": "url2"},
    ]

    metagame_repo._save_cached_archetypes("Modern", archetypes)

    assert archetype_cache_file.exists()
    with archetype_cache_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert "Modern" in data
    assert len(data["Modern"]["items"]) == 2


def test_save_cached_archetypes_existing_file(metagame_repo, archetype_cache_file):
    """Test saving archetypes to existing cache file."""
    # Create existing cache
    existing_data = {
        "Standard": {
            "timestamp": time.time(),
            "items": [{"name": "Standard Archetype"}],
        }
    }
    archetype_cache_file.write_text(json.dumps(existing_data), encoding="utf-8")

    # Save new format
    archetypes = [{"name": "Modern Archetype"}]
    metagame_repo._save_cached_archetypes("Modern", archetypes)

    # Both formats should exist
    with archetype_cache_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert "Standard" in data
    assert "Modern" in data


def test_save_cached_archetypes_update_existing_format(metagame_repo, archetype_cache_file):
    """Test updating archetypes for existing format."""
    # Create existing cache
    existing_data = {
        "Modern": {
            "timestamp": time.time() - 3600,
            "items": [{"name": "Old Archetype"}],
        }
    }
    archetype_cache_file.write_text(json.dumps(existing_data), encoding="utf-8")

    # Update same format
    archetypes = [{"name": "New Archetype"}]
    metagame_repo._save_cached_archetypes("Modern", archetypes)

    # Should have new data
    with archetype_cache_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["Modern"]["items"]) == 1
    assert data["Modern"]["items"][0]["name"] == "New Archetype"


# ============= Deck Cache Tests =============


def test_load_cached_decks_expired(metagame_repo, archetype_deck_cache_file):
    """Deck cache past max_age should be treated as a miss."""
    _write_cache(
        archetype_deck_cache_file,
        {"url": {"timestamp": time.time() - 7200, "items": [{"name": "Old Deck"}]}},
    )

    result = metagame_repo._load_cached_decks("url", max_age=3600)

    assert result is None


def test_load_cached_decks_invalid_json(metagame_repo, archetype_deck_cache_file):
    """Corrupt deck cache should be ignored."""
    archetype_deck_cache_file.write_text("{not json", encoding="utf-8")

    assert metagame_repo._load_cached_decks("url") is None


def test_get_decks_returns_stale_cache_when_fetch_fails(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Ensure stale deck cache is returned when MTGGoldfish fetch fails."""
    repo = MetagameRepository(
        cache_ttl=1,
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    stale_items = [{"name": "UR Murktide", "source": "mtggoldfish"}]
    _write_cache(
        archetype_deck_cache_file,
        {"Modern": {"timestamp": time.time() - 3600, "items": stale_items}},
    )

    def fake_get_decks(_href):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        fake_get_decks,
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    result = repo.get_decks_for_archetype({"href": "Modern", "name": "Modern"})

    assert result == stale_items


# ============= Stale Fallback Tests =============


def test_get_archetypes_returns_stale_cache_when_fetch_fails(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Ensure stale archetype cache is returned when MTGGoldfish fetch fails."""
    repo = MetagameRepository(
        cache_ttl=1,
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    stale_items = [{"name": "UR Murktide"}]
    _write_cache(
        archetype_cache_file,
        {"Modern": {"timestamp": time.time() - 3600, "items": stale_items}},
    )

    def fake_get_archetypes(_format):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        fake_get_archetypes,
    )

    assert repo.get_archetypes_for_format("Modern") == stale_items


def test_get_archetypes_recovers_from_corrupt_cache(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Corrupt archetype cache should be overwritten after a successful fetch."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    archetype_cache_file.write_text("{bad json", encoding="utf-8")
    fresh_archetypes = [{"name": "Living End", "url": "/archetype/living-end"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes", lambda _format: fresh_archetypes
    )

    result = repo.get_archetypes_for_format("Modern")

    assert result == fresh_archetypes
    cached = json.loads(archetype_cache_file.read_text(encoding="utf-8"))
    assert cached["Modern"]["items"] == fresh_archetypes


def test_get_decks_recovers_from_corrupt_cache(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Corrupt deck cache should be overwritten after a successful fetch."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    archetype_deck_cache_file.write_text("{bad json", encoding="utf-8")
    fresh_decks = [{"name": "Living End", "date": "2024-03-05", "source": "mtggoldfish"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks", lambda _href: fresh_decks
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    result = repo.get_decks_for_archetype({"href": "modern-living-end", "name": "Living End"})

    assert result == fresh_decks
    cached = json.loads(archetype_deck_cache_file.read_text(encoding="utf-8"))
    assert cached["modern-living-end"]["items"] == fresh_decks


# ============= Deck Date Parsing and Sorting Tests =============


def test_parse_deck_date_supports_common_formats():
    """Date parser should handle MTGGoldfish and MTGO formats."""
    assert _parse_deck_date("2024-03-09") == (2024, 3, 9)
    assert _parse_deck_date("03/09/2024") == (2024, 3, 9)
    assert _parse_deck_date("not a date") == (0, 0, 0)


def test_merge_and_sort_decks_is_deterministic(metagame_repo):
    """Merged decks should sort by date while remaining stable for ties."""
    mtggoldfish_decks = [
        {"name": "GF Latest", "date": "2024-03-04", "source": "mtggoldfish"},
        {"name": "GF Old", "date": "03/02/2024", "source": "mtggoldfish"},
    ]
    mtgo_decks = [
        {"name": "MTGO Top", "date": "03/05/2024", "source": "mtgo"},
        {"name": "MTGO Tie", "date": "2024-03-04", "source": "mtgo"},
    ]

    result = metagame_repo._merge_and_sort_decks(mtggoldfish_decks, mtgo_decks)

    assert [deck["name"] for deck in result] == [
        "MTGO Top",
        "GF Latest",
        "MTGO Tie",
        "GF Old",
    ]


def test_get_decks_respects_source_filters_and_sorting(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Source filters should produce deterministic sorted results."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    mtggoldfish_decks = [
        {"name": "GF New", "date": "2024-03-04", "source": "mtggoldfish", "number": "1"},
        {"name": "GF Old", "date": "03/02/2024", "source": "mtggoldfish", "number": "2"},
    ]
    mtgo_decks = [
        {"name": "MTGO New", "date": "03/05/2024", "source": "mtgo", "number": "3"},
        {"name": "MTGO Old", "date": "2024-03-01", "source": "mtgo", "number": "4"},
    ]
    archetype = {"href": "test-decks", "name": "Test"}

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: mtggoldfish_decks,
    )

    def fake_mtgo(_name, source_filter):
        if source_filter == "mtggoldfish":
            return []
        return mtgo_decks

    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", fake_mtgo)

    combined = repo.get_decks_for_archetype(archetype, force_refresh=True)
    assert [deck["name"] for deck in combined] == ["MTGO New", "GF New", "GF Old", "MTGO Old"]

    goldfish_only = repo.get_decks_for_archetype(
        archetype, force_refresh=True, source_filter="mtggoldfish"
    )
    assert [deck["name"] for deck in goldfish_only] == ["GF New", "GF Old"]
    assert all(deck["source"] == "mtggoldfish" for deck in goldfish_only)

    mtgo_only = repo.get_decks_for_archetype(archetype, force_refresh=True, source_filter="mtgo")
    assert [deck["name"] for deck in mtgo_only] == ["MTGO New", "MTGO Old"]
    assert all(deck["source"] == "mtgo" for deck in mtgo_only)


# ============= Clear Cache Tests =============


def test_clear_cache(metagame_repo, archetype_cache_file):
    """Test clearing all caches."""
    # Create cache files
    archetype_cache_file.write_text("{}", encoding="utf-8")

    metagame_repo.clear_cache()

    assert not archetype_cache_file.exists()


def test_clear_cache_nonexistent_files(metagame_repo):
    """Test clearing cache when files don't exist."""
    # Should not raise exception
    metagame_repo.clear_cache()


# ============= Repository Initialization Tests =============


def test_repository_initialization():
    """Test repository initializes with default TTL."""
    repo = MetagameRepository()
    assert repo.cache_ttl == 3600


def test_repository_custom_ttl():
    """Test repository with custom TTL."""
    repo = MetagameRepository(cache_ttl=7200)
    assert repo.cache_ttl == 7200


# ============= Remote-First Resolution Tests =============


class _FakeRemoteClient:
    """Minimal stub for RemoteSnapshotClient."""

    def __init__(self, archetypes=None, stats=None):
        self._archetypes = archetypes
        self._stats = stats
        self.archetypes_calls: list[str] = []
        self.stats_calls: list[str] = []

    def get_archetypes_for_format(self, fmt):
        self.archetypes_calls.append(fmt)
        return self._archetypes

    def get_metagame_stats_for_format(self, fmt):
        self.stats_calls.append(fmt)
        return self._stats


def _make_repo(tmp_path, remote_client=None):
    return MetagameRepository(
        cache_ttl=3600,
        archetype_list_cache_file=tmp_path / "archetypes.json",
        archetype_decks_cache_file=tmp_path / "decks.json",
        remote_snapshot_client=remote_client,
    )


def test_archetypes_prefer_remote_snapshot_over_live_scrape(tmp_path, monkeypatch):
    """Remote snapshot data should be returned without calling the live scraper."""
    remote_archetypes = [{"name": "UR Murktide", "href": "/archetype/modern-ur-murktide"}]
    remote = _FakeRemoteClient(archetypes=remote_archetypes)
    repo = _make_repo(tmp_path, remote_client=remote)

    live_calls = []
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: live_calls.append(1) or [],
    )

    result = repo.get_archetypes_for_format("modern")

    assert result == remote_archetypes
    assert live_calls == [], "live scraper should not be called when remote snapshot succeeds"
    assert remote.archetypes_calls == ["modern"]


def test_archetypes_fall_through_to_live_when_remote_returns_none(tmp_path, monkeypatch):
    """When the remote client returns None the live scraper should be tried."""
    remote = _FakeRemoteClient(archetypes=None)
    repo = _make_repo(tmp_path, remote_client=remote)

    live_archetypes = [{"name": "Amulet Titan"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: live_archetypes,
    )

    result = repo.get_archetypes_for_format("modern")

    assert result == live_archetypes


def test_archetypes_fall_through_to_live_when_remote_raises(tmp_path, monkeypatch):
    """A remote client exception should be swallowed and live scrape used."""

    class _BoomClient:
        def get_archetypes_for_format(self, _fmt):
            raise RuntimeError("network error")

    repo = _make_repo(tmp_path, remote_client=_BoomClient())

    live_archetypes = [{"name": "Living End"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: live_archetypes,
    )

    result = repo.get_archetypes_for_format("modern")
    assert result == live_archetypes


def test_archetypes_local_cache_preferred_over_remote(tmp_path, monkeypatch):
    """A fresh local cache entry should be returned without consulting remote."""
    import time

    cache_file = tmp_path / "archetypes.json"
    cached_archetypes = [{"name": "Cascade Crasher"}]
    cache_file.write_text(
        json.dumps({"modern": {"timestamp": time.time(), "items": cached_archetypes}}),
        encoding="utf-8",
    )

    remote = _FakeRemoteClient(archetypes=[{"name": "Something Else"}])
    repo = _make_repo(tmp_path, remote_client=remote)

    result = repo.get_archetypes_for_format("modern")

    assert result == cached_archetypes
    assert remote.archetypes_calls == [], "remote client should not be called for fresh cache"


def test_get_stats_returns_remote_snapshot_data(tmp_path):
    """get_stats_for_format should return remote snapshot data when available."""
    remote_stats = {
        "modern": {
            "timestamp": 1711234567.0,
            "UR Murktide": {"results": {"2025-03-24": 5}},
        }
    }
    remote = _FakeRemoteClient(stats=remote_stats)
    repo = _make_repo(tmp_path, remote_client=remote)

    result = repo.get_stats_for_format("modern")

    assert result == remote_stats
    assert remote.stats_calls == ["modern"]


def test_get_stats_falls_back_to_live_when_remote_returns_none(tmp_path, monkeypatch):
    """When remote stats are unavailable the live navigator is called."""
    live_stats = {"modern": {"timestamp": 0.0, "UR Murktide": {"results": {}}}}
    called = []

    def fake_live_stats(fmt):
        called.append(fmt)
        return live_stats

    monkeypatch.setattr("navigators.mtggoldfish.get_archetype_stats", fake_live_stats)

    repo = _make_repo(tmp_path, remote_client=_FakeRemoteClient(stats=None))
    result = repo.get_stats_for_format("modern")

    assert result == live_stats
    assert called == ["modern"]


def test_remote_client_not_used_when_disabled(tmp_path, monkeypatch):
    """Without an injected client and REMOTE_SNAPSHOTS_ENABLED=False, no remote calls."""
    monkeypatch.setattr("repositories.metagame_repository.REMOTE_SNAPSHOTS_ENABLED", False)
    repo = _make_repo(tmp_path, remote_client=None)

    live_archetypes = [{"name": "Cascade Crasher"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: live_archetypes,
    )

    result = repo.get_archetypes_for_format("modern")
    assert result == live_archetypes


# ============= Remote-First Resolution Tests: Deck Lists =============


class _FakeRemoteClientWithDecks(_FakeRemoteClient):
    """Extends the fake remote client with deck-list support."""

    def __init__(self, archetypes=None, stats=None, decks=None):
        super().__init__(archetypes=archetypes, stats=stats)
        self._decks = decks
        self.decks_calls: list[tuple[str, str]] = []

    def get_decks_for_archetype(self, fmt, slug):
        self.decks_calls.append((fmt, slug))
        return self._decks


def test_decks_prefer_remote_snapshot_over_live_scrape(tmp_path, monkeypatch):
    """Remote snapshot decks should be returned without calling the live scraper."""
    remote_decks = [{"name": "modern-ur-murktide", "number": "123", "source": "mtggoldfish"}]
    remote = _FakeRemoteClientWithDecks(decks=remote_decks)
    repo = _make_repo(tmp_path, remote_client=remote)

    live_calls = []
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: live_calls.append(1) or [],
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    archetype = {"href": "modern-ur-murktide", "name": "UR Murktide"}
    result = repo.get_decks_for_archetype(archetype, mtg_format="modern")

    assert result == remote_decks
    assert live_calls == [], "live scraper should not be called when remote snapshot succeeds"
    assert remote.decks_calls == [("modern", "modern-ur-murktide")]


def test_decks_fall_through_to_live_when_remote_returns_none(tmp_path, monkeypatch):
    """When the remote client returns None for decks the live scraper should be tried."""
    remote = _FakeRemoteClientWithDecks(decks=None)
    repo = _make_repo(tmp_path, remote_client=remote)

    live_decks = [{"name": "modern-ur-murktide", "number": "456", "source": "mtggoldfish"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: live_decks,
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    archetype = {"href": "modern-ur-murktide", "name": "UR Murktide"}
    result = repo.get_decks_for_archetype(archetype, mtg_format="modern")

    assert result == live_decks


def test_decks_fall_through_to_live_when_remote_raises(tmp_path, monkeypatch):
    """A remote client exception for decks should be swallowed and live scrape used."""

    class _BoomDeckClient(_FakeRemoteClientWithDecks):
        def get_decks_for_archetype(self, _fmt, _slug):
            raise RuntimeError("network error")

    repo = _make_repo(tmp_path, remote_client=_BoomDeckClient())

    live_decks = [{"name": "modern-ur-murktide", "number": "789", "source": "mtggoldfish"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: live_decks,
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    archetype = {"href": "modern-ur-murktide", "name": "UR Murktide"}
    result = repo.get_decks_for_archetype(archetype, mtg_format="modern")
    assert result == live_decks


def test_decks_skip_remote_when_no_format_provided(tmp_path, monkeypatch):
    """Remote snapshot step should be skipped when mtg_format is not supplied."""
    remote = _FakeRemoteClientWithDecks(decks=[{"name": "some-deck"}])
    repo = _make_repo(tmp_path, remote_client=remote)

    live_decks = [{"name": "modern-ur-murktide", "number": "1", "source": "mtggoldfish"}]
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: live_decks,
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    archetype = {"href": "modern-ur-murktide", "name": "UR Murktide"}
    result = repo.get_decks_for_archetype(archetype)  # no mtg_format

    assert result == live_decks
    assert remote.decks_calls == [], "remote client must not be consulted without a format"


def test_decks_local_cache_preferred_over_remote(tmp_path, monkeypatch):
    """A fresh local cache entry should be returned without consulting remote."""
    cache_file = tmp_path / "decks.json"
    cached_decks = [{"name": "modern-ur-murktide", "number": "cached", "source": "mtggoldfish"}]
    cache_file.write_text(
        json.dumps(
            {
                "modern-ur-murktide": {
                    "timestamp": time.time(),
                    "items": cached_decks,
                }
            }
        ),
        encoding="utf-8",
    )

    remote = _FakeRemoteClientWithDecks(decks=[{"name": "remote-deck"}])
    repo = MetagameRepository(
        cache_ttl=3600,
        archetype_list_cache_file=tmp_path / "archetypes.json",
        archetype_decks_cache_file=cache_file,
        remote_snapshot_client=remote,
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    archetype = {"href": "modern-ur-murktide", "name": "UR Murktide"}
    result = repo.get_decks_for_archetype(archetype, mtg_format="modern")

    assert result == cached_decks
    assert remote.decks_calls == [], "remote client should not be called for fresh cache"


def test_decks_remote_snapshot_saves_to_local_cache(tmp_path, monkeypatch):
    """Decks fetched from the remote snapshot should be written to the local cache."""
    remote_decks = [{"name": "modern-ur-murktide", "number": "snap", "source": "mtggoldfish"}]
    remote = _FakeRemoteClientWithDecks(decks=remote_decks)
    repo = _make_repo(tmp_path, remote_client=remote)

    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    archetype = {"href": "modern-ur-murktide", "name": "UR Murktide"}
    repo.get_decks_for_archetype(archetype, mtg_format="modern")

    cache = json.loads((tmp_path / "decks.json").read_text(encoding="utf-8"))
    assert cache["modern-ur-murktide"]["items"] == remote_decks


# ============= download_deck_content: embedded deck_text fast path =============


def test_download_deck_content_uses_embedded_deck_text(tmp_path):
    """download_deck_content should return deck_text without network access."""
    repo = _make_repo(tmp_path)
    deck = {
        "name": "UR Murktide",
        "number": "123456",
        "source": "mtggoldfish",
        "deck_text": "4 Murktide Regent\n\nSideboard\n2 Flusterstorm\n",
    }

    result = repo.download_deck_content(deck)

    assert result == deck["deck_text"]


def test_download_deck_content_falls_back_to_fetch_when_no_deck_text(tmp_path, monkeypatch):
    """download_deck_content should call fetch_deck_text when deck_text is absent."""
    repo = _make_repo(tmp_path)
    fetched = []

    def fake_fetch(number, source_filter=None):
        fetched.append(number)
        return "4 Lightning Bolt\n"

    monkeypatch.setattr("repositories.metagame_repository.fetch_deck_text", fake_fetch)

    deck = {"name": "Burn", "number": "99999", "source": "mtggoldfish"}
    result = repo.download_deck_content(deck)

    assert result == "4 Lightning Bolt\n"
    assert fetched == ["99999"]


def test_download_deck_content_empty_deck_text_falls_back_to_fetch(tmp_path, monkeypatch):
    """An empty deck_text string should not be used; fetch_deck_text should be called."""
    repo = _make_repo(tmp_path)
    fetched = []

    def fake_fetch(number, source_filter=None):
        fetched.append(number)
        return "4 Lightning Bolt\n"

    monkeypatch.setattr("repositories.metagame_repository.fetch_deck_text", fake_fetch)

    deck = {"name": "Burn", "number": "99999", "source": "mtggoldfish", "deck_text": ""}
    result = repo.download_deck_content(deck)

    assert result == "4 Lightning Bolt\n"
    assert fetched == ["99999"]


# ============= prefetch_deck_artifacts_for_format =============


def test_prefetch_calls_remote_client_with_slugs(tmp_path):
    """prefetch_deck_artifacts_for_format should extract hrefs and call the remote client."""
    prefetch_calls: list[tuple[str, list[str]]] = []

    class _PrefetchClient(_FakeRemoteClientWithDecks):
        def prefetch_deck_artifacts(self, fmt, slugs):
            prefetch_calls.append((fmt, slugs))

    remote = _PrefetchClient()
    repo = _make_repo(tmp_path, remote_client=remote)

    archetypes = [
        {"name": "UR Murktide", "href": "modern-ur-murktide"},
        {"name": "Amulet Titan", "href": "modern-amulet-titan"},
    ]
    repo.prefetch_deck_artifacts_for_format("modern", archetypes)

    assert prefetch_calls == [("modern", ["modern-ur-murktide", "modern-amulet-titan"])]


def test_prefetch_skips_archetypes_with_no_href(tmp_path):
    """Archetypes without href or url should be silently skipped."""
    prefetch_calls: list[tuple[str, list[str]]] = []

    class _PrefetchClient(_FakeRemoteClientWithDecks):
        def prefetch_deck_artifacts(self, fmt, slugs):
            prefetch_calls.append((fmt, slugs))

    remote = _PrefetchClient()
    repo = _make_repo(tmp_path, remote_client=remote)

    archetypes = [
        {"name": "UR Murktide", "href": "modern-ur-murktide"},
        {"name": "No Href"},
    ]
    repo.prefetch_deck_artifacts_for_format("modern", archetypes)

    assert prefetch_calls == [("modern", ["modern-ur-murktide"])]


def test_prefetch_does_nothing_when_no_remote_client(tmp_path, monkeypatch):
    """prefetch_deck_artifacts_for_format should be a no-op when remote is disabled."""
    monkeypatch.setattr("repositories.metagame_repository.REMOTE_SNAPSHOTS_ENABLED", False)
    repo = _make_repo(tmp_path, remote_client=None)

    # Should not raise
    repo.prefetch_deck_artifacts_for_format("modern", [{"href": "modern-ur-murktide"}])
