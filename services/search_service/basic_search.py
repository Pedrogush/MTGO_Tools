"""Name-based card search and typeahead suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.constants import DEFAULT_SEARCH_LIMIT, DEFAULT_SUGGESTION_LIMIT, MIN_PARTIAL_NAME_LENGTH

if TYPE_CHECKING:
    from services.search_service.protocol import SearchServiceProto

    _Base = SearchServiceProto
else:
    _Base = object


class BasicSearchMixin(_Base):
    """Name search and suggestion lookups against the card repository."""

    def search_cards_by_name(
        self, query: str, limit: int = DEFAULT_SEARCH_LIMIT
    ) -> list[dict[str, Any]]:
        if not query:
            return []

        try:
            if not self.card_repo.is_card_data_loaded():
                logger.warning("Card data not loaded")
                return []

            results = self.card_repo.search_cards(query=query)
            return results[:limit]

        except Exception as exc:
            logger.error(f"Failed to search cards by name: {exc}")
            return []

    def get_card_suggestions(
        self, partial_name: str, limit: int = DEFAULT_SUGGESTION_LIMIT
    ) -> list[str]:
        if len(partial_name) < MIN_PARTIAL_NAME_LENGTH:
            return []

        try:
            results = self.search_cards_by_name(partial_name, limit=limit)
            return [card.get("name", "") for card in results if card.get("name")]
        except Exception as exc:
            logger.warning(f"Failed to get card suggestions: {exc}")
            return []
