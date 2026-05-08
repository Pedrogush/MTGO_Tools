"""Event and data-refresh callbacks for the Top Cards viewer."""

from __future__ import annotations

import wx

from services.format_card_pool_service import FormatCardPoolService
from services.radar_service import RadarService
from services.radar_service.card_stats import CardUsageStats


def _format_avg(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _format_archetypes(stats: CardUsageStats) -> str:
    if not stats.mainboard_archetypes and not stats.sideboard_archetypes:
        return "—"
    return f"{stats.mainboard_archetypes} / {stats.sideboard_archetypes}"


def _format_formats(formats: list[str]) -> str:
    if not formats:
        return "—"
    return ", ".join(fmt.title() for fmt in formats)


class TopCardsHandlersMixin:
    """Callbacks for :class:`TopCardsFrame`."""

    # Attributes supplied by :class:`TopCardsFrame`.
    current_format: str
    _service: FormatCardPoolService
    _radar_service: RadarService
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

        card_names = [entry.card_name for entry in top_cards]
        usage_by_name = self._radar_service.get_card_usage_stats(format_name, card_names)
        legality_by_name = self._radar_service.get_effective_legalities(card_names)

        for index, entry in enumerate(top_cards, start=1):
            row = self.card_list.InsertItem(self.card_list.GetItemCount(), str(index))
            self.card_list.SetItem(row, 1, entry.card_name)
            self.card_list.SetItem(row, 2, str(entry.copies_played))

            stats = usage_by_name.get(
                entry.card_name,
                CardUsageStats(
                    card_name=entry.card_name,
                    format_name=format_name.lower(),
                    total_decks=0,
                    mainboard_archetypes=0,
                    sideboard_archetypes=0,
                    mainboard_copies=0,
                    sideboard_copies=0,
                    mainboard_decks_present=0,
                    sideboard_decks_present=0,
                ),
            )
            self.card_list.SetItem(row, 3, str(stats.mainboard_decks_present))
            self.card_list.SetItem(row, 4, _format_avg(stats.mainboard_avg_arithmetic))
            self.card_list.SetItem(row, 5, _format_avg(stats.mainboard_avg_karsten))
            self.card_list.SetItem(row, 6, str(stats.sideboard_decks_present))
            self.card_list.SetItem(row, 7, _format_avg(stats.sideboard_avg_arithmetic))
            self.card_list.SetItem(row, 8, _format_avg(stats.sideboard_avg_karsten))
            self.card_list.SetItem(row, 9, _format_archetypes(stats))
            self.card_list.SetItem(
                row, 10, _format_formats(legality_by_name.get(entry.card_name, []))
            )

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()
