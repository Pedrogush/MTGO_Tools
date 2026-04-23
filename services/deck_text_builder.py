"""Backward-compat re-export for the legacy ``services.deck_text_builder`` module.

The :class:`DeckTextBuilder` implementation now lives in
``services.deck_service.text_builder`` as part of the deck-service package refactor.
"""

from __future__ import annotations

from services.deck_service.text_builder import DeckTextBuilder

__all__ = ["DeckTextBuilder"]
