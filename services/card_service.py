"""Thin service wrapping :class:`CardRepository` state for controller/widget use.

The :class:`CardRepository` exposes loading/ready flags plus a
``CardDataManager`` handle that the UI background-preloads at startup.
:class:`AppController` previously held a direct ``card_repo`` handle to drive
that lifecycle; this service is the canonical service-layer entry point so the
controller no longer imports :mod:`repositories.card_repository` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from repositories.card_repository import CardRepository, get_card_repository

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager


class CardService:
    """Service exposing card-data lifecycle operations to controllers/widgets."""

    def __init__(self, card_repository: CardRepository | None = None) -> None:
        self.card_repo: CardRepository = card_repository or get_card_repository()

    def is_card_data_loaded(self) -> bool:
        """Return ``True`` once the card index has been fully populated."""
        return self.card_repo.is_card_data_loaded()

    def is_card_data_loading(self) -> bool:
        """Return ``True`` while a background preload is in progress."""
        return self.card_repo.is_card_data_loading()

    def set_card_data_loading(self, loading: bool) -> None:
        """Mark the card-data preload as in-flight or idle."""
        self.card_repo.set_card_data_loading(loading)

    def set_card_data_ready(self, ready: bool) -> None:
        """Mark the card data as ready (or not yet) for widget consumption."""
        self.card_repo.set_card_data_ready(ready)

    def set_card_manager(self, manager: CardDataManager | None) -> None:
        """Hand the freshly-loaded :class:`CardDataManager` to the repository."""
        self.card_repo.set_card_manager(manager)

    def ensure_card_data_loaded(self, force: bool = False) -> CardDataManager:
        """Force-load (or return the existing) :class:`CardDataManager`."""
        return self.card_repo.ensure_card_data_loaded(force=force)


_default_service: CardService | None = None


def get_card_service() -> CardService:
    """Return the shared :class:`CardService` instance."""
    global _default_service
    if _default_service is None:
        _default_service = CardService()
    return _default_service


def reset_card_service() -> None:
    """Reset the global card service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "CardService",
    "get_card_service",
    "reset_card_service",
]
