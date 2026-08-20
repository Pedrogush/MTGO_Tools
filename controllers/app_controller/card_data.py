"""Card-data preload handling for :class:`AppController`."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto
    from repositories.card_repository import CardDataManager

    _Base = AppControllerProto
else:
    _Base = object


class CardDataMixin(_Base):
    """Trigger background card-index loading and keep the repository flags in sync.

    Every caller here registers ``on_success`` because it has UI state that only
    the :class:`CardDataManager` can fill in -- the deck stats charts, the card
    inspector, a pending builder search. The load itself happens at most once,
    so the three states this has to distinguish are *already loaded* (answer
    now), *load in flight* (answer when it lands) and *not started* (start it,
    then answer).

    Until this was fixed the first two states shared one ``return`` and the
    caller's callbacks were dropped on the floor. That is a silent failure by
    construction: the caller has no way to tell "your callback will never run"
    from "the data is on its way", so it waits forever. It bit the deck stats
    panel, whose only route to a card manager is the ``on_success`` the app
    frame registers -- :meth:`LifecycleMixin.initialize_app` step 5 pre-loads
    the index with ``on_success=lambda _: None``, so on any start where that
    pre-load won the race the panel kept ``card_manager = None`` for the life of
    the process and every metadata-derived chart rendered empty.
    """

    def ensure_card_data_loaded(
        self,
        on_success: Callable[[CardDataManager], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[..., None],
    ) -> None:
        if self.card_service.is_card_data_loaded():
            manager = self.card_service.get_card_manager()
            if manager is not None:
                on_success(manager)
                return

        waiters = self._card_data_waiters
        waiters.append((on_success, on_error))
        if self.card_service.is_card_data_loading():
            # A load is already running; it will drain the queue when it lands.
            return

        self.card_service.set_card_data_loading(True)
        on_status("app.status.card_db_loading")

        def worker():
            return self.card_service.ensure_card_data_loaded()

        def success_handler(manager: CardDataManager):
            self.card_service.set_card_manager(manager)
            self.card_service.set_card_data_loading(False)
            self.card_service.set_card_data_ready(True)
            on_status("app.status.card_db_loaded")
            for callback, _on_error in self._drain_card_data_waiters():
                callback(manager)

        def error_handler(error: Exception):
            self.card_service.set_card_data_loading(False)
            logger.error(f"Failed to load card data: {error}")
            on_status("app.status.card_db_failed", error=error)
            for _callback, callback_on_error in self._drain_card_data_waiters():
                callback_on_error(error)

        self._worker.submit(worker, on_success=success_handler, on_error=error_handler)

    def _drain_card_data_waiters(
        self,
    ) -> list[tuple[Callable[[CardDataManager], None], Callable[[Exception], None]]]:
        """Take the queued callbacks, leaving the queue empty.

        Taken rather than iterated in place so a callback that itself calls
        :meth:`ensure_card_data_loaded` (the data is loaded by then, so it is
        answered inline) cannot see its own entry twice.
        """
        waiters = self._card_data_waiters
        drained = list(waiters)
        waiters.clear()
        return drained
