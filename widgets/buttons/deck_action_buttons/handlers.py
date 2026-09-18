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
    on_save_diff: Callable[[], None] | None
    save_button: wx.Button
    _labels: dict[str, str]

    def _on_daily_average_clicked(self, _event: wx.Event) -> None:
        if self.on_daily_average:
            self.on_daily_average()

    def _on_copy_clicked(self, _event: wx.Event) -> None:
        if self.on_copy:
            self.on_copy()

    def _on_load_clicked(self, _event: wx.Event) -> None:
        if self.on_load:
            self.on_load()

    def save_menu_entries(self) -> list[tuple[str, Callable[[], None] | None]]:
        """The Save dropdown's ``(label, callback)`` pairs, in menu order (#1044).

        Exposed rather than built inside the click handler so a test can read the
        menu without entering ``PopupMenu``'s nested modal loop.
        """
        return [
            (self._labels.get("save_deck", "Save Deck"), self.on_save),
            (self._labels.get("save_diff", "Save Collection Diff"), self.on_save_diff),
        ]

    def _on_save_clicked(self, _event: wx.Event) -> None:
        """Open the Save dropdown. Save is a menu, not an action, since #1044."""
        menu = wx.Menu()
        for label, callback in self.save_menu_entries():
            item = menu.Append(wx.ID_ANY, label)
            item.Enable(callback is not None)
            menu.Bind(wx.EVT_MENU, lambda _evt, cb=callback: cb and cb(), item)
        # PopupMenu runs a nested modal loop: the chosen callback has already run
        # by the time it returns, which is why the menu is destroyed after it.
        self.PopupMenu(menu, self.save_button.GetPosition())
        menu.Destroy()
