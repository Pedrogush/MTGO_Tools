"""
Deck Service - Business logic for deck operations.

This module contains all the business logic for working with decks including:
- Deck parsing and analysis
- Deck averaging and aggregation
- Deck validation
- Format compliance checking
- Zone management
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from repositories.deck_repository import DeckRepository, get_deck_repository
from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from services.deck_averager import DeckAverager
from services.deck_parser import DeckParser


@dataclass(frozen=True)
class ZoneUpdateResult:
    """Result of updating deck zones."""

    deck_text: str
    has_loaded_deck: bool


class DeckService:
    """Service for deck-related business logic."""

    def __init__(
        self,
        deck_repository: DeckRepository | None = None,
        metagame_repository: MetagameRepository | None = None,
        deck_parser: DeckParser | None = None,
        deck_averager: DeckAverager | None = None,
    ):
        """
        Initialize the deck service.

        Args:
            deck_repository: DeckRepository instance
            metagame_repository: MetagameRepository instance
        """
        self.deck_repo = deck_repository or get_deck_repository()
        self.metagame_repo = metagame_repository or get_metagame_repository()
        self.deck_parser = deck_parser or DeckParser()
        self.deck_averager = deck_averager or DeckAverager(self.deck_parser)

    # ============= Deck Parsing and Analysis =============

    def deck_to_dictionary(self, deck_text: str) -> dict[str, float]:
        """
        Convert deck text to a dictionary representation.

        Args:
            deck_text: Deck list as text (format: "quantity card_name")

        Returns:
            Dictionary mapping card names to quantities (floats to preserve averages)
            Sideboard cards are prefixed with "Sideboard "
        """
        return self.deck_parser.deck_to_dictionary(deck_text)

    def analyze_deck(self, deck_content: str) -> dict[str, Any]:
        """
        Analyze a deck and return statistics.

        Args:
            deck_content: Deck list as text

        Returns:
            Dictionary with keys:
                - mainboard_count: int
                - sideboard_count: int
                - total_cards: int
                - unique_mainboard: int
                - unique_sideboard: int
                - mainboard_cards: list of (card_name, count) tuples
                - sideboard_cards: list of (card_name, count) tuples
                - estimated_lands: int
        """
        return self.deck_parser.analyze_deck(deck_content)

    # ============= Deck Averaging and Aggregation =============

    def add_deck_to_buffer(self, buffer: dict[str, float], deck_text: str) -> dict[str, float]:
        """
        Add a deck to an averaging buffer.

        Args:
            buffer: Existing buffer of card totals
            deck_text: Deck list to add

        Returns:
            Updated buffer
        """
        return self.deck_averager.add_deck_to_buffer(buffer, deck_text)

    def render_average_deck(self, buffer: dict[str, float], deck_count: int) -> str:
        """
        Render an average deck from a buffer.

        Args:
            buffer: Dictionary of card names to total counts
            deck_count: Number of decks averaged

        Returns:
            Deck list as text with average card counts
        """
        return self.deck_averager.render_average_deck(buffer, deck_count)

    def build_daily_average(
        self, archetype: dict[str, Any], max_decks: int = 10, source_filter: str | None = None
    ) -> tuple[str, int]:
        """
        Build an average deck from recent tournament results.

        Args:
            archetype: Archetype dictionary with 'url' key
            max_decks: Maximum number of decks to average
            source_filter: Optional source filter ('mtggoldfish', 'mtgo', or 'both')

        Returns:
            Tuple of (averaged_deck_text, decks_processed)
        """
        try:
            return self.deck_averager.build_daily_average(
                archetype,
                metagame_repo=self.metagame_repo,
                max_decks=max_decks,
                source_filter=source_filter,
            )

        except Exception as exc:
            logger.error(f"Failed to build daily average: {exc}")
            return "", 0

    # ============= Deck Validation =============

    def validate_deck_format(self, deck_content: str, format_name: str) -> dict[str, Any]:
        """
        Validate a deck against format rules.

        Args:
            deck_content: Deck list as text
            format_name: Format to validate against (e.g., "Modern", "Standard")

        Returns:
            Dictionary with validation results:
                - valid: bool
                - errors: list of error messages
                - warnings: list of warning messages
        """
        analysis = self.analyze_deck(deck_content)
        errors = []
        warnings = []

        # Check mainboard size
        mainboard_count = analysis["mainboard_count"]
        if mainboard_count < 60:
            errors.append(f"Mainboard has {mainboard_count} cards (minimum 60)")
        elif mainboard_count > 60:
            warnings.append(f"Mainboard has {mainboard_count} cards (more than minimum 60)")

        # Check sideboard size
        sideboard_count = analysis["sideboard_count"]
        if sideboard_count > 15:
            errors.append(f"Sideboard has {sideboard_count} cards (maximum 15)")

        # Format-specific validations could be added here
        # For example, checking banned cards, card limits, etc.

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "analysis": analysis,
        }

    def is_valid_deck_size(self, deck_content: str) -> bool:
        """
        Quick check if deck has valid size (60+ mainboard, 0-15 sideboard).

        Args:
            deck_content: Deck list as text

        Returns:
            True if valid size, False otherwise
        """
        analysis = self.analyze_deck(deck_content)
        return analysis["mainboard_count"] >= 60 and analysis["sideboard_count"] <= 15

    # ============= Deck Building Helpers =============

    def build_deck_text_from_zones(self, zone_cards: dict[str, list[dict[str, Any]]]) -> str:
        """
        Build deck text from zone_cards dictionary (used in deck selector UI).

        Args:
            zone_cards: Dictionary with 'main' and 'side' keys mapping to card lists
                       Each card is a dict with 'name' and 'qty' keys

        Returns:
            Formatted deck list text
        """
        if not zone_cards.get("main") and not zone_cards.get("side"):
            return ""
        lines: list[str] = []
        for entry in zone_cards.get("main", []):
            lines.append(f"{entry['qty']} {entry['name']}")
        if zone_cards.get("side"):
            lines.append("")
            lines.append("Sideboard")
            for entry in zone_cards["side"]:
                lines.append(f"{entry['qty']} {entry['name']}")
        return "\n".join(lines).strip()

    def build_deck_text(self, zones: dict[str, list[dict[str, Any]]]) -> str:
        """
        Build deck text from zone dictionaries.

        Args:
            zones: Dictionary mapping zone names to card lists
                   Each card is a dict with 'name' and 'count' keys

        Returns:
            Formatted deck list text
        """
        lines = []

        # Add mainboard cards
        for zone in ["Maindeck", "Deck", "Main"]:
            if zone in zones:
                for card in zones[zone]:
                    count = card.get("count", 1)
                    name = card.get("name", "")
                    if name:
                        lines.append(f"{count} {name}")
                break  # Only process first matching zone

        # Add sideboard section
        sideboard_found = False
        for zone in ["Sideboard", "Side"]:
            if zone in zones and zones[zone]:
                if not sideboard_found:
                    lines.append("")  # Blank line before sideboard
                    sideboard_found = True
                for card in zones[zone]:
                    count = card.get("count", 1)
                    name = card.get("name", "")
                    if name:
                        lines.append(f"{count} {name}")
                break  # Only process first matching zone

        return "\n".join(lines)

    # ============= Zone Management =============

    def handle_zone_change(self, zone_cards: dict[str, list[dict[str, Any]]]) -> ZoneUpdateResult:
        """
        Handle changes to zone cards (mainboard/sideboard).

        Args:
            zone_cards: Dictionary with 'main' and 'side' keys mapping to card lists

        Returns:
            ZoneUpdateResult with updated deck text and loaded state
        """
        deck_text = self.build_deck_text_from_zones(zone_cards)
        self.deck_repo.set_current_deck_text(deck_text)
        has_loaded_deck = bool(zone_cards.get("main") or zone_cards.get("side"))
        return ZoneUpdateResult(deck_text=deck_text, has_loaded_deck=has_loaded_deck)

    # ============= Daily Average Building =============

    def filter_today_decks(
        self, decks: list[dict[str, Any]], today: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Filter decks to only those from today.

        Args:
            decks: List of deck dictionaries
            today: Date string (YYYY-MM-DD format), defaults to today

        Returns:
            Filtered list of decks from today
        """
        return self.deck_averager.filter_today_decks(decks, today=today)

    def build_average_text(
        self,
        todays_decks: list[dict[str, Any]],
        download_deck: Callable[[str], None],
        read_deck_file: Callable[[], str],
    ) -> str:
        """
        Build average deck text from a list of decks.

        Args:
            todays_decks: List of deck dictionaries to average
            download_deck: Function to download a deck by number
            read_deck_file: Function to read the current deck file
            progress_callback: Optional callback for progress updates (current, total)

        Returns:
            Averaged deck text
        """
        return self.deck_averager.build_average_text(
            todays_decks,
            download_deck,
            read_deck_file,
            self.deck_repo,
        )


# Global instance for backward compatibility
_default_service = None


def get_deck_service() -> DeckService:
    """Get the default deck service instance."""
    global _default_service
    if _default_service is None:
        _default_service = DeckService()
    return _default_service


def reset_deck_service() -> None:
    """
    Reset the global deck service instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_service
    _default_service = None


__all__ = [
    "DeckService",
    "ZoneUpdateResult",
    "get_deck_service",
    "reset_deck_service",
]
