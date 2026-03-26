"""Tests for the Radar Service."""

from unittest.mock import MagicMock

import pytest

from repositories.radar_repository import RadarRepository
from services.radar_service import CardFrequency, RadarData, RadarService


@pytest.fixture
def mock_metagame_repo():
    """Mock metagame repository."""
    repo = MagicMock()
    return repo


@pytest.fixture
def mock_deck_service():
    """Mock deck service."""
    service = MagicMock()
    return service


@pytest.fixture
def radar_service(mock_metagame_repo, mock_deck_service):
    """RadarService with mocked dependencies."""
    return RadarService(metagame_repository=mock_metagame_repo, deck_service=mock_deck_service)


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


def test_calculate_radar_success(
    radar_service, mock_metagame_repo, mock_deck_service, sample_archetype, sample_decks
):
    """Test successful radar calculation."""
    # Setup mocks
    mock_metagame_repo.get_decks_for_archetype.return_value = sample_decks

    # Mock deck downloads
    deck_contents = [
        "4 Lightning Bolt\n3 Island\n\nSideboard\n2 Counterspell",
        "4 Lightning Bolt\n4 Island\n\nSideboard\n1 Counterspell",
        "4 Lightning Bolt\n2 Island\n\nSideboard\n3 Counterspell",
    ]
    mock_metagame_repo.download_deck_content.side_effect = deck_contents

    # Mock deck analysis
    def mock_analyze(content):
        lines = content.split("\n")
        mainboard = []
        sideboard = []
        is_side = False

        for line in lines:
            if not line.strip():
                is_side = True
                continue
            if line.lower() == "sideboard":
                continue

            parts = line.split(" ", 1)
            if len(parts) == 2:
                count = int(parts[0])
                name = parts[1]
                if is_side:
                    sideboard.append((name, count))
                else:
                    mainboard.append((name, count))

        return {
            "mainboard_cards": mainboard,
            "sideboard_cards": sideboard,
            "mainboard_count": sum(c for _, c in mainboard),
            "sideboard_count": sum(c for _, c in sideboard),
        }

    mock_deck_service.analyze_deck.side_effect = mock_analyze

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


def test_calculate_radar_uses_precomputed_snapshot(tmp_path, mock_metagame_repo, mock_deck_service):
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
        deck_service=mock_deck_service,
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
    radar_service, mock_metagame_repo, mock_deck_service, sample_archetype, sample_decks
):
    """Test radar calculation with some deck failures."""
    mock_metagame_repo.get_decks_for_archetype.return_value = sample_decks

    # First deck succeeds, second fails, third succeeds
    def download_side_effect(deck):
        if deck["name"] == "Deck 2":
            raise Exception("Download failed")
        return "4 Lightning Bolt\n\nSideboard\n2 Counterspell"

    mock_metagame_repo.download_deck_content.side_effect = download_side_effect

    mock_deck_service.analyze_deck.return_value = {
        "mainboard_cards": [("Lightning Bolt", 4)],
        "sideboard_cards": [("Counterspell", 2)],
    }

    # Calculate radar
    radar = radar_service.calculate_radar(sample_archetype, "Modern")

    # Should have 2 successful decks, 1 failed
    assert radar.total_decks_analyzed == 2
    assert radar.decks_failed == 1


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


def test_calculate_radar_with_max_decks(
    radar_service, mock_metagame_repo, mock_deck_service, sample_archetype
):
    """Test radar calculation with max_decks limit."""
    # Create 10 decks
    many_decks = [{"name": f"Deck {i}", "url": f"https://example.com/deck{i}"} for i in range(10)]
    mock_metagame_repo.get_decks_for_archetype.return_value = many_decks

    mock_metagame_repo.download_deck_content.return_value = "4 Lightning Bolt"
    mock_deck_service.analyze_deck.return_value = {
        "mainboard_cards": [("Lightning Bolt", 4)],
        "sideboard_cards": [],
    }

    # Calculate with max_decks=5
    radar = radar_service.calculate_radar(sample_archetype, "Modern", max_decks=5)

    # Should only process 5 decks
    assert radar.total_decks_analyzed == 5
    assert mock_metagame_repo.download_deck_content.call_count == 5
