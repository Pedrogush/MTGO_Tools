"""Tests for navigators/mtggoldfish.py module."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from navigators.mtggoldfish import (
    _load_cached_archetypes,
    _save_cached_archetypes,
    download_deck,
    get_archetype_decks,
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
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = _load_cached_archetypes("modern", max_age=3600)
        assert result is None

    def test_load_cached_archetypes_invalid_json(self, temp_archetype_list_file):
        """Test loading archetypes with invalid JSON."""
        temp_archetype_list_file.write_text("invalid json{{{")
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = _load_cached_archetypes("modern", max_age=3600)
            assert result is None

    def test_load_cached_archetypes_missing_format(self, temp_archetype_list_file):
        """Test loading archetypes when format is not in cache."""
        temp_archetype_list_file.write_text(
            json.dumps({"pioneer": {"timestamp": time.time(), "items": []}})
        )
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = _load_cached_archetypes("modern", max_age=3600)
            assert result is None

    def test_load_cached_archetypes_expired(self, temp_archetype_list_file):
        """Test loading archetypes when cache is expired."""
        old_timestamp = time.time() - 7200  # 2 hours ago
        data = {"modern": {"timestamp": old_timestamp, "items": [{"name": "Test", "href": "test"}]}}
        temp_archetype_list_file.write_text(json.dumps(data))
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = _load_cached_archetypes("modern", max_age=3600)  # 1 hour max age
            assert result is None

    def test_load_cached_archetypes_valid(self, temp_archetype_list_file):
        """Test loading valid cached archetypes."""
        items = [{"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"}]
        data = {"modern": {"timestamp": time.time(), "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = _load_cached_archetypes("modern", max_age=3600)
            assert result == items


class TestCacheSaving:
    """Test archetype cache saving functions."""

    def test_save_cached_archetypes_new_file(self, temp_archetype_list_file):
        """Test saving archetypes to a new cache file."""
        items = [{"name": "Rakdos Midrange", "href": "modern-rakdos-midrange"}]
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
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
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            _save_cached_archetypes("modern", modern_items)

        data = json.loads(temp_archetype_list_file.read_text())
        assert "pioneer" in data
        assert "modern" in data
        assert data["modern"]["items"] == modern_items

    def test_save_cached_archetypes_invalid_existing_json(self, temp_archetype_list_file):
        """Test saving archetypes when existing file has invalid JSON."""
        temp_archetype_list_file.write_text("invalid json")

        items = [{"name": "Test", "href": "test"}]
        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
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

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = get_archetypes("modern")
            assert result == items

    @patch("navigators.mtggoldfish.requests.get")
    def test_get_archetypes_from_web(self, mock_get, temp_archetype_list_file):
        """Test fetching archetypes from web when cache is missing."""
        mock_response = Mock()
        mock_response.text = SAMPLE_METAGAME_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = get_archetypes("modern", cache_ttl=0)  # Force cache miss

        assert len(result) == 2
        assert result[0]["name"] == "Rakdos Midrange"
        assert result[0]["href"] == "modern-rakdos-midrange"
        assert result[1]["name"] == "Amulet Titan"
        assert result[1]["href"] == "modern-amulet-titan"

        # Verify cache was saved
        assert temp_archetype_list_file.exists()

    @patch("navigators.mtggoldfish.requests.get")
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

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = get_archetypes("modern", cache_ttl=3600, allow_stale=True)

        assert result == items

    @patch("navigators.mtggoldfish.requests.get")
    def test_get_archetypes_request_failure_no_stale_cache(
        self, mock_get, temp_archetype_list_file
    ):
        """Test that exception is raised when request fails and no stale cache exists."""
        mock_get.side_effect = Exception("Network error")

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            with pytest.raises(Exception, match="Network error"):
                get_archetypes("modern", cache_ttl=0, allow_stale=True)

    @patch("navigators.mtggoldfish.requests.get")
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

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            with pytest.raises(Exception, match="Network error"):
                get_archetypes("modern", cache_ttl=0, allow_stale=False)

    @patch("navigators.mtggoldfish.requests.get")
    def test_get_archetypes_missing_container(self, mock_get, temp_archetype_list_file):
        """Test handling when metagame container is missing from HTML."""
        mock_response = Mock()
        mock_response.text = "<html><body>No container here</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            with pytest.raises(RuntimeError, match="Failed to locate metagame deck container"):
                get_archetypes("modern", cache_ttl=0)

    def test_get_archetypes_case_insensitive_format(self, temp_archetype_list_file):
        """Test that format is case-insensitive."""
        items = [{"name": "Test", "href": "test"}]
        data = {"modern": {"timestamp": time.time(), "items": items}}
        temp_archetype_list_file.write_text(json.dumps(data))

        with patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file):
            result = get_archetypes("MODERN")
            assert result == items


class TestGetArchetypeDecks:
    """Test get_archetype_decks function."""

    @patch("navigators.mtggoldfish.requests.get")
    def test_get_archetype_decks_success(self, mock_get, temp_archetype_decks_file):
        """Test successfully fetching archetype decks."""
        mock_response = Mock()
        mock_response.text = SAMPLE_ARCHETYPE_DECKS_HTML
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch("navigators.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE", temp_archetype_decks_file):
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

    @patch("navigators.mtggoldfish.requests.get")
    def test_get_archetype_decks_request_failure(self, mock_get, temp_archetype_decks_file):
        """Test handling request failure returns cached data."""
        mock_get.side_effect = Exception("Network error")

        # Should return cached data from previous successful test
        with patch("navigators.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE", temp_archetype_decks_file):
            result = get_archetype_decks("modern-rakdos-midrange")
        assert len(result) == 2  # Returns cached data as fallback
        assert result[0]["number"] == "123456"

    @patch("navigators.mtggoldfish.requests.get")
    def test_get_archetype_decks_missing_table(self, mock_get, temp_archetype_decks_file):
        """Test handling missing deck table returns cached data."""
        mock_response = Mock()
        mock_response.text = "<html><body>No table here</body></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Should return cached data from previous successful test
        with patch("navigators.mtggoldfish.ARCHETYPE_DECKS_CACHE_FILE", temp_archetype_decks_file):
            result = get_archetype_decks("modern-rakdos-midrange")
        assert len(result) == 2  # Returns cached data as fallback
        assert result[0]["number"] == "123456"


# NOTE: TestFetchDeckText tests were removed because they tested the old JSON-based
# deck cache which was replaced with SQLite. These tests need to be rewritten to work
# with the new SQLite-based deck cache system.


class TestDownloadDeck:
    """Test download_deck function."""

    @patch("navigators.mtggoldfish.fetch_deck_text")
    def test_download_deck(self, mock_fetch, temp_curr_deck_file):
        """Test downloading a deck to file."""
        deck_text = "4 Lightning Bolt\n4 Counterspell\n\n3 Duress"
        mock_fetch.return_value = deck_text

        with patch("navigators.mtggoldfish.CURR_DECK_FILE", temp_curr_deck_file):
            download_deck("123456")

        assert temp_curr_deck_file.exists()
        assert temp_curr_deck_file.read_text() == deck_text
        mock_fetch.assert_called_once_with("123456", source_filter=None)
