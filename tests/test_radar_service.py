"""Tests for the Radar Service."""

from unittest.mock import MagicMock

import pytest

from repositories.radar_repository import RadarRepository
from services.deck_service import DeckService
from services.radar_service import CardFrequency, RadarData, RadarService


@pytest.fixture
def mock_metagame_repo():
    """Mock metagame repository.

    Only the network-facing methods (``get_decks_for_archetype`` and
    ``download_deck_content``) are exercised, so a plain mock standing in for
    the scraping layer is the only test double the radar tests need.
    """
    repo = MagicMock()
    return repo


@pytest.fixture
def deck_service(mock_metagame_repo):
    """Real DeckService whose only used method is the pure ``analyze_deck`` parser.

    The repositories are mocked because ``analyze_deck`` never touches them; the
    radar path feeds it the decklist strings returned by ``download_deck_content``.
    Using the real parser means the tests verify actual parsing behaviour rather
    than a reimplemented fake.
    """
    return DeckService(deck_repository=MagicMock(), metagame_repository=mock_metagame_repo)


@pytest.fixture
def radar_repo(tmp_path):
    """tmp_path-backed RadarRepository so tests never read the real global cache."""
    return RadarRepository(tmp_path / "radar_cache.db")


@pytest.fixture
def radar_service(mock_metagame_repo, deck_service, radar_repo):
    """RadarService wired with the real deck parser and an isolated radar cache."""
    return RadarService(
        metagame_repository=mock_metagame_repo,
        deck_service=deck_service,
        radar_repository=radar_repo,
    )


@pytest.fixture
def sample_archetype():
    """Sample archetype dictionary."""
    return {"name": "Azorius Control", "url": "https://example.com/archetype"}


@pytest.fixture
def sample_decks():
    """Sample deck list."""
    return [
        {"name": "Deck 1", "url": "https://example.com/deck1"},
        {"name": "Deck 2", "url": "https://example.com/deck2"},
        {"name": "Deck 3", "url": "https://example.com/deck3"},
    ]


def test_calculate_frequencies_basic():
    """Test basic frequency calculation."""
    service = RadarService()
    card_stats = {
        "Lightning Bolt": [4, 4, 4],  # Always a 4-of in 3 decks
        "Counterspell": [2, 2],  # 2-of in 2 out of 3 decks
        "Consider": [4],  # 4-of in 1 out of 3 decks
    }

    frequencies = service._calculate_frequencies(card_stats, total_decks=3)

    # Find each card in results
    bolt = next(f for f in frequencies if f.card_name == "Lightning Bolt")
    counter = next(f for f in frequencies if f.card_name == "Counterspell")
    consider = next(f for f in frequencies if f.card_name == "Consider")

    # Lightning Bolt: 100% inclusion, always 4-of = 4.0 expected copies
    assert bolt.appearances == 3
    assert bolt.total_copies == 12
    assert bolt.max_copies == 4
    assert bolt.avg_copies == 4.0
    assert bolt.inclusion_rate == 100.0
    assert bolt.expected_copies == 4.0
    assert bolt.copy_distribution == {4: 3}

    # Counterspell: 66.7% inclusion, 2-of when present = 1.33 expected copies
    assert counter.appearances == 2
    assert counter.total_copies == 4
    assert counter.max_copies == 2
    assert counter.avg_copies == 2.0
    assert counter.inclusion_rate == pytest.approx(66.7, abs=0.1)
    assert counter.expected_copies == pytest.approx(1.33, abs=0.01)
    assert counter.copy_distribution == {2: 2, 0: 1}

    # Consider: 33.3% inclusion, 4-of when present = 1.33 expected copies
    assert consider.appearances == 1
    assert consider.total_copies == 4
    assert consider.max_copies == 4
    assert consider.avg_copies == 4.0
    assert consider.inclusion_rate == pytest.approx(33.3, abs=0.1)
    assert consider.expected_copies == pytest.approx(1.33, abs=0.01)
    assert consider.copy_distribution == {4: 1, 0: 2}


