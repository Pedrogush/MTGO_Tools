"""Dataclass returned by :class:`FormatCardPoolRepository` reads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatCardPoolSummary:
    """Metadata for one locally cached format card pool."""

    format_name: str
    generated_at: str
    source: str
    total_decks_analyzed: int
    decks_failed: int
    unique_cards: int


@dataclass(frozen=True)
class FormatCardPoolCardTotal:
    """Aggregated copy-total entry for a card in one format."""

    card_name: str
    copies_played: int
