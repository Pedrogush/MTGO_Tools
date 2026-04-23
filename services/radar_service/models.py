"""Dataclasses produced by :class:`RadarService`."""

from __future__ import annotations

from dataclasses import dataclass


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
