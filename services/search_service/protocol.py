"""Shared ``self`` contract that the :class:`SearchService` mixins assume."""

from __future__ import annotations

from typing import Any, Protocol

from repositories.card_repository import CardRepository
from services.format_card_pool_service import FormatCardPoolService


class SearchServiceProto(Protocol):
    """Cross-mixin ``self`` surface for ``SearchService``."""

    card_repo: CardRepository
    format_card_pool_service: FormatCardPoolService

    def search_cards_by_name(self, query: str, limit: int = ...) -> list[dict[str, Any]]: ...
    def _matches_color_filter(self, card: dict[str, Any], colors: list[str], mode: str) -> bool: ...
    def _matches_type_filter(self, card: dict[str, Any], types: list[str]) -> bool: ...
    def _matches_mana_cost_filter(self, card: dict[str, Any], query: str, mode: str) -> bool: ...
    def _matches_mana_value_filter(
        self, card: dict[str, Any], target: float, comparator: str
    ) -> bool: ...
    def _matches_text_filter(self, card: dict[str, Any], query: str, mode: str = ...) -> bool: ...
    def _get_card_colors_for_filter(self, card: dict[str, Any]) -> list[str]: ...
