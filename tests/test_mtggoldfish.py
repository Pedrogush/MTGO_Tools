"""Tests for services/scrapers/mtggoldfish.py module."""

import json
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import repositories.scrapers.mtggoldfish as mtggoldfish
from repositories.scrapers.mtggoldfish import (
    _load_cached_archetypes,
    _save_cached_archetypes,
    download_deck,
    get_archetype_decks,
    get_archetype_stats,
    get_archetypes,
)

# Sample HTML for testing
SAMPLE_METAGAME_HTML = """
<html>
<body>
<div id="metagame-decks-container">
    <span class="deck-price-paper">
        <a href="/archetype/modern-rakdos-midrange#paper">Rakdos Midrange</a>
    </span>
    <span class="deck-price-paper">
        <a href="/archetype/modern-amulet-titan#paper">Amulet Titan</a>
    </span>
    <span class="deck-price-paper">
        <div>Should be filtered</div>
        <a href="/archetype/filtered">Filtered</a>
    </span>
</div>
</body>
</html>
"""

SAMPLE_METAGAME_HTML_WITH_DUPLICATE = """
<html>
<body>
<div id="metagame-decks-container">
    <span class="deck-price-paper">
        <a href="/archetype/modern-rakdos-midrange#paper">Rakdos Midrange</a>
    </span>
    <span class="deck-price-paper">
        <a href="/archetype/modern-rakdos-midrange-alt#paper">Rakdos Midrange</a>
    </span>
    <span class="deck-price-paper">
        <a href="/archetype/modern-amulet-titan#paper">Amulet Titan</a>
    </span>
</div>
</body>
</html>
"""

SAMPLE_ARCHETYPE_DECKS_HTML = """
<html>
<body>
<table class="table-striped">
    <tr><th>Date</th><th>Deck</th><th>Player</th><th>Event</th><th>Result</th></tr>
    <tr>
        <td>Jan 15</td>
        <td><a href="/deck/123456">View Deck</a></td>
        <td>PlayerOne</td>
        <td>MTGO Challenge</td>
        <td>1st</td>
    </tr>
    <tr>
        <td>Jan 14</td>
        <td><a href="/deck/789012">View Deck</a></td>
        <td>PlayerTwo</td>
        <td>MTGO League</td>
        <td>5-0</td>
    </tr>
</table>
</body>
</html>
"""

SAMPLE_DECK_HTML = """
<html>
<body>
<script>
initializeDeckComponents(123, 456, "4%20Lightning%20Bolt%0A4%20Counterspell%0A%0A3%20Duress");
</script>
</body>
</html>
"""


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_archetype_list_file(temp_cache_dir):
    """Create a temporary archetype list cache file."""
    cache_file = temp_cache_dir / "archetype_list.json"
    return cache_file


@pytest.fixture
def temp_curr_deck_file(temp_cache_dir):
    """Create a temporary current deck file."""
    curr_deck_file = temp_cache_dir / "curr_deck.txt"
    return curr_deck_file


@pytest.fixture(scope="class")
def temp_archetype_decks_file(tmp_path_factory):
    """Class-scoped temp cache file for archetype decks (shared across tests in the class)."""
    return tmp_path_factory.mktemp("deck_cache") / "archetype_decks.json"


