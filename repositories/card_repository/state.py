"""Card-data loading/ready state for the UI layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import repositories.card_repository as _pkg

if TYPE_CHECKING:
    from repositories.card_repository.protocol import CardRepositoryProto
    from services.card_data_service import CardDataManager

    _Base = CardRepositoryProto
else:
    _Base = object


class StateMixin(_Base):
    """In-memory loading/ready flags and ``CardDataManager`` accessors."""

    def is_card_data_loading(self) -> bool:
        return self._card_data_loading

    def set_card_data_loading(self, loading: bool) -> None:
        self._card_data_loading = loading

    def is_card_data_ready(self) -> bool:
        return self._card_data_ready

    def set_card_data_ready(self, ready: bool) -> None:
        self._card_data_ready = ready

    def get_card_manager(self) -> CardDataManager | None:
        return self._card_data_manager

    def set_card_manager(self, manager: CardDataManager | None) -> None:
        self._card_data_manager = manager
        if manager is not None:
            self._card_data_ready = True

    def ensure_card_data_loaded(self, force: bool = False) -> CardDataManager:
        if not force and self._card_data_manager is not None and self._card_data_manager.is_loaded:
            return self._card_data_manager

        # Resolved lazily through the package namespace so the
        # ``repositories → services`` import only happens on first use.
        manager = _pkg.load_card_manager()
        self.set_card_manager(manager)
        return manager
