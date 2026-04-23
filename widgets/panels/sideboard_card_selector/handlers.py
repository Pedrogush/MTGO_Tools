"""Button callbacks and display updates for the sideboard card selector panel."""

from __future__ import annotations

import wx


class SideboardCardSelectorHandlersMixin:
    """Increment/decrement callbacks and display refreshers for :class:`SideboardCardSelector`."""

    selected_cards: dict[str, int]
    card_widgets: dict[str, tuple[wx.StaticText, wx.Panel]]
    count_label: wx.StaticText

    def _increment(self, card_name: str, max_qty: int) -> None:
        current = self.selected_cards.get(card_name, 0)
        if current < max_qty:
            self.selected_cards[card_name] = current + 1
            self._update_display(card_name)
            self._update_count()

    def _decrement(self, card_name: str) -> None:
        current = self.selected_cards.get(card_name, 0)
        if current > 0:
            new_qty = current - 1
            if new_qty == 0:
                self.selected_cards.pop(card_name, None)
            else:
                self.selected_cards[card_name] = new_qty
            self._update_display(card_name)
            self._update_count()

    def _set_zero(self, card_name: str) -> None:
        self.selected_cards.pop(card_name, None)
        self._update_display(card_name)
        self._update_count()

    def _set_max(self, card_name: str, max_qty: int) -> None:
        self.selected_cards[card_name] = max_qty
        self._update_display(card_name)
        self._update_count()

    def _update_display(self, card_name: str) -> None:
        qty = self.selected_cards.get(card_name, 0)
        qty_label, _ = self.card_widgets[card_name]
        qty_label.SetLabel(f"{qty:3d}")

    def _update_count(self) -> None:
        total = sum(self.selected_cards.values())
        self.count_label.SetLabel(self._t("guide.selector.cards_selected", count=total))

    def set_selected_cards(self, cards: dict[str, int]) -> None:
        self.selected_cards = cards.copy()

        for card_name in self.card_widgets:
            self._update_display(card_name)

        self._update_count()
