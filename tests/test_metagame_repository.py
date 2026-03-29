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


# ============= Stale-While-Revalidate Tests =============


def test_stale_while_revalidate_returns_stale_immediately(
    archetype_cache_file, archetype_deck_cache_file
):
    """When cache is stale, get_archetypes_for_format returns it right away."""
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

    result = repo.get_archetypes_for_format("Modern")

    assert result == stale_items


def test_stale_while_revalidate_triggers_background_refresh(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Background refresh callback is invoked with fresh data when cache is stale."""
    import threading

    repo = MetagameRepository(
        cache_ttl=1,
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    stale_items = [{"name": "UR Murktide"}]
    fresh_items = [{"name": "UR Murktide"}, {"name": "Amulet Titan"}]
    _write_cache(
        archetype_cache_file,
        {"Modern": {"timestamp": time.time() - 3600, "items": stale_items}},
    )

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: fresh_items,
    )

    refresh_received: list[list] = []
    done = threading.Event()

    def on_refresh(items):
        refresh_received.append(items)
        done.set()

    result = repo.get_archetypes_for_format("Modern", on_background_refresh=on_refresh)

    assert result == stale_items
    assert done.wait(timeout=5), "background refresh did not complete in time"
    assert refresh_received == [fresh_items]


def test_stale_while_revalidate_no_callback_no_background_thread(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """No background thread is started when on_background_refresh is not provided."""
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

    triggered = []
    monkeypatch.setattr(repo, "_trigger_background_refresh", lambda *a: triggered.append(a))

    repo.get_archetypes_for_format("Modern")

    assert triggered == [], "background refresh should not be triggered without a callback"


def test_stale_while_revalidate_updates_cache_on_refresh(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Background refresh persists fresh data to the cache."""
    import threading

    repo = MetagameRepository(
        cache_ttl=1,
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    stale_items = [{"name": "UR Murktide"}]
    fresh_items = [{"name": "UR Murktide"}, {"name": "Amulet Titan"}]
    _write_cache(
        archetype_cache_file,
        {"Modern": {"timestamp": time.time() - 3600, "items": stale_items}},
    )

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: fresh_items,
    )

    done = threading.Event()
    repo.get_archetypes_for_format("Modern", on_background_refresh=lambda _: done.set())
    done.wait(timeout=5)

    # After background refresh the cache should be fresh
    cached = repo._load_cached_archetypes("Modern")
    assert cached == fresh_items


def test_stale_while_revalidate_background_failure_is_silent(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """A failed background refresh does not invoke the callback and does not raise."""
    import threading

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

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetypes",
        lambda _fmt: (_ for _ in ()).throw(RuntimeError("network down")),
    )

    callback_called = threading.Event()
    repo.get_archetypes_for_format("Modern", on_background_refresh=lambda _: callback_called.set())

    # Give thread a moment to fail
    callback_called.wait(timeout=1)
    assert not callback_called.is_set(), "callback must not be called on refresh failure"


def test_fresh_cache_does_not_trigger_background_refresh(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """When cache is fresh, no background refresh is triggered."""
    repo = MetagameRepository(
        cache_ttl=3600,
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    fresh_items = [{"name": "Cascade Crasher"}]
    _write_cache(
        archetype_cache_file,
        {"Modern": {"timestamp": time.time(), "items": fresh_items}},
    )

    triggered = []
    monkeypatch.setattr(repo, "_trigger_background_refresh", lambda *a: triggered.append(a))

    result = repo.get_archetypes_for_format("Modern", on_background_refresh=lambda _: None)

    assert result == fresh_items
    assert triggered == [], "background refresh must not fire on a fresh cache hit"


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


# ============= Bundle MTGO Preservation Tests =============


def test_live_scrape_preserves_bundle_mtgo_decks(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """A live MTGGoldfish scrape must not evict MTGO decks hydrated from the bundle."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    bundle_mtgo = {"name": "Bundle MTGO", "date": "2026-03-25", "source": "mtgo", "number": "m1"}
    fresh_gf = {"name": "GF Fresh", "date": "2026-03-26", "source": "mtggoldfish", "number": "g1"}
    archetype = {"href": "test-arch", "name": "Test"}

    # Seed the cache with a bundle-provided MTGO entry
    _write_cache(
        archetype_deck_cache_file,
        {"test-arch": {"timestamp": time.time(), "items": [bundle_mtgo]}},
    )

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: [fresh_gf],
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    result = repo.get_decks_for_archetype(archetype, force_refresh=True)

    names = [d["name"] for d in result]
    assert "Bundle MTGO" in names
    assert "GF Fresh" in names


def test_live_scrape_preserves_only_mtgo_source(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Only entries with source='mtgo' are preserved; old MTGGoldfish entries are replaced."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    old_gf = {"name": "Old GF", "date": "2026-01-01", "source": "mtggoldfish", "number": "g0"}
    bundle_mtgo = {"name": "Bundle MTGO", "date": "2026-03-25", "source": "mtgo", "number": "m1"}
    fresh_gf = {"name": "GF Fresh", "date": "2026-03-26", "source": "mtggoldfish", "number": "g1"}
    archetype = {"href": "test-arch", "name": "Test"}

    _write_cache(
        archetype_deck_cache_file,
        {"test-arch": {"timestamp": time.time(), "items": [old_gf, bundle_mtgo]}},
    )

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: [fresh_gf],
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    result = repo.get_decks_for_archetype(archetype, force_refresh=True)

    names = [d["name"] for d in result]
    assert "Old GF" not in names  # replaced by fresh scrape
    assert "GF Fresh" in names
    assert "Bundle MTGO" in names  # preserved


def test_live_scrape_no_prior_bundle_entries(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Live scrape with no prior bundle MTGO entries behaves the same as before."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    fresh_gf = {"name": "GF Fresh", "date": "2026-03-26", "source": "mtggoldfish", "number": "g1"}
    archetype = {"href": "test-arch", "name": "Test"}

    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: [fresh_gf],
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    result = repo.get_decks_for_archetype(archetype, force_refresh=True)

    assert len(result) == 1
    assert result[0]["name"] == "GF Fresh"


def test_cached_path_returns_bundle_mtgo_decks(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """Bundle MTGO decks in the archetype cache are returned on the cache hit path."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    bundle_mtgo = {"name": "Bundle MTGO", "date": "2026-03-25", "source": "mtgo", "number": "m1"}
    gf_deck = {"name": "GF Deck", "date": "2026-03-24", "source": "mtggoldfish", "number": "g1"}
    archetype = {"href": "test-arch", "name": "Test"}

    _write_cache(
        archetype_deck_cache_file,
        {"test-arch": {"timestamp": time.time(), "items": [gf_deck, bundle_mtgo]}},
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    result = repo.get_decks_for_archetype(archetype)

    names = [d["name"] for d in result]
    assert "Bundle MTGO" in names
    assert "GF Deck" in names


def test_saved_cache_after_live_scrape_contains_bundle_mtgo(
    archetype_cache_file, archetype_deck_cache_file, monkeypatch
):
    """After a live scrape, persisted cache contains both fresh GF and bundle MTGO entries."""
    repo = MetagameRepository(
        archetype_list_cache_file=archetype_cache_file,
        archetype_decks_cache_file=archetype_deck_cache_file,
    )
    bundle_mtgo = {"name": "Bundle MTGO", "date": "2026-03-25", "source": "mtgo", "number": "m1"}
    fresh_gf = {"name": "GF Fresh", "date": "2026-03-26", "source": "mtggoldfish", "number": "g1"}
    archetype = {"href": "test-arch", "name": "Test"}

    _write_cache(
        archetype_deck_cache_file,
        {"test-arch": {"timestamp": time.time(), "items": [bundle_mtgo]}},
    )
    monkeypatch.setattr(
        "repositories.metagame_repository.get_archetype_decks",
        lambda _href: [fresh_gf],
    )
    monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", lambda *_: [])

    repo.get_decks_for_archetype(archetype, force_refresh=True)

    saved = json.loads(archetype_deck_cache_file.read_text())
    saved_names = [d["name"] for d in saved["test-arch"]["items"]]
    assert "Bundle MTGO" in saved_names
    assert "GF Fresh" in saved_names


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
