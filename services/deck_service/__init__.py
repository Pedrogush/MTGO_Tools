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
    "ZoneUpdateResult",
    "get_deck_service",
    "reset_deck_service",
]
