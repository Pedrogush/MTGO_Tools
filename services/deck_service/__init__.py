"""Deck Service package - Business logic for deck operations.

Split by responsibility into internal modules:

- ``parser``: deck-text parsing and analysis (:class:`DeckParser`)
- ``averager``: arithmetic and Karsten averaging (:class:`DeckAverager`)
- ``text_builder``: zone → text rendering (:class:`DeckTextBuilder`)
- ``service``: :class:`DeckService` composed from the above
"""

from __future__ import annotations

from services.deck_service.averager import DeckAverager
from services.deck_service.parser import DeckParser
from services.deck_service.printing import (
    ParsedCard,
    decklist_with_full_art_printings,
    decklist_with_newest_printings,
    decklist_with_newest_printings_by,
    decklist_with_oldest_printings,
    decklist_with_printings_after,
    decklist_with_printings_to_agnostic,
    format_decklist_on_load,
    parse_printed_decklist,
)
from services.deck_service.service import DeckService, ZoneUpdateResult
from services.deck_service.text_builder import DeckTextBuilder

# Global instance for backward compatibility
_default_service: DeckService | None = None


def get_deck_service() -> DeckService:
    """Get the default deck service instance."""
    global _default_service
    if _default_service is None:
        _default_service = DeckService()
    return _default_service


def reset_deck_service() -> None:
    """Reset the global deck service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "DeckAverager",
    "DeckParser",
    "DeckService",
    "DeckTextBuilder",
    "ParsedCard",
    "ZoneUpdateResult",
    "decklist_with_full_art_printings",
    "decklist_with_newest_printings",
    "decklist_with_newest_printings_by",
    "decklist_with_oldest_printings",
    "decklist_with_printings_after",
    "decklist_with_printings_to_agnostic",
    "format_decklist_on_load",
    "get_deck_service",
    "parse_printed_decklist",
    "reset_deck_service",
]
