"""Deck capability analysis: what a decklist could do on each turn.

See :mod:`services.deck_patterns_service.service` for the pipeline. Nothing in
this package imports wx, so the whole analysis is unit-testable directly.
"""

from __future__ import annotations

from services.deck_patterns_service.service import (
    DEFAULT_MAX_COMBINATIONS,
    DEFAULT_MAX_TURN,
    CombinationResult,
    DeckPatternsService,
    PatternsOptions,
    PatternsResult,
    TurnResult,
    get_deck_patterns_service,
    reset_deck_patterns_service,
)

__all__ = [
    "DEFAULT_MAX_COMBINATIONS",
    "DEFAULT_MAX_TURN",
    "CombinationResult",
    "DeckPatternsService",
    "PatternsOptions",
    "PatternsResult",
    "TurnResult",
    "get_deck_patterns_service",
    "reset_deck_patterns_service",
]