def test_calculate_radar_success(radar_service, mock_metagame_repo, sample_archetype, sample_decks):
    """Test successful radar calculation using the real deck parser."""
    mock_metagame_repo.get_decks_for_archetype.return_value = sample_decks

    # Real decklist strings; the real DeckService.analyze_deck parses them.
    deck_contents = [
        "4 Lightning Bolt\n3 Island\n\nSideboard\n2 Counterspell",
        "4 Lightning Bolt\n4 Island\n\nSideboard\n1 Counterspell",
        "4 Lightning Bolt\n2 Island\n\nSideboard\n3 Counterspell",
    ]
    mock_metagame_repo.download_deck_content.side_effect = deck_contents

    # Calculate radar
    radar = radar_service.calculate_radar(sample_archetype, "Modern")

    # Verify results
    assert radar.archetype_name == "Azorius Control"
    assert radar.format_name == "Modern"
    assert radar.total_decks_analyzed == 3
    assert radar.decks_failed == 0

    # Check mainboard cards
    assert len(radar.mainboard_cards) == 2  # Lightning Bolt and Island

    # Lightning Bolt should be first (highest expected copies)
    bolt = radar.mainboard_cards[0]
    assert bolt.card_name == "Lightning Bolt"
    assert bolt.inclusion_rate == 100.0
    assert bolt.expected_copies == 4.0

    # Island should be second (varies in count)
    island = radar.mainboard_cards[1]
    assert island.card_name == "Island"
    assert island.inclusion_rate == 100.0

    # Check sideboard
    assert len(radar.sideboard_cards) == 1
    counter = radar.sideboard_cards[0]
    assert counter.card_name == "Counterspell"


def test_calculate_radar_uses_precomputed_snapshot(tmp_path, mock_metagame_repo, deck_service):
    """Test that locally cached precomputed radars short-circuit live calculation."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    repo.replace_radar(
        {
            "format": "modern",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Azorius Control", "href": "modern-azorius-control"},
            "total_decks_analyzed": 50,
            "decks_failed": 0,
            "mainboard_cards": [
                {
                    "card_name": "Counterspell",
                    "appearances": 50,
                    "total_copies": 200,
                    "max_copies": 4,
                    "avg_copies": 4.0,
                    "inclusion_rate": 100.0,
                    "expected_copies": 4.0,
                    "copy_distribution": {4: 50},
                }
            ],
            "sideboard_cards": [],
        }
    )
    service = RadarService(
        metagame_repository=mock_metagame_repo,
        deck_service=deck_service,
        radar_repository=repo,
    )

    radar = service.calculate_radar(
        {"name": "Azorius Control", "href": "modern-azorius-control"},
        "Modern",
        max_decks=50,
    )

    assert radar.total_decks_analyzed == 50
    assert radar.mainboard_cards[0].card_name == "Counterspell"
    mock_metagame_repo.get_decks_for_archetype.assert_not_called()


def test_calculate_radar_handles_failures(
    radar_service, mock_metagame_repo, sample_archetype, sample_decks
):
    """Test radar calculation with some deck failures."""
    mock_metagame_repo.get_decks_for_archetype.return_value = sample_decks

    # First deck succeeds, second fails, third succeeds
    def download_side_effect(deck):
        if deck["name"] == "Deck 2":
            raise Exception("Download failed")
        return "4 Lightning Bolt\n\nSideboard\n2 Counterspell"

    mock_metagame_repo.download_deck_content.side_effect = download_side_effect

    # Calculate radar
    radar = radar_service.calculate_radar(sample_archetype, "Modern")

    # Should have 2 successful decks, 1 failed
    assert radar.total_decks_analyzed == 2
    assert radar.decks_failed == 1


def test_calculate_radar_falls_back_to_live_when_precomputed_snapshot_is_empty(
    tmp_path, mock_metagame_repo, deck_service
):
    """Empty precomputed snapshots should not block live radar scraping."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    repo.replace_radar(
        {
            "format": "modern",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Azorius Control", "href": "modern-azorius-control"},
            "total_decks_analyzed": 0,
            "decks_failed": 0,
            "mainboard_cards": [],
            "sideboard_cards": [],
        }
    )
    mock_metagame_repo.get_decks_for_archetype.return_value = [
        {"name": "Deck 1", "url": "https://example.com/deck1"}
    ]
    mock_metagame_repo.download_deck_content.return_value = (
        "4 Lightning Bolt\n\nSideboard\n2 Counterspell"
    )

    service = RadarService(
        metagame_repository=mock_metagame_repo,
        deck_service=deck_service,
        radar_repository=repo,
    )

    radar = service.calculate_radar(
        {"name": "Azorius Control", "href": "modern-azorius-control"},
        "Modern",
    )

    assert radar.total_decks_analyzed == 1
    assert radar.mainboard_cards[0].card_name == "Lightning Bolt"
    mock_metagame_repo.get_decks_for_archetype.assert_called_once()


