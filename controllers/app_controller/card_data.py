"""Card-data preload handling for :class:`AppController`."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from utils.card_data import CardDataManager

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto

    _Base = AppControllerProto
else:
    _Base = object


class CardDataMixin(_Base):
    """Trigger background card-index loading and keep the repository flags in sync."""

    def ensure_card_data_loaded(
        self,
        on_success: Callable[[CardDataManager], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[..., None],
    ) -> None:
        if self.card_repo.is_card_data_loaded() or self.card_repo.is_card_data_loading():
            return

        self.card_repo.set_card_data_loading(True)
        on_status("app.status.card_db_loading")

        def worker():
            return self.card_repo.ensure_card_data_loaded()

        def success_handler(manager: CardDataManager):
            self.card_repo.set_card_manager(manager)
            self.card_repo.set_card_data_loading(False)
            self.card_repo.set_card_data_ready(True)
            on_status("app.status.card_db_loaded")
            on_success(manager)

        def error_handler(error: Exception):
            self.card_repo.set_card_data_loading(False)
            logger.error(f"Failed to load card data: {error}")
            on_status("app.status.card_db_failed", error=error)
            on_error(error)

        self._worker.submit(worker, on_success=success_handler, on_error=error_handler)
