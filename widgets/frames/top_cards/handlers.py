"""Event and data-refresh callbacks for the Top Cards viewer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from services.format_card_pool_service import FormatCardPoolService
    from services.radar_service import RadarService
    from services.radar_service.card_stats import CardUsageStats

FORMATS_COLUMN_INDEX = 11

# Visible columns are 1..11; column 0 is a hidden 0-width spacer.
_HEADER_TOOLTIP_KEYS: dict[int, str] = {
    1: "top_cards.tooltip.rank",
    2: "top_cards.tooltip.card",
    3: "top_cards.tooltip.copies",
    4: "top_cards.tooltip.mb_decks",
    5: "top_cards.tooltip.mb_avg",
    6: "top_cards.tooltip.mb_avg_karsten",
    7: "top_cards.tooltip.sb_decks",
    8: "top_cards.tooltip.sb_avg",
    9: "top_cards.tooltip.sb_avg_karsten",
    10: "top_cards.tooltip.archetypes",
    11: "top_cards.tooltip.formats",
}


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
            # Column 0 is a 0-width spacer so the visible columns can be centered.
            row = self.card_list.InsertItem(self.card_list.GetItemCount(), "")
            self.card_list.SetItem(row, 1, str(index))
            self.card_list.SetItem(row, 2, entry.card_name)
            self.card_list.SetItem(row, 3, str(entry.copies_played))

            stats = usage_by_name.get(
                entry.card_name,
                self.controller.CardUsageStats(
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
            self.card_list.SetItem(row, 4, str(stats.mainboard_decks_present))
            self.card_list.SetItem(row, 5, _format_avg(stats.mainboard_avg_arithmetic))
            self.card_list.SetItem(row, 6, _format_avg(stats.mainboard_avg_karsten))
            self.card_list.SetItem(row, 7, str(stats.sideboard_decks_present))
            self.card_list.SetItem(row, 8, _format_avg(stats.sideboard_avg_arithmetic))
            self.card_list.SetItem(row, 9, _format_avg(stats.sideboard_avg_karsten))
            self.card_list.SetItem(row, 10, _format_archetypes(stats))
            self.card_list.SetItem(
                row, 11, _format_formats(legality_by_name.get(entry.card_name, []))
            )

        self._autosize_formats_column()

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()

    def _autosize_formats_column(self) -> None:
        """Size the Formats column to whichever of (data, header) is wider.

        Avoids the trailing-ellipsis state when a card is legal in many
        formats, since the comma-joined list grows wider than the default 160px.
        """
        col = FORMATS_COLUMN_INDEX
        self.card_list.SetColumnWidth(col, wx.LIST_AUTOSIZE)
        data_width = self.card_list.GetColumnWidth(col)
        self.card_list.SetColumnWidth(col, wx.LIST_AUTOSIZE_USEHEADER)
        header_width = self.card_list.GetColumnWidth(col)
        self.card_list.SetColumnWidth(col, max(data_width, header_width))

    def _bind_header_tooltips(self) -> None:
        self.card_list.Bind(wx.EVT_MOTION, self._on_list_mouse_motion)
        self.card_list.Bind(wx.EVT_LEAVE_WINDOW, self._on_list_mouse_leave)

    def _on_list_mouse_motion(self, event: wx.MouseEvent) -> None:
        col = self._column_at_x(event.GetPosition().x)
        if col is None or col not in _HEADER_TOOLTIP_KEYS:
            self._set_list_tooltip("")
        else:
            self._set_list_tooltip(self._t(_HEADER_TOOLTIP_KEYS[col]))
        event.Skip()

    def _on_list_mouse_leave(self, event: wx.MouseEvent) -> None:
        self._set_list_tooltip("")
        event.Skip()

    def _set_list_tooltip(self, text: str) -> None:
        current_tip = self.card_list.GetToolTip()
        current_text = current_tip.GetTip() if current_tip else ""
        if text == current_text:
            return
        self.card_list.SetToolTip(text)

    def _column_at_x(self, x: int) -> int | None:
        cumulative = 0
        for i in range(self.card_list.GetColumnCount()):
            width = self.card_list.GetColumnWidth(i)
            if width <= 0:
                continue
            cumulative += width
            if x < cumulative:
                return i
        return None