def test_export_radar_as_decklist():
    """Test exporting radar as a deck list."""
    service = RadarService()

    # Create sample radar data
    radar = RadarData(
        archetype_name="Test Archetype",
        format_name="Modern",
        mainboard_cards=[
            CardFrequency(
                "Lightning Bolt",
                10,
                40,
                4,
                4.0,
                100.0,
                4.0,
                {4: 10},
            ),
            CardFrequency(
                "Counterspell",
                5,
                10,
                2,
                2.0,
                50.0,
                1.0,
                {2: 5, 0: 5},
            ),
            CardFrequency(
                "Consider",
                3,
                3,
                1,
                1.0,
                30.0,
                0.3,
                {1: 3, 0: 7},
            ),
        ],
        sideboard_cards=[
            CardFrequency(
                "Abrade",
                8,
                16,
                2,
                2.0,
                80.0,
                1.6,
                {2: 8, 0: 2},
            ),
            CardFrequency(
                "Negate",
                2,
                2,
                1,
                1.0,
                20.0,
                0.2,
                {1: 2, 0: 8},
            ),
        ],
        total_decks_analyzed=10,
        decks_failed=0,
    )

    # Export with minimum expected copies of 0.5
    decklist = service.export_radar_as_decklist(radar, min_expected_copies=0.5)

    # Parse the decklist
    decklist.split("\n")

    # Should include Lightning Bolt (4.0 expected), Counterspell (1.0), Abrade (1.6)
    # Should exclude Consider (0.3) and Negate (0.2)
    assert "4 Lightning Bolt" in decklist
    assert "2 Counterspell" in decklist
    assert "2 Abrade" in decklist
    assert "Consider" not in decklist
    assert "Negate" not in decklist

    # Check sideboard section exists
    assert "Sideboard" in decklist


def test_get_radar_card_names():
    """Test extracting card names from radar."""
    service = RadarService()

    radar = RadarData(
        archetype_name="Test",
        format_name="Modern",
        mainboard_cards=[
            CardFrequency("Card A", 1, 1, 1, 1.0, 100.0, 1.0, {1: 1}),
            CardFrequency("Card B", 1, 1, 1, 1.0, 100.0, 1.0, {1: 1}),
        ],
        sideboard_cards=[
            CardFrequency("Card C", 1, 1, 1, 1.0, 100.0, 1.0, {1: 1}),
            CardFrequency("Card D", 1, 1, 1, 1.0, 100.0, 1.0, {1: 1}),
        ],
        total_decks_analyzed=1,
        decks_failed=0,
    )

    # Test getting all cards
    all_cards = service.get_radar_card_names(radar, "both")
    assert all_cards == {"Card A", "Card B", "Card C", "Card D"}

    # Test mainboard only
    mainboard = service.get_radar_card_names(radar, "mainboard")
    assert mainboard == {"Card A", "Card B"}

    # Test sideboard only
    sideboard = service.get_radar_card_names(radar, "sideboard")
    assert sideboard == {"Card C", "Card D"}


def test_calculate_radar_with_max_decks(radar_service, mock_metagame_repo, sample_archetype):
    """Test radar calculation with max_decks limit."""
    # Create 10 decks
    many_decks = [{"name": f"Deck {i}", "url": f"https://example.com/deck{i}"} for i in range(10)]
    mock_metagame_repo.get_decks_for_archetype.return_value = many_decks

    mock_metagame_repo.download_deck_content.return_value = "4 Lightning Bolt"

    # Calculate with max_decks=5
    radar = radar_service.calculate_radar(sample_archetype, "Modern", max_decks=5)

    # Should only process 5 decks
    assert radar.total_decks_analyzed == 5
    assert mock_metagame_repo.download_deck_content.call_count == 5


