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
        """Return True when a local snapshot exists for *format_name*."""
        return self.repository.has_format_pool(format_name)

    def get_card_pool_names(self, format_name: str) -> set[str]:
        """Return the local card pool for *format_name*."""
        return self.repository.get_card_names(format_name)

    def get_top_cards(self, format_name: str, limit: int = 100) -> list[FormatCardPoolCardTotal]:
        """Return the highest copy-total cards for *format_name*."""
        return self.repository.get_top_cards(format_name, limit=limit)

    def get_summary(self, format_name: str) -> FormatCardPoolSummary | None:
        """Return local metadata for *format_name*."""
        return self.repository.get_summary(format_name)


_default_service: FormatCardPoolService | None = None


def get_format_card_pool_service() -> FormatCardPoolService:
    """Return the shared format card-pool service instance."""
    global _default_service
    if _default_service is None:
        _default_service = FormatCardPoolService()
    return _default_service


def reset_format_card_pool_service() -> None:
    """Reset the shared format card-pool service instance."""
    global _default_service
    _default_service = None
