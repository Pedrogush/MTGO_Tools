"""DeckService assembled from parser/averager/text-builder modules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from repositories.deck_repository import DeckRepository, get_deck_repository
from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from services.deck_service.averager import DeckAverager
from services.deck_service.parser import DeckParser
from services.deck_service.text_builder import DeckTextBuilder
from utils.constants import DEFAULT_MAX_DECKS


@dataclass(frozen=True)
class ZoneUpdateResult:
    """Result of updating deck zones."""

    deck_text: str
    has_loaded_deck: bool


class DeckService:
    """Service for deck-related business logic."""

    def __init__(
        self,
        deck_repository: DeckRepository | None = None,
        metagame_repository: MetagameRepository | None = None,
        deck_parser: DeckParser | None = None,
        deck_averager: DeckAverager | None = None,
        deck_text_builder: DeckTextBuilder | None = None,
    ):
        self.deck_repo = deck_repository or get_deck_repository()
        self.metagame_repo = metagame_repository or get_metagame_repository()
        self.deck_parser = deck_parser or DeckParser()
        self.deck_averager = deck_averager or DeckAverager(self.deck_parser)
        self.deck_text_builder = deck_text_builder or DeckTextBuilder()

    # ============= Deck Parsing and Analysis =============

    def deck_to_dictionary(self, deck_text: str) -> dict[str, float]:
        # Sideboard cards are prefixed with "Sideboard " in the returned dict.
        return self.deck_parser.deck_to_dictionary(deck_text)

    def analyze_deck(self, deck_content: str) -> dict[str, Any]:
        return self.deck_parser.analyze_deck(deck_content)

    # ============= Deck Averaging and Aggregation =============

    def add_deck_to_buffer(self, buffer: dict[str, float], deck_text: str) -> dict[str, float]:
        return self.deck_averager.add_deck_to_buffer(buffer, deck_text)

    def add_deck_to_karsten_buffer(self, buffer: dict[str, int], deck_text: str) -> dict[str, int]:
        return self.deck_averager.add_deck_to_karsten_buffer(buffer, deck_text)

    def render_average_deck(self, buffer: dict[str, float], deck_count: int) -> str:
        return self.deck_averager.render_average_deck(buffer, deck_count)

    def render_karsten_deck(self, buffer: dict[str, int]) -> str:
        return self.deck_averager.render_karsten_deck(buffer)

    def build_daily_average(
        self,
        archetype: dict[str, Any],
        max_decks: int = DEFAULT_MAX_DECKS,
        source_filter: str | None = None,
    ) -> tuple[str, int]:
        try:
            return self.deck_averager.build_daily_average(
                archetype,
                metagame_repo=self.metagame_repo,
                max_decks=max_decks,
                source_filter=source_filter,
            )

        except Exception as exc:
            logger.error(f"Failed to build daily average: {exc}")
            return "", 0

    # ============= Deck Building Helpers =============

    def build_deck_text_from_zones(self, zone_cards: dict[str, list[dict[str, Any]]]) -> str:
        return self.deck_text_builder.build_deck_text_from_zones(zone_cards)

    def build_deck_text(self, zones: dict[str, list[dict[str, Any]]]) -> str:
        return self.deck_text_builder.build_deck_text(zones)

    # ============= Daily Average Building =============

    def filter_today_decks(
        self, decks: list[dict[str, Any]], today: str | None = None
    ) -> list[dict[str, Any]]:
        return self.deck_averager.filter_today_decks(decks, today=today)

    def build_average_text(
        self,
        todays_decks: list[dict[str, Any]],
        download_deck: Callable[[str], None],
        read_deck_file: Callable[[], str],
    ) -> str:
        return self.deck_averager.build_average_text(
            todays_decks,
            download_deck,
            read_deck_file,
            self.deck_repo,
        )
