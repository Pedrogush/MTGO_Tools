"""
Repositories package - Data access layer.

This package contains repository classes that handle all data persistence
and retrieval operations, isolating the UI and business logic from data access details.
"""

from repositories.card_repository import CardRepository, get_card_repository
from repositories.deck_repository import DeckRepository, get_deck_repository
from repositories.deck_text_cache import DeckTextCache, get_deck_cache
from repositories.format_card_pool_repository import (
    FormatCardPoolRepository,
    get_format_card_pool_repository,
)
from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from repositories.radar_repository import RadarRepository, get_radar_repository

__all__ = [
    "CardRepository",
    "DeckRepository",
    "DeckTextCache",
    "FormatCardPoolRepository",
    "MetagameRepository",
    "RadarRepository",
    "get_card_repository",
    "get_deck_cache",
    "get_deck_repository",
    "get_format_card_pool_repository",
    "get_metagame_repository",
    "get_radar_repository",
]
