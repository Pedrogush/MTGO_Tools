"""Event and data-refresh callbacks for the Top Cards viewer."""

from __future__ import annotations

import wx

from services.format_card_pool_service import FormatCardPoolService


class TopCardsHandlersMixin:
    """Callbacks for :class:`TopCardsFrame`."""

    # Attributes supplied by :class:`TopCardsFrame`.
    current_format: str
    _service: FormatCardPoolService
    format_choice: wx.Choice
    status_label: wx.StaticText
    card_list: wx.ListCtrl

    def on_format_change(self, _event: wx.CommandEvent) -> None:
        self.current_format = self.format_choice.GetStringSelection().lower()
        self.refresh_data()

    def refresh_data(self) -> None:
        format_name = self.current_format
        summary = self._service.get_summary(format_name)
        top_cards = self._service.get_top_cards(format_name)

        self.card_list.DeleteAllItems()
        if summary is None or not top_cards:
            self.status_label.SetLabel(
                self._t("top_cards.status.no_data", format=format_name.title())
            )
            return

        self.status_label.SetLabel(
            self._t(
                "top_cards.status.loaded",
                decks=summary.total_decks_analyzed,
                unique_cards=summary.unique_cards,
                generated_at=summary.generated_at,
            )
        )
        for index, entry in enumerate(top_cards, start=1):
            row = self.card_list.InsertItem(self.card_list.GetItemCount(), str(index))
            self.card_list.SetItem(row, 1, entry.card_name)
            self.card_list.SetItem(row, 2, str(entry.copies_played))

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()
