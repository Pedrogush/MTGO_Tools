"""Dataclasses returned by :class:`RadarRepository` reads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredRadarCard:
    """One persisted radar card row."""

    card_name: str
    appearances: int
    total_copies: int
    max_copies: int
    avg_copies: float
    inclusion_rate: float
    expected_copies: float
    copy_distribution: dict[int, int]


@dataclass(frozen=True)
class StoredRadar:
    """Full persisted radar snapshot."""

    archetype_name: str
    archetype_href: str
    format_name: str
    generated_at: str
    source: str
    total_decks_analyzed: int
    decks_failed: int
    mainboard_cards: list[StoredRadarCard]
    sideboard_cards: list[StoredRadarCard]
