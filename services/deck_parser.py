"""Backward-compat re-export for the legacy ``services.deck_parser`` module.

The :class:`DeckParser` implementation now lives in
``services.deck_service.parser`` as part of the deck-service package refactor.
"""

from __future__ import annotations

from services.deck_service.parser import DeckEntry, DeckParser

__all__ = ["DeckEntry", "DeckParser"]
