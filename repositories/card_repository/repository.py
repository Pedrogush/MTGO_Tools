"""CardRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING

import repositories.card_repository as _pkg
from repositories.card_repository.collection import CollectionMixin
from repositories.card_repository.metadata import MetadataMixin
from repositories.card_repository.state import StateMixin

if TYPE_CHECKING:
    from services.card_data_service import CardDataManager


class CardRepository(
    MetadataMixin,
    CollectionMixin,
    StateMixin,
):
    """Repository for card data access operations and card data state management."""

    def __init__(self, card_data_manager: CardDataManager | None = None):
        self._card_data_manager = card_data_manager

        self._card_data_loading: bool = False
        self._card_data_ready: bool = False

    @property
    def card_data_manager(self) -> CardDataManager:
        if self._card_data_manager is None:
            # Resolved lazily through the package namespace so the
            # ``repositories → services`` import only happens on first use.
            self._card_data_manager = _pkg.CardDataManager()
        return self._card_data_manager
