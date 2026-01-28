"""
Radar Service - Business logic for archetype card frequency analysis.

This module provides functionality for analyzing card frequencies across all decks
in a specific archetype, tracking which cards appear and how often.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from services.deck_service import DeckService, get_deck_service
from utils.constants import (
    RADAR_AVG_COPIES_ROUND_DIGITS,
    RADAR_EXPECTED_COPIES_ROUND_DIGITS,
    RADAR_INCLUSION_RATE_ROUND_DIGITS,
    RADAR_MIN_COPY_COUNT,
    RADAR_MIN_EXPECTED_COPIES_DEFAULT,
)


@dataclass
class CardFrequency:
    """Statistics for a card's appearance in an archetype."""

    card_name: str
    appearances: int  # Number of decks containing this card
    total_copies: int  # Total copies across all decks
    max_copies: int  # Maximum copies in a single deck
    avg_copies: float  # Average copies when present
    inclusion_rate: float  # % of decks containing this card
    expected_copies: float  # Average copies per deck across the sample
    copy_distribution: dict[int, int]  # Deck counts keyed by number of copies


@dataclass
class RadarData:
    """Complete radar data for an archetype."""

    archetype_name: str
    format_name: str
    mainboard_cards: list[CardFrequency]
    sideboard_cards: list[CardFrequency]
    total_decks_analyzed: int
    decks_failed: int