class TestCacheLoading:
    """Test archetype cache loading functions."""

    def test_load_cached_archetypes_missing_file(self, temp_archetype_list_file):
        """Test loading archetypes when cache file doesn't exist."""
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = _load_cached_archetypes("modern", max_age=3600)
        assert result is None

    def test_load_cached_archetypes_invalid_json(self, temp_archetype_list_file):
        """Test loading archetypes with invalid JSON."""
        temp_archetype_list_file.write_text("invalid json{{{")
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = _load_cached_archetypes("modern", max_age=3600)
            assert result is None

    def test_load_cached_archetypes_missing_format(self, temp_archetype_list_file):
        """Test loading archetypes when format is not in cache."""
        temp_archetype_list_file.write_text(
            json.dumps({"pioneer": {"timestamp": time.time(), "items": []}})
        )
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = _load_cached_archetypes("modern", max_age=3600)
            assert result is None

    def test_load_cached_archetypes_expired(self, temp_archetype_list_file):
        """Test loading archetypes when cache is expired."""
        old_timestamp = time.time() - 7200  # 2 hours ago
        data = {"modern": {"timestamp": old_timestamp, "items": [{"name": "Test", "href": "test"}]}}
        temp_archetype_list_file.write_text(json.dumps(data))
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = _load_cached_archetypes("modern", max_age=3600)  # 1 hour max age
            assert result is None

    def test_load_cached_archetypes_valid(self, temp_archetype_list_file):
        """Test loading valid cached archetypes."""
        items = [{"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"}]
        data = {"modern": {"timestamp": time.time(), "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = _load_cached_archetypes("modern", max_age=3600)
            assert result == items


class TestCacheSaving:
    """Test archetype cache saving functions."""

    def test_save_cached_archetypes_new_file(self, temp_archetype_list_file):
        """Test saving archetypes to a new cache file."""
        items = [{"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"}]
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            _save_cached_archetypes("modern", items)

        assert temp_archetype_list_file.exists()
        data = json.loads(temp_archetype_list_file.read_text())
        assert "modern" in data
        assert data["modern"]["items"] == items
        assert "timestamp" in data["modern"]

    def test_save_cached_archetypes_existing_file(self, temp_archetype_list_file):
        """Test saving archetypes to an existing cache file."""
        # Create initial cache with pioneer data
        initial_data = {
            "pioneer": {
                "timestamp": time.time(),
                "items": [{"name": "Pioneer Deck", "href": "pioneer-deck"}],
            }
        }
        temp_archetype_list_file.write_text(json.dumps(initial_data))

        # Save modern data
        modern_items = [{"name": "Modern Deck", "href": "modern-deck"}]
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            _save_cached_archetypes("modern", modern_items)

        data = json.loads(temp_archetype_list_file.read_text())
        assert "pioneer" in data
        assert "modern" in data
        assert data["modern"]["items"] == modern_items

    def test_save_cached_archetypes_invalid_existing_json(self, temp_archetype_list_file):
        """Test saving archetypes when existing file has invalid JSON."""
        temp_archetype_list_file.write_text("invalid json")

        items = [{"name": "Test", "href": "test"}]
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            _save_cached_archetypes("modern", items)

        data = json.loads(temp_archetype_list_file.read_text())
        assert data == {"modern": {"timestamp": data["modern"]["timestamp"], "items": items}}


class TestGetArchetypes:
    """Test get_archetypes function."""

    def test_get_archetypes_from_cache(self, temp_archetype_list_file):
        """Test getting archetypes from cache."""
        items = [{"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"}]
        data = {"modern": {"timestamp": time.time(), "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = get_archetypes("modern")
            assert result == items

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetypes_from_web(self, mock_get, temp_archetype_list_file):
        """Test fetching archetypes from web when cache is missing."""
        mock_response = Mock()
        mock_response.text = SAMPLE_METAGAME_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = get_archetypes("modern", cache_ttl=0)  # Force cache miss

        assert len(result) == 2
        assert result[0]["name"] == "Rakdos Midrange"
        assert result[0]["href"] == "modern-rakdos-midrange"
        assert result[1]["name"] == "Amulet Titan"
        assert result[1]["href"] == "modern-amulet-titan"

        # Verify cache was saved
        assert temp_archetype_list_file.exists()

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetypes_deduplicates_by_name(self, mock_get, temp_archetype_list_file):
        """Duplicate archetype names (same display name, different hrefs) collapse to
        a single entry, keeping the first occurrence's href."""
        mock_response = Mock()
        mock_response.text = SAMPLE_METAGAME_HTML_WITH_DUPLICATE
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = get_archetypes("modern", cache_ttl=0)  # Force cache miss

        assert len(result) == 2
        rakdos = [item for item in result if item["name"] == "Rakdos Midrange"]
        assert len(rakdos) == 1
        # First occurrence wins.
        assert rakdos[0]["href"] == "modern-rakdos-midrange"

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetypes_request_failure_with_stale_cache(
        self, mock_get, temp_archetype_list_file
    ):
        """Test fallback to stale cache when request fails."""
        # Create stale cache (2 hours old)
        old_timestamp = time.time() - 7200
        items = [{"name": "Stale Deck", "href": "stale-deck"}]
        data = {"modern": {"timestamp": old_timestamp, "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))

        # Mock request failure
        mock_get.side_effect = Exception("Network error")

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = get_archetypes("modern", cache_ttl=3600, allow_stale=True)

        assert result == items

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetypes_request_failure_no_stale_cache(
        self, mock_get, temp_archetype_list_file
    ):
        """Test that exception is raised when request fails and no stale cache exists."""
        mock_get.side_effect = Exception("Network error")

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            with pytest.raises(Exception, match="Network error"):
                get_archetypes("modern", cache_ttl=0, allow_stale=True)

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetypes_request_failure_stale_not_allowed(
        self, mock_get, temp_archetype_list_file
    ):
        """Test that exception is raised when allow_stale is False."""
        # Create stale cache
        old_timestamp = time.time() - 7200
        items = [{"name": "Stale Deck", "href": "stale-deck"}]
        data = {"modern": {"timestamp": old_timestamp, "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))

        mock_get.side_effect = Exception("Network error")

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            with pytest.raises(Exception, match="Network error"):
                get_archetypes("modern", cache_ttl=0, allow_stale=False)

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetypes_missing_container(self, mock_get, temp_archetype_list_file):
        """Test handling when metagame container is missing from HTML."""
        mock_response = Mock()
        mock_response.text = "<html><body>No container here</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            with pytest.raises(RuntimeError, match="Failed to locate metagame deck container"):
                get_archetypes("modern", cache_ttl=0)

    def test_get_archetypes_case_insensitive_format(self, temp_archetype_list_file):
        """Test that format is case-insensitive."""
        items = [{"name": "Test", "href": "test"}]
        data = {"modern": {"timestamp": time.time(), "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file
        ):
            result = get_archetypes("MODERN")
            assert result == items


class TestGetArchetypeDecks:
    """Test get_archetype_decks function."""

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetype_decks_success(self, mock_get, temp_archetype_decks_file):
        """Test successfully fetching archetype decks."""
        mock_response = Mock()
        mock_response.text = SAMPLE_ARCHETYPE_DECKS_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE",
            temp_archetype_decks_file,
        ):
            result = get_archetype_decks("modern-rakdos-midrange")

        assert len(result) == 2
        assert result[0]["date"] == "Jan 15"
        assert result[0]["number"] == "123456"
        assert result[0]["player"] == "PlayerOne"
        assert result[0]["event"] == "MTGO Challenge"
        assert result[0]["result"] == "1st"
        assert result[0]["name"] == "modern-rakdos-midrange"

        assert result[1]["number"] == "789012"
        assert result[1]["player"] == "PlayerTwo"

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetype_decks_request_failure(self, mock_get, temp_cache_dir):
        """Test that a request exception is caught and yields an empty result.

        Uses a fresh per-test cache file and a never-before-seen archetype so the
        cache misses and the network path actually runs (the failure return at
        mtggoldfish.py is what is being exercised here)."""
        mock_get.side_effect = Exception("Network error")

        fresh_cache = temp_cache_dir / "archetype_decks.json"
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE",
            fresh_cache,
        ):
            result = get_archetype_decks("modern-request-failure-archetype")

        mock_get.assert_called()  # network path was taken (no cache short-circuit)
        assert result == []

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetype_decks_missing_table(self, mock_get, temp_cache_dir):
        """Test that missing deck table yields an empty result.

        Uses a fresh per-test cache file and a never-before-seen archetype so the
        cache misses and the missing-table return path actually runs."""
        mock_response = Mock()
        mock_response.text = "<html><body>No table here</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        fresh_cache = temp_cache_dir / "archetype_decks.json"
        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE",
            fresh_cache,
        ):
            result = get_archetype_decks("modern-missing-table-archetype")

        mock_get.assert_called()  # network path was taken (no cache short-circuit)
        assert result == []

    @patch("repositories.scrapers.mtggoldfish.requests.get")
    def test_get_archetype_decks_uses_split_connect_read_timeout(
        self, mock_get, temp_archetype_decks_file
    ):
        """The bulk stats per-archetype GET must use the tighter (connect, read)
        timeout split so one hung host fails fast instead of riding the full 30s
        single-request timeout."""
        mock_response = Mock()
        mock_response.text = SAMPLE_ARCHETYPE_DECKS_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch(
            "repositories.scrapers.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE",
            temp_archetype_decks_file,
        ):
            get_archetype_decks("modern-some-fresh-archetype")

        timeout = mock_get.call_args.kwargs["timeout"]
        assert timeout == (
            mtggoldfish.MTGGOLDFISH_STATS_CONNECT_TIMEOUT_SECONDS,
            mtggoldfish.MTGGOLDFISH_STATS_READ_TIMEOUT_SECONDS,
        )
        connect_timeout = timeout[0]
        assert connect_timeout < mtggoldfish.MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS


class TestGetArchetypeStats:
    """Test get_archetype_stats parallelization and result aggregation."""

    def test_parallel_fetch_preserves_archetype_mapping(self, temp_cache_dir):
        """Each archetype's decks must map back to that archetype, even when the
        per-archetype fetches run concurrently and complete out of order.

        Submission order is deterministically permuted relative to completion order
        by blocking each fake fetch until the *last*-submitted archetype has been
        entered, forcing out-of-order completion so a serial/positional mapping bug
        would be caught."""
        archetypes = [
            {"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"},
            {"name": "Amulet Titan", "href": "modern-amulet-titan"},
            {"name": "Burn", "href": "modern-burn"},
        ]
        today = datetime.now().strftime("%Y-%m-%d")
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        # Each archetype has two decks: one today, one two days ago. The "two days
        # ago" deck exercises a non-today lookback bucket; mixed casing on the date
        # exercises the case-insensitive substring match.
        decks_by_href = {
            a["href"]: [
                {"date": today, "name": a["name"], "tag": a["href"]},
                {"date": two_days_ago.upper(), "name": a["name"], "tag": a["href"]},
            ]
            for a in archetypes
        }

        # Barrier of size N so all workers enter before any returns, then completion
        # order is reversed relative to submission order via a per-href delay event.
        barrier = threading.Barrier(len(archetypes))
        order = [a["href"] for a in archetypes]

        def fake_get_archetype_decks(href):
            barrier.wait(timeout=5)
            # Later-submitted hrefs sleep less, so they finish first -> out of order.
            time.sleep(0.02 * order.index(href))
            return decks_by_href[href]

        cache_file = temp_cache_dir / "archetype_stats.json"
        with (
            patch.object(mtggoldfish, "get_archetypes", return_value=archetypes),
            patch.object(
                mtggoldfish, "get_archetype_decks", side_effect=fake_get_archetype_decks
            ) as mock_decks,
            patch.object(mtggoldfish, "ARCHETYPE_CACHE_FILE", cache_file),
        ):
            stats = get_archetype_stats("modern")

        # One fetch per archetype, parallelized but complete.
        assert mock_decks.call_count == len(archetypes)
        for a in archetypes:
            entry = stats["modern"][a["name"]]
            assert entry["decks"] == decks_by_href[a["href"]]
            # Today's lookback bucket counts the single "today" deck.
            assert entry["results"][today] == 1
            # A prior-day bucket counts the case-insensitively matched deck.
            assert entry["results"][two_days_ago] == 1
        # Cache file written.
        assert cache_file.exists()

    def test_get_archetype_stats_returns_fresh_cache_without_network(self, temp_cache_dir):
        """A recent cache entry (< ONE_DAY_SECONDS old) is returned directly without
        re-scraping, so neither get_archetypes nor get_archetype_decks is called."""
        cache_file = temp_cache_dir / "archetype_stats.json"
        cached_stats = {
            "modern": {
                "timestamp": time.time(),  # fresh
                "Rakdos Midrange": {"decks": [], "results": {}},
            }
        }
        cache_file.write_text(json.dumps(cached_stats))

        with (
            patch.object(mtggoldfish, "get_archetypes") as mock_archetypes,
            patch.object(mtggoldfish, "get_archetype_decks") as mock_decks,
            patch.object(mtggoldfish, "ARCHETYPE_CACHE_FILE", cache_file),
        ):
            result = get_archetype_stats("modern")

        assert result == cached_stats
        mock_archetypes.assert_not_called()
        mock_decks.assert_not_called()

    def test_get_archetype_stats_recovers_from_corrupt_cache(self, temp_cache_dir):
        """An unreadable (invalid JSON) cache is discarded and stats are recomputed
        from the network path rather than crashing."""
        cache_file = temp_cache_dir / "archetype_stats.json"
        cache_file.write_text("not valid json{{{")

        archetypes = [{"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"}]
        today = datetime.now().strftime("%Y-%m-%d")
        decks = [{"date": today, "name": "Rakdos Midrange"}]

        with (
            patch.object(mtggoldfish, "get_archetypes", return_value=archetypes) as mock_archetypes,
            patch.object(mtggoldfish, "get_archetype_decks", return_value=decks) as mock_decks,
            patch.object(mtggoldfish, "ARCHETYPE_CACHE_FILE", cache_file),
        ):
            result = get_archetype_stats("modern")

        # Recovered: recomputed instead of raising on the corrupt cache.
        mock_archetypes.assert_called_once()
        mock_decks.assert_called_once()
        assert result["modern"]["Rakdos Midrange"]["decks"] == decks
        assert result["modern"]["Rakdos Midrange"]["results"][today] == 1


class TestFetchDeckText:
    """Test fetch_deck_text against a real SQLite-backed deck cache.

    Only the network seam (the visual-page fetch) is mocked. The cache is a real
    ``DeckTextCache`` over a ``tmp_path`` SQLite DB, so we assert on persisted
    values rather than on mock interactions.
    """

    @pytest.fixture
    def real_cache(self, tmp_path):
        """A real DeckTextCache over a throwaway SQLite DB.

        Patches both the function-local ``get_deck_cache`` import target and points
        the legacy JSON migration source at a nonexistent path so migration is an
        inert no-op for these tests.
        """
        from repositories.deck_text_cache import DeckTextCache

        cache = DeckTextCache(tmp_path / "deck_cache.db")
        with (
            patch("repositories.deck_text_cache.get_deck_cache", return_value=cache),
            patch(
                "repositories.scrapers.mtggoldfish.DECK_TEXT_CACHE_FILE",
                tmp_path / "missing_legacy_cache.json",
            ),
        ):
            yield cache

    def test_fetch_deck_text_cache_hit_no_download(self, real_cache):
        """A pre-seeded cache entry is returned without hitting the visual page."""
        real_cache.set("123456", "4 Lightning Bolt", source="mtggoldfish")

        with patch(
            "repositories.scrapers.mtggoldfish_visual.fetch_deck_text_from_visual_page"
        ) as mock_visual:
            result = mtggoldfish.fetch_deck_text("123456")

        assert result == "4 Lightning Bolt"
        mock_visual.assert_not_called()

    def test_fetch_deck_text_mtgo_filter_cache_miss_raises(self, real_cache):
        """source_filter='mtgo' with a cache miss must not fall back to MTGGoldfish
        and instead raises ValueError."""
        with patch(
            "repositories.scrapers.mtggoldfish_visual.fetch_deck_text_from_visual_page"
        ) as mock_visual:
            with pytest.raises(ValueError, match="not available from MTGO source"):
                mtggoldfish.fetch_deck_text("123456", source_filter="mtgo")

        mock_visual.assert_not_called()
        # Nothing was persisted for the missing deck.
        assert real_cache.get("123456") is None

    def test_fetch_deck_text_mtgo_filter_serves_only_mtgo_source(self, real_cache):
        """source_filter='mtgo' returns an mtgo-sourced entry but ignores an
        mtggoldfish-sourced one (the source filter is honored against the real DB)."""
        real_cache.set("mtgo-deck", "4 Island", source="mtgo")
        real_cache.set("goldfish-deck", "4 Mountain", source="mtggoldfish")

        with patch(
            "repositories.scrapers.mtggoldfish_visual.fetch_deck_text_from_visual_page"
        ) as mock_visual:
            assert mtggoldfish.fetch_deck_text("mtgo-deck", source_filter="mtgo") == "4 Island"
            # The mtggoldfish-sourced deck is not visible under the mtgo filter.
            with pytest.raises(ValueError, match="not available from MTGO source"):
                mtggoldfish.fetch_deck_text("goldfish-deck", source_filter="mtgo")

        mock_visual.assert_not_called()

    def test_fetch_deck_text_visual_failure_wrapped_and_not_cached(self, real_cache):
        """A visual-page fetch exception is wrapped in ValueError and the cache is
        not poisoned with a partial/empty entry."""
        with patch(
            "repositories.scrapers.mtggoldfish_visual.fetch_deck_text_from_visual_page",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(ValueError, match="Could not parse deck data"):
                mtggoldfish.fetch_deck_text("123456")

        assert real_cache.get("123456") is None

    def test_fetch_deck_text_successful_download_persists_result(self, real_cache):
        """On a cache miss the deck is downloaded and persisted with source
        'mtggoldfish', and a subsequent fetch is served from the DB."""
        with patch(
            "repositories.scrapers.mtggoldfish_visual.fetch_deck_text_from_visual_page",
            return_value="4 Lightning Bolt",
        ) as mock_visual:
            result = mtggoldfish.fetch_deck_text("123456")

        assert result == "4 Lightning Bolt"
        # Persisted to the real DB under the expected source.
        assert real_cache.get("123456", source="mtggoldfish") == "4 Lightning Bolt"

        # A second fetch is served from cache without re-downloading.
        with patch(
            "repositories.scrapers.mtggoldfish_visual.fetch_deck_text_from_visual_page"
        ) as mock_visual_again:
            assert mtggoldfish.fetch_deck_text("123456") == "4 Lightning Bolt"
        mock_visual_again.assert_not_called()
        mock_visual.assert_called_once_with("123456")


class TestCacheMigration:
    """Test _ensure_cache_migration end-to-end against a real SQLite cache."""

    def setup_method(self):
        # The migration guard is a module-level flag; reset it so each test runs.
        mtggoldfish._migration_attempted = False

    def teardown_method(self):
        mtggoldfish._migration_attempted = False

    def test_migration_imports_json_decks_and_backs_up_file(self, tmp_path):
        """A legacy JSON deck cache is imported into the real SQLite cache and the
        JSON file is renamed to a .json.backup sidecar."""
        from repositories.deck_text_cache import DeckTextCache

        json_path = tmp_path / "deck_text_cache.json"
        json_path.write_text(
            json.dumps({"111": "4 Lightning Bolt", "222": "4 Counterspell"}),
            encoding="utf-8",
        )

        cache = DeckTextCache(tmp_path / "deck_cache.db")
        with (
            patch("repositories.deck_text_cache.get_deck_cache", return_value=cache),
            patch("repositories.scrapers.mtggoldfish.DECK_TEXT_CACHE_FILE", json_path),
        ):
            mtggoldfish._ensure_cache_migration()

        # Decks landed in the real SQLite cache.
        assert cache.get("111") == "4 Lightning Bolt"
        assert cache.get("222") == "4 Counterspell"
        # Original JSON was backed up and removed.
        assert not json_path.exists()
        assert json_path.with_suffix(".json.backup").exists()

    def test_migration_is_noop_when_no_json_cache(self, tmp_path):
        """With no legacy JSON file the migration leaves the SQLite cache empty and
        creates no backup."""
        from repositories.deck_text_cache import DeckTextCache

        json_path = tmp_path / "deck_text_cache.json"  # does not exist
        cache = DeckTextCache(tmp_path / "deck_cache.db")
        with (
            patch("repositories.deck_text_cache.get_deck_cache", return_value=cache),
            patch("repositories.scrapers.mtggoldfish.DECK_TEXT_CACHE_FILE", json_path),
        ):
            mtggoldfish._ensure_cache_migration()

        assert cache.get_stats()["total_decks"] == 0
        assert not json_path.with_suffix(".json.backup").exists()

    def test_migration_runs_only_once(self, tmp_path):
        """The module-level guard prevents a second migration pass; a JSON file
        written after the first call is not imported."""
        from repositories.deck_text_cache import DeckTextCache

        json_path = tmp_path / "deck_text_cache.json"  # absent on first call
        cache = DeckTextCache(tmp_path / "deck_cache.db")
        with (
            patch("repositories.deck_text_cache.get_deck_cache", return_value=cache),
            patch("repositories.scrapers.mtggoldfish.DECK_TEXT_CACHE_FILE", json_path),
        ):
            mtggoldfish._ensure_cache_migration()  # marks attempted, no-op

            json_path.write_text(json.dumps({"999": "4 Brainstorm"}), encoding="utf-8")
            mtggoldfish._ensure_cache_migration()  # guarded -> skipped

        assert cache.get("999") is None
        assert json_path.exists()  # untouched, not backed up


class TestDownloadDeck:
    """Test download_deck function."""

    @patch("repositories.scrapers.mtggoldfish.fetch_deck_text")
    def test_download_deck(self, mock_fetch, temp_curr_deck_file):
        """Test downloading a deck to file."""
        deck_text = "4 Lightning Bolt\n4 Counterspell\n\n3 Duress"
        mock_fetch.return_value = deck_text

        with patch("repositories.scrapers.mtggoldfish.CURR_DECK_FILE", temp_curr_deck_file):
            download_deck("123456")

        assert temp_curr_deck_file.exists()
        assert temp_curr_deck_file.read_text() == deck_text
        mock_fetch.assert_called_once_with("123456", source_filter=None)