def test_calculate_radar_downloads_decks_concurrently(
    radar_service, mock_metagame_repo, sample_archetype
):
    """Cache-missing deck downloads should run in parallel, not one at a time."""
    import threading
    import time

    many_decks = [{"name": f"Deck {i}", "url": f"https://example.com/deck{i}"} for i in range(8)]
    mock_metagame_repo.get_decks_for_archetype.return_value = many_decks

    active = 0
    max_active = 0
    lock = threading.Lock()

    def slow_download(deck):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "4 Lightning Bolt"

    mock_metagame_repo.download_deck_content.side_effect = slow_download

    progress_calls = []

    def progress_callback(current, total, deck_name):
        progress_calls.append((current, total, deck_name))

    radar = radar_service.calculate_radar(
        sample_archetype, "Modern", progress_callback=progress_callback
    )

    assert radar.total_decks_analyzed == 8
    # Downloads overlapped (serial execution would never exceed 1 in flight).
    assert max_active > 1
    # Progress fired once per deck with a monotonically increasing counter.
    assert len(progress_calls) == 8
    assert [c[0] for c in progress_calls] == list(range(1, 9))
    assert all(c[1] == 8 for c in progress_calls)


def test_calculate_radar_progress_callback_can_cancel(
    radar_service, mock_metagame_repo, sample_archetype
):
    """A progress callback raising should abort generation and propagate."""
    many_decks = [{"name": f"Deck {i}", "url": f"https://example.com/deck{i}"} for i in range(8)]
    mock_metagame_repo.get_decks_for_archetype.return_value = many_decks

    mock_metagame_repo.download_deck_content.return_value = "4 Lightning Bolt"

    calls = []

    def cancelling_callback(current, total, deck_name):
        calls.append(current)
        raise InterruptedError("cancelled by user")

    with pytest.raises(InterruptedError):
        radar_service.calculate_radar(
            sample_archetype, "Modern", progress_callback=cancelling_callback
        )

    # Cancelling on the first completed deck must not keep analyzing the rest.
    assert len(calls) == 1


def test_calculate_radar_no_decks_found(radar_service, mock_metagame_repo, sample_archetype):
    """An archetype with no decks returns an empty, zero-count radar."""
    mock_metagame_repo.get_decks_for_archetype.return_value = []

    radar = radar_service.calculate_radar(sample_archetype, "Modern")

    assert radar.archetype_name == "Azorius Control"
    assert radar.format_name == "Modern"
    assert radar.total_decks_analyzed == 0
    assert radar.decks_failed == 0
    assert radar.mainboard_cards == []
    assert radar.sideboard_cards == []
    # Without any decks we never attempt a download.
    mock_metagame_repo.download_deck_content.assert_not_called()


def test_calculate_radar_all_decks_fail(
    radar_service, mock_metagame_repo, sample_archetype, sample_decks
):
    """When every deck fails to download, the radar reports zero analyzed/all failed."""
    mock_metagame_repo.get_decks_for_archetype.return_value = sample_decks

    # Every download raises, so successful_decks stays at 0 and the parser is
    # never reached.
    mock_metagame_repo.download_deck_content.side_effect = Exception("Download failed")

    radar = radar_service.calculate_radar(sample_archetype, "Modern")

    assert radar.total_decks_analyzed == 0
    assert radar.decks_failed == len(sample_decks)
    assert radar.mainboard_cards == []
    assert radar.sideboard_cards == []