class RadarService:
    """Service for calculating archetype radar (card frequency analysis)."""

    def __init__(
        self,
        metagame_repository: MetagameRepository | None = None,
        deck_service: DeckService | None = None,
    ):
        """
        Initialize the radar service.

        Args:
            metagame_repository: MetagameRepository instance
            deck_service: DeckService instance
        """
        self.metagame_repo = metagame_repository or get_metagame_repository()
        self.deck_service = deck_service or get_deck_service()

    def calculate_radar(
        self,
        archetype: dict[str, Any],
        format_name: str,
        max_decks: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> RadarData:
        """
        Calculate radar data for a specific archetype.

        Args:
            archetype: Archetype dictionary with 'url' and 'name' keys
            format_name: MTG format (e.g., "Modern", "Standard")
            max_decks: Maximum number of decks to analyze (None = all)
            progress_callback: Optional callback(current, total, deck_name)

        Returns:
            RadarData with frequency statistics
        """
        archetype_name = archetype.get("name", "Unknown")
        logger.info(f"Calculating radar for {archetype_name} in {format_name}")

        try:
            # Fetch all decks for this archetype
            decks = self.metagame_repo.get_decks_for_archetype(archetype)

            if not decks:
                logger.warning(f"No decks found for {archetype_name}")
                return RadarData(
                    archetype_name=archetype_name,
                    format_name=format_name,
                    mainboard_cards=[],
                    sideboard_cards=[],
                    total_decks_analyzed=0,
                    decks_failed=0,
                )

            # Limit decks if specified
            if max_decks is not None:
                decks = decks[:max_decks]

            # Track card appearances
            mainboard_stats: dict[str, list[int]] = defaultdict(list)
            sideboard_stats: dict[str, list[int]] = defaultdict(list)
            successful_decks = 0
            failed_decks = 0

            # Analyze each deck
            for i, deck in enumerate(decks):
                deck_name = deck.get("name", f"Deck {i+1}")

                if progress_callback:
                    progress_callback(i + 1, len(decks), deck_name)

                try:
                    # Download deck content
                    deck_content = self.metagame_repo.download_deck_content(deck)

                    # Analyze deck structure
                    analysis = self.deck_service.analyze_deck(deck_content)

                    # Record mainboard card counts
                    for card_name, count in analysis["mainboard_cards"]:
                        # Convert to int (in case it's a float from averaging)
                        count_int = int(count) if isinstance(count, float) else count
                        mainboard_stats[card_name].append(count_int)

                    # Record sideboard card counts
                    for card_name, count in analysis["sideboard_cards"]:
                        count_int = int(count) if isinstance(count, float) else count
                        sideboard_stats[card_name].append(count_int)

                    successful_decks += 1

                except Exception as exc:
                    logger.warning(f"Failed to analyze deck {deck_name}: {exc}")
                    failed_decks += 1
                    continue

            if successful_decks == 0:
                logger.error(f"Failed to analyze any decks for {archetype_name}")
                return RadarData(
                    archetype_name=archetype_name,
                    format_name=format_name,
                    mainboard_cards=[],
                    sideboard_cards=[],
                    total_decks_analyzed=0,
                    decks_failed=failed_decks,
                )

            # Calculate frequency statistics
            mainboard_frequencies = self._calculate_frequencies(mainboard_stats, successful_decks)
            sideboard_frequencies = self._calculate_frequencies(sideboard_stats, successful_decks)

            # Sort by expected copies (descending)
            mainboard_frequencies.sort(
                key=lambda x: (x.expected_copies, x.inclusion_rate), reverse=True
            )
            sideboard_frequencies.sort(
                key=lambda x: (x.expected_copies, x.inclusion_rate), reverse=True
            )

            logger.info(
                f"Radar calculated: {len(mainboard_frequencies)} mainboard cards, "
                f"{len(sideboard_frequencies)} sideboard cards from {successful_decks} decks"
            )

            return RadarData(
                archetype_name=archetype_name,
                format_name=format_name,
                mainboard_cards=mainboard_frequencies,
                sideboard_cards=sideboard_frequencies,
                total_decks_analyzed=successful_decks,
                decks_failed=failed_decks,
            )

        except Exception as exc:
            logger.error(f"Failed to calculate radar for {archetype_name}: {exc}")
            raise

    def _calculate_frequencies(
        self, card_stats: dict[str, list[int]], total_decks: int
    ) -> list[CardFrequency]:
        """
        Calculate frequency statistics for a set of cards.

        Args:
            card_stats: Dictionary mapping card names to list of counts (one per deck)
            total_decks: Total number of decks analyzed

        Returns:
            List of CardFrequency objects
        """
        frequencies = []

        for card_name, counts in card_stats.items():
            appearances = len(counts)
            total_copies = sum(counts)
            max_copies = max(counts)
            avg_copies = total_copies / appearances if appearances > 0 else 0

            # Inclusion rate: what % of decks include this card
            inclusion_rate = (appearances / total_decks) * 100 if total_decks > 0 else 0

            # Expected copies across all analyzed decks (including decks with 0 copies)
            expected_copies = total_copies / total_decks if total_decks > 0 else 0

            # Build distribution including decks that don't run the card
            copy_distribution: dict[int, int] = defaultdict(int)
            for count in counts:
                copy_distribution[count] += 1
            zero_count = max(total_decks - appearances, 0)
            if zero_count:
                copy_distribution[0] += zero_count

            frequencies.append(
                CardFrequency(
                    card_name=card_name,
                    appearances=appearances,
                    total_copies=total_copies,
                    max_copies=max_copies,
                    avg_copies=round(avg_copies, RADAR_AVG_COPIES_ROUND_DIGITS),
                    inclusion_rate=round(inclusion_rate, RADAR_INCLUSION_RATE_ROUND_DIGITS),
                    expected_copies=round(expected_copies, RADAR_EXPECTED_COPIES_ROUND_DIGITS),
                    copy_distribution=dict(sorted(copy_distribution.items(), reverse=True)),
                )
            )

        return frequencies

    def export_radar_as_decklist(
        self,
        radar: RadarData,
        min_expected_copies: float = RADAR_MIN_EXPECTED_COPIES_DEFAULT,
        max_cards: int | None = None,
    ) -> str:
        """
        Export radar data as a standard deck list format.

        Cards are included based on their average count when present,
        filtered by minimum expected copies per deck.

        Args:
            radar: RadarData to export
            min_expected_copies: Minimum expected copies to include (0-4+)
            max_cards: Maximum number of cards to include per zone (None = all)

        Returns:
            Deck list as text
        """
        lines = []

        # Filter and format mainboard
        mainboard = [
            card for card in radar.mainboard_cards if card.expected_copies >= min_expected_copies
        ]
        if max_cards is not None:
            mainboard = mainboard[:max_cards]

        for card in mainboard:
            # Use average copies rounded to nearest integer
            count = max(RADAR_MIN_COPY_COUNT, round(card.avg_copies))
            lines.append(f"{count} {card.card_name}")

        # Add sideboard section
        sideboard = [
            card for card in radar.sideboard_cards if card.expected_copies >= min_expected_copies
        ]
        if max_cards is not None:
            sideboard = sideboard[:max_cards]

        if sideboard:
            lines.append("")
            lines.append("Sideboard")
            for card in sideboard:
                count = max(RADAR_MIN_COPY_COUNT, round(card.avg_copies))
                lines.append(f"{count} {card.card_name}")

        return "\n".join(lines)

    def get_radar_card_names(self, radar: RadarData, zone: str = "both") -> set[str]:
        """
        Get set of all card names in the radar.

        Args:
            radar: RadarData to extract from
            zone: "mainboard", "sideboard", or "both"

        Returns:
            Set of card names
        """
        cards = set()

        if zone in ("mainboard", "both"):
            cards.update(card.card_name for card in radar.mainboard_cards)

        if zone in ("sideboard", "both"):
            cards.update(card.card_name for card in radar.sideboard_cards)

        return cards


# Global instance for backward compatibility
_default_service = None


def get_radar_service() -> RadarService:
    """Get the default radar service instance."""
    global _default_service
    if _default_service is None:
        _default_service = RadarService()
    return _default_service


def reset_radar_service() -> None:
    """
    Reset the global radar service instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_service
    _default_service = None


__all__ = [
    "RadarService",
    "RadarData",
    "CardFrequency",
    "get_radar_service",
    "reset_radar_service",
]
