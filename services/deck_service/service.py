"""DeckService composed from parser/averager/text-builder mixins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from repositories.deck_repository import DeckRepository, get_deck_repository
from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from services.deck_service.averager import DeckAveragerMixin
from services.deck_service.parser import DeckParserMixin
from services.deck_service.text_builder import DeckTextBuilderMixin
from utils.constants import DEFAULT_MAX_DECKS


@dataclass(frozen=True)
class ZoneUpdateResult:
    """Result of updating deck zones."""

    deck_text: str
    has_loaded_deck: bool


class DeckService(
    DeckParserMixin,
    DeckAveragerMixin,
    DeckTextBuilderMixin,
):
    """Service for deck-related business logic."""

    def __init__(
        self,
        deck_repository: DeckRepository | None = None,
        metagame_repository: MetagameRepository | None = None,
    ):
        self.deck_repo = deck_repository or get_deck_repository()
        self.metagame_repo = metagame_repository or get_metagame_repository()

    # ============= Repository-coupled orchestration =============

    def build_daily_average(
        self,
        archetype: dict[str, Any],
        max_decks: int = DEFAULT_MAX_DECKS,
        source_filter: str | None = None,
    ) -> tuple[str, int]:
        try:
            decks = self.metagame_repo.get_decks_for_archetype(
                archetype, force_refresh=True, source_filter=source_filter
            )

            if not decks:
                logger.warning(f"No decks found for archetype: {archetype.get('name')}")
                return "", 0

            decks_to_process = decks[:max_decks]

            buffer: dict[str, float] = {}
            processed = 0

            for deck in decks_to_process:
                try:
                    deck_content = self.metagame_repo.download_deck_content(
                        deck, source_filter=source_filter
                    )
                    buffer = self.add_deck_to_buffer(buffer, deck_content)
                    processed += 1
                except Exception as exc:
                    logger.warning(f"Failed to download deck {deck.get('name')}: {exc}")
                    continue

            if processed == 0:
                return "", 0

            averaged_deck = self.render_average_deck(buffer, processed)
            return averaged_deck, processed

        except Exception as exc:
            logger.error(f"Failed to build daily average: {exc}")
            return "", 0

    def build_average_text(
        self,
        todays_decks: list[dict[str, Any]],
        download_deck: Callable[[str], None],
        read_deck_file: Callable[[], str],
    ) -> str:
        buffer = self.deck_repo.build_daily_average_deck(
            todays_decks,
            download_deck,
            read_deck_file,
            self.add_deck_to_buffer,
        )
        return self.render_average_deck(buffer, len(todays_decks))