def test_calculate_radar_rejects_precomputed_snapshot_larger_than_max_decks(
    tmp_path, mock_metagame_repo, deck_service
):
    """A cached snapshot with more decks than max_decks falls back to live scraping."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    repo.replace_radar(
        {
            "format": "modern",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Azorius Control", "href": "modern-azorius-control"},
            "total_decks_analyzed": 50,
            "decks_failed": 0,
            "mainboard_cards": [
                {
                    "card_name": "Counterspell",
                    "appearances": 50,
                    "total_copies": 200,
                    "max_copies": 4,
                    "avg_copies": 4.0,
                    "inclusion_rate": 100.0,
                    "expected_copies": 4.0,
                    "copy_distribution": {4: 50},
                }
            ],
            "sideboard_cards": [],
        }
    )
    mock_metagame_repo.get_decks_for_archetype.return_value = [
        {"name": "Deck 1", "url": "https://example.com/deck1"}
    ]
    mock_metagame_repo.download_deck_content.return_value = "4 Lightning Bolt"

    service = RadarService(
        metagame_repository=mock_metagame_repo,
        deck_service=deck_service,
        radar_repository=repo,
    )

    # The snapshot has 50 decks but the caller asked for at most 10, so the
    # snapshot must be rejected and the live path used instead.
    radar = service.calculate_radar(
        {"name": "Azorius Control", "href": "modern-azorius-control"},
        "Modern",
        max_decks=10,
    )

    assert radar.total_decks_analyzed == 1
    assert radar.mainboard_cards[0].card_name == "Lightning Bolt"
    mock_metagame_repo.get_decks_for_archetype.assert_called_once()


def _store_usage_snapshot(repo):
    """Seed a format with two archetype radars sharing a card for usage rollups."""
    repo.replace_radar(
        {
            "format": "modern",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Azorius Control", "href": "modern-azorius-control"},
            "total_decks_analyzed": 10,
            "decks_failed": 0,
            "mainboard_cards": [
                {
                    "card_name": "Counterspell",
                    "appearances": 8,
                    "total_copies": 24,
                    "max_copies": 4,
                    "avg_copies": 3.0,
                    "inclusion_rate": 80.0,
                    "expected_copies": 2.4,
                    "copy_distribution": {4: 4, 2: 4, 0: 2},
                }
            ],
            "sideboard_cards": [
                {
                    "card_name": "Negate",
                    "appearances": 5,
                    "total_copies": 5,
                    "max_copies": 1,
                    "avg_copies": 1.0,
                    "inclusion_rate": 50.0,
                    "expected_copies": 0.5,
                    "copy_distribution": {1: 5, 0: 5},
                }
            ],
        }
    )
    repo.replace_radar(
        {
            "format": "modern",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Dimir Control", "href": "modern-dimir-control"},
            "total_decks_analyzed": 5,
            "decks_failed": 0,
            "mainboard_cards": [
                {
                    "card_name": "Counterspell",
                    "appearances": 5,
                    "total_copies": 16,
                    "max_copies": 4,
                    "avg_copies": 3.2,
                    "inclusion_rate": 100.0,
                    "expected_copies": 3.2,
                    "copy_distribution": {4: 3, 2: 2},
                }
            ],
            "sideboard_cards": [],
        }
    )


def test_get_card_usage_stats_rolls_up_across_archetypes(tmp_path, mock_metagame_repo):
    """Usage stats sum copies/appearances across every archetype radar in a format."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    _store_usage_snapshot(repo)
    service = RadarService(metagame_repository=mock_metagame_repo, radar_repository=repo)

    stats = service.get_card_usage_stats("Modern", ["Counterspell", "Negate"])

    counter = stats["Counterspell"]
    # 10 + 5 decks analyzed across the two archetype radars.
    assert counter.total_decks == 15
    # Mainboard copies/appearances roll up across both archetypes.
    assert counter.mainboard_copies == 40
    assert counter.mainboard_decks_present == 13
    assert counter.mainboard_archetypes == 2
    assert counter.sideboard_archetypes == 0
    # Karsten avg = copies / decks present; arithmetic = copies / total decks.
    assert counter.mainboard_avg_karsten == pytest.approx(40 / 13)
    assert counter.mainboard_avg_arithmetic == pytest.approx(40 / 15)

    negate = stats["Negate"]
    assert negate.sideboard_copies == 5
    assert negate.sideboard_decks_present == 5
    assert negate.sideboard_avg_karsten == pytest.approx(1.0)
    assert negate.sideboard_avg_arithmetic == pytest.approx(5 / 15)


