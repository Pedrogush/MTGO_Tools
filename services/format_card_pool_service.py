"""Business logic for locally cached format card-pool data."""

from __future__ import annotations

from repositories.format_card_pool_repository import (
    FormatCardPoolCardTotal,
    FormatCardPoolRepository,
    FormatCardPoolSummary,
    get_format_card_pool_repository,
)


class FormatCardPoolService:
    """Service wrapper around the format card-pool repository."""

    def __init__(self, repository: FormatCardPoolRepository | None = None) -> None:
        self.repository = repository or get_format_card_pool_repository()

    def has_format_pool(self, format_name: str) -> bool:
        return self.repository.has_format_pool(format_name)

    def get_card_pool_names(self, format_name: str) -> set[str]:
        return self.repository.get_card_names(format_name)

    def get_top_cards(self, format_name: str, limit: int = 100) -> list[FormatCardPoolCardTotal]:
        return self.repository.get_top_cards(format_name, limit=limit)

    def get_summary(self, format_name: str) -> FormatCardPoolSummary | None:
        return self.repository.get_summary(format_name)


_default_service: FormatCardPoolService | None = None


def get_format_card_pool_service() -> FormatCardPoolService:
    global _default_service
    if _default_service is None:
        _default_service = FormatCardPoolService()
    return _default_service


def reset_format_card_pool_service() -> None:
    global _default_service
    _default_service = None
