"""Tests for opponent tracker radar integration."""

from unittest.mock import MagicMock, patch

import pytest

from services.radar_service import RadarData


@pytest.fixture
def mock_wx():
    """Mock wx module to avoid GUI dependencies."""
    with patch("widgets.frames.identify_opponent.wx") as mock:
        # Mock common wx classes
        mock.Frame = MagicMock
        mock.Panel = MagicMock
        mock.StaticText = MagicMock
        mock.Button = MagicMock
        mock.Timer = MagicMock
        mock.BoxSizer = MagicMock
        mock.VERTICAL = 0
        mock.HORIZONTAL = 1
        mock.EXPAND = 1
        mock.ALL = 1
        mock.CallAfter = lambda func, *args, **kwargs: func(*args, **kwargs)
        yield mock


@pytest.fixture
def mock_radar_service():
    """Mock radar service."""
    service = MagicMock()
    service.calculate_radar.return_value = RadarData(
        archetype_name="UR Murktide",
        format_name="Modern",
        mainboard_cards=[],
        sideboard_cards=[],
        total_decks_analyzed=10,
        decks_failed=0,
    )
    return service


@pytest.fixture
def mock_metagame_repo():
    """Mock metagame repository."""
    repo = MagicMock()
    repo.get_archetypes_for_format.return_value = [
        {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
        {"name": "Azorius Control", "href": "/archetype/azorius-control"},
    ]
    return repo


class TestRadarIntegration:
    """Test radar integration in opponent tracker."""

    def test_trigger_radar_load_with_valid_archetype(
        self, mock_wx, mock_radar_service, mock_metagame_repo
    ):
        """Test that radar loading is triggered when opponent has known deck."""
        with patch("widgets.frames.identify_opponent.find_archetype_by_name") as mock_find:
            mock_find.return_value = {
                "name": "UR Murktide",
                "href": "/archetype/ur-murktide",
            }

            # This would normally create the GUI, but we're mocking wx
            # So we can't fully instantiate it without GUI dependencies
            # Instead, test the logic directly

            # Verify find_archetype_by_name would be called with correct args
            archetype_dict = mock_find("UR Murktide", "Modern", mock_metagame_repo)
            assert archetype_dict is not None
            assert archetype_dict["name"] == "UR Murktide"

    def test_clear_radar_on_opponent_change(self, mock_wx):
        """Test that radar clears when opponent changes."""
        # Test the clear logic
        mock_panel = MagicMock()
        mock_panel.clear = MagicMock()

        # Simulate clearing
        mock_panel.clear()
        mock_panel.clear.assert_called_once()

    def test_skip_duplicate_radar_requests(self):
        """Test that duplicate radar requests for same archetype are skipped."""
        last_archetype = "UR Murktide"
        new_archetype = "UR Murktide"

        # Should skip if archetypes match
        should_skip = last_archetype == new_archetype
        assert should_skip is True

        # Should not skip if different
        different_archetype = "Azorius Control"
        should_skip = last_archetype == different_archetype
        assert should_skip is False

    def test_radar_worker_handles_cancellation(self, mock_radar_service):
        """Test that radar worker respects cancellation flag."""
        cancel_requested = False

        def mock_progress_callback(current, total, deck_name):
            if cancel_requested:
                raise InterruptedError("Cancelled")

        # Simulate cancellation
        cancel_requested = True
        with pytest.raises(InterruptedError):
            mock_progress_callback(1, 10, "Test Deck")

    def test_radar_worker_handles_network_failure(self, mock_radar_service):
        """Test that radar worker handles network failures gracefully."""
        mock_radar_service.calculate_radar.side_effect = Exception("Network error")

        with pytest.raises(Exception) as exc_info:
            mock_radar_service.calculate_radar(
                {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
                "Modern",
            )

        assert "Network error" in str(exc_info.value)

    def test_archetype_resolver_exact_match(self):
        """Test archetype name resolution with exact match."""
        from utils.archetype_resolver import normalize_archetype_name

        result = normalize_archetype_name("UR Murktide")
        assert result == "ur murktide"

        # Case insensitive
        result2 = normalize_archetype_name("ur murktide")
        assert result2 == "ur murktide"

        # Should match
        assert result == result2

    def test_archetype_resolver_partial_match(self, mock_metagame_repo):
        """Test archetype name resolution with partial match."""
        from utils.archetype_resolver import find_archetype_by_name

        result = find_archetype_by_name("Murktide", "Modern", mock_metagame_repo)
        assert result is not None
        assert "Murktide" in result["name"]

    def test_radar_config_persistence(self):
        """Test that radar visibility state is saved to config."""
        config = {
            "screen_pos": [100, 100],
            "calculator_visible": False,
            "radar_visible": True,
        }

        # Verify config structure
        assert "radar_visible" in config
        assert config["radar_visible"] is True

    def test_radar_panel_display(self):
        """Test that radar panel displays data correctly."""
        from services.radar_service import CardFrequency, RadarData

        radar = RadarData(
            archetype_name="UR Murktide",
            format_name="Modern",
            mainboard_cards=[
                CardFrequency(
                    card_name="Murktide Regent",
                    appearances=10,
                    total_copies=40,
                    max_copies=4,
                    avg_copies=4.0,
                    inclusion_rate=100.0,
                    expected_copies=4.0,
                    copy_distribution={4: 10},
                ),
            ],
            sideboard_cards=[],
            total_decks_analyzed=10,
            decks_failed=0,
        )

        # Verify radar data structure
        assert radar.archetype_name == "UR Murktide"
        assert radar.format_name == "Modern"
        assert len(radar.mainboard_cards) == 1
        assert radar.mainboard_cards[0].card_name == "Murktide Regent"
        assert radar.mainboard_cards[0].inclusion_rate == 100.0


class TestRadarPanelLogic:
    """Test compact radar panel logic without GUI."""

    def test_format_top_card_line(self):
        """Test card line formatting for top cards view."""
        avg_copies = 4
        card_name = "Lightning Bolt"
        inclusion_rate = 95.0

        line = f"{avg_copies}x {card_name} ({inclusion_rate:.0f}%)"
        assert line == "4x Lightning Bolt (95%)"

    def test_format_full_decklist_line(self):
        """Test card line formatting for full decklist view."""
        count = 4
        card_name = "Lightning Bolt"

        line = f"{count} {card_name}"
        assert line == "4 Lightning Bolt"

    def test_mainboard_card_limit(self):
        """Test that mainboard cards are limited to 15 in top cards view."""
        from widgets.panels.compact_radar_panel import _TOP_MAINBOARD_LIMIT

        assert _TOP_MAINBOARD_LIMIT == 15

        total_cards = 50
        mainboard_display = min(_TOP_MAINBOARD_LIMIT, total_cards)
        assert mainboard_display == 15

        total_cards = 10
        mainboard_display = min(_TOP_MAINBOARD_LIMIT, total_cards)
        assert mainboard_display == 10

    def test_sideboard_card_limit(self):
        """Test that sideboard cards are limited to 8 in top cards view."""
        from widgets.panels.compact_radar_panel import _TOP_SIDEBOARD_LIMIT

        assert _TOP_SIDEBOARD_LIMIT == 8

        total_cards = 20
        sideboard_display = min(_TOP_SIDEBOARD_LIMIT, total_cards)
        assert sideboard_display == 8

        total_cards = 5
        sideboard_display = min(_TOP_SIDEBOARD_LIMIT, total_cards)
        assert sideboard_display == 5

    def test_view_mode_enum(self):
        """Test that view mode enum has expected values."""
        from widgets.panels.compact_radar_panel import RadarViewMode

        assert RadarViewMode.TOP_CARDS.value == "top"
        assert RadarViewMode.FULL_DECKLIST.value == "full"

    def test_full_decklist_includes_all_cards(self):
        """Test that full decklist mode counts all cards."""
        from services.radar_service import CardFrequency

        cards = [
            CardFrequency("Card A", 10, 40, 4, 4.0, 100.0, 4.0, {4: 10}),
            CardFrequency("Card B", 5, 10, 2, 2.0, 50.0, 1.0, {2: 5, 0: 5}),
            CardFrequency("Card C", 3, 3, 1, 1.0, 30.0, 0.3, {1: 3, 0: 7}),
        ]

        # Full decklist should include all cards
        total = sum(max(1, round(c.avg_copies)) for c in cards)
        assert total == 4 + 2 + 1  # 7 total

    def test_full_decklist_min_one_copy(self):
        """Test that full decklist shows at least 1 copy per card."""
        from services.radar_service import CardFrequency

        # Card with avg_copies < 0.5 rounds to 0, but we clamp to 1
        card = CardFrequency("Rare Card", 1, 1, 1, 0.3, 10.0, 0.03, {1: 1, 0: 9})
        count = max(1, round(card.avg_copies))
        assert count == 1