def test_get_card_usage_stats_missing_card_is_zeroed(tmp_path, mock_metagame_repo):
    """A card absent from every radar yields a zero-filled entry with None averages."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    _store_usage_snapshot(repo)
    service = RadarService(metagame_repository=mock_metagame_repo, radar_repository=repo)

    stats = service.get_card_usage_stats("Modern", ["Black Lotus"])

    lotus = stats["Black Lotus"]
    assert lotus.mainboard_copies == 0
    assert lotus.sideboard_copies == 0
    assert lotus.mainboard_decks_present == 0
    assert lotus.sideboard_decks_present == 0
    # No decks present -> Karsten averages are None even though total_decks > 0.
    assert lotus.mainboard_avg_karsten is None
    assert lotus.sideboard_avg_karsten is None
    # Arithmetic averages over the format's total decks are still defined (0.0).
    assert lotus.mainboard_avg_arithmetic == 0.0


def test_get_card_usage_stats_blank_names_return_empty(tmp_path, mock_metagame_repo):
    """All-blank card-name input short-circuits to an empty mapping."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    service = RadarService(metagame_repository=mock_metagame_repo, radar_repository=repo)

    assert service.get_card_usage_stats("Modern", ["", "   "]) == {}


def test_get_card_usage_stats_zero_total_decks_averages_none(tmp_path, mock_metagame_repo):
    """When the format has no analyzed decks, arithmetic averages are None."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    # A radar with zero analyzed decks but a stored card row.
    repo.replace_radar(
        {
            "format": "modern",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Empty", "href": "modern-empty"},
            "total_decks_analyzed": 0,
            "decks_failed": 0,
            "mainboard_cards": [
                {
                    "card_name": "Counterspell",
                    "appearances": 0,
                    "total_copies": 0,
                    "max_copies": 0,
                    "avg_copies": 0.0,
                    "inclusion_rate": 0.0,
                    "expected_copies": 0.0,
                    "copy_distribution": {},
                }
            ],
            "sideboard_cards": [],
        }
    )
    service = RadarService(metagame_repository=mock_metagame_repo, radar_repository=repo)

    stats = service.get_card_usage_stats("Modern", ["Counterspell"])
    counter = stats["Counterspell"]
    assert counter.total_decks == 0
    assert counter.mainboard_avg_arithmetic is None
    assert counter.sideboard_avg_arithmetic is None


def test_get_effective_legalities_filters_blanks_and_lists_formats(tmp_path, mock_metagame_repo):
    """Effective legality maps each card to the formats whose radars include it."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    _store_usage_snapshot(repo)
    # Same card appearing in a second format establishes multi-format membership.
    repo.replace_radar(
        {
            "format": "legacy",
            "generated_at": "2026-03-26T12:00:00Z",
            "source": "published-deck-texts",
            "archetype": {"name": "Legacy Control", "href": "legacy-control"},
            "total_decks_analyzed": 3,
            "decks_failed": 0,
            "mainboard_cards": [
                {
                    "card_name": "Counterspell",
                    "appearances": 3,
                    "total_copies": 12,
                    "max_copies": 4,
                    "avg_copies": 4.0,
                    "inclusion_rate": 100.0,
                    "expected_copies": 4.0,
                    "copy_distribution": {4: 3},
                }
            ],
            "sideboard_cards": [],
        }
    )
    service = RadarService(metagame_repository=mock_metagame_repo, radar_repository=repo)

    legalities = service.get_effective_legalities(["Counterspell", "Negate", "  "])

    # Blank names are filtered out entirely.
    assert "  " not in legalities
    # Counterspell appears in both formats; Negate only in modern (sideboard).
    assert legalities["Counterspell"] == ["legacy", "modern"]
    assert legalities["Negate"] == ["modern"]


def test_get_effective_legalities_blank_names_return_empty(tmp_path, mock_metagame_repo):
    """All-blank input short-circuits to an empty mapping."""
    repo = RadarRepository(tmp_path / "radar_cache.db")
    service = RadarService(metagame_repository=mock_metagame_repo, radar_repository=repo)

    assert service.get_effective_legalities(["", "   "]) == {}
