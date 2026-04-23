"""Backward-compat re-export for the legacy ``services.deck_averager`` module.

The :class:`DeckAverager` implementation now lives in
``services.deck_service.averager`` as part of the deck-service package refactor.
"""

from __future__ import annotations

from services.deck_service.averager import (
    KARSTEN_MAIN_SIZE,
    KARSTEN_SIDE_SIZE,
    DeckAverager,
)

__all__ = ["DeckAverager", "KARSTEN_MAIN_SIZE", "KARSTEN_SIDE_SIZE"]
