"""Click handlers for the deck action button panel."""

from __future__ import annotations

from collections.abc import Callable

import wx


class DeckActionButtonsHandlersMixin:
    """Click dispatchers for :class:`DeckActionButtons`."""

    on_copy: Callable[[], None] | None
    on_save: Callable[[], None] | None
    on_daily_average: Callable[[], None] | None
    on_load: Callable[[], None] | None

    def _on_daily_average_clicked(self, _event: wx.Event) -> None:
        if self.on_daily_average:
            self.on_daily_average()

    def _on_copy_clicked(self, _event: wx.Event) -> None:
        if self.on_copy:
            self.on_copy()

    def _on_load_clicked(self, _event: wx.Event) -> None:
        if self.on_load:
            self.on_load()

    def _on_save_clicked(self, _event: wx.Event) -> None:
        if self.on_save:
            self.on_save()
