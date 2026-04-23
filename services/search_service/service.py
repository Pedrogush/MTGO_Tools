"""SearchService composed from responsibility-specific mixins."""

from __future__ import annotations

from repositories.card_repository import CardRepository, get_card_repository
from services.format_card_pool_service import FormatCardPoolService, get_format_card_pool_service
from services.search_service.basic_search import BasicSearchMixin
from services.search_service.builder_search import BuilderSearchMixin
from services.search_service.deck_search import DeckSearchMixin
from services.search_service.filtering import FilteringMixin


class SearchService(
    BasicSearchMixin,
    FilteringMixin,
    BuilderSearchMixin,
    DeckSearchMixin,
):
    """Service for card search and filtering logic."""

    def __init__(
        self,
        card_repository: CardRepository | None = None,
        format_card_pool_service: FormatCardPoolService | None = None,
    ):
        self.card_repo = card_repository or get_card_repository()
        self.format_card_pool_service = format_card_pool_service or get_format_card_pool_service()
