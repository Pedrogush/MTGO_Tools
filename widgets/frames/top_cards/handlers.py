"""Event and data-refresh callbacks for the Top Cards viewer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from widgets.grids import DataGrid

if TYPE_CHECKING:
    from services.format_card_pool_service import FormatCardPoolService
    from services.radar_service import RadarService
    from services.radar_service.card_stats import CardUsageStats

# Column indices are now 0-based and dense: the old table reserved index 0 for a
# 0-width spacer because wx.ListCtrl on MSW always left-aligns column 0 whatever
# format you ask for. The own-drawn grid has no such rule.
_HEADER_TOOLTIP_KEYS: dict[int, str] = {
    0: "top_cards.tooltip.rank",
    1: "top_cards.tooltip.card",
    2: "top_cards.tooltip.copies",
    3: "top_cards.tooltip.mb_decks",
    4: "top_cards.tooltip.mb_avg",
    5: "top_cards.tooltip.mb_avg_karsten",
    6: "top_cards.tooltip.sb_decks",
    7: "top_cards.tooltip.sb_avg",
    8: "top_cards.tooltip.sb_avg_karsten",
    9: "top_cards.tooltip.archetypes",
    10: "top_cards.tooltip.formats",
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
    card_list: DataGrid

    def on_format_change(self, _event: wx.CommandEvent) -> None:
        self.current_format = self.format_choice.GetStringSelection().lower()
        self.refresh_data()

    def refresh_data(self) -> None:
        format_name = self.current_format
        summary = self._service.get_summary(format_name)
        top_cards = self._service.get_top_cards(format_name)

        if summary is None or not top_cards:
            self.card_list.set_rows([])
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

        rows: list[list[str]] = []
        for index, entry in enumerate(top_cards, start=1):
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
            rows.append(
                [
                    str(index),
                    entry.card_name,
                    str(entry.copies_played),
                    str(stats.mainboard_decks_present),
                    _format_avg(stats.mainboard_avg_arithmetic),
                    _format_avg(stats.mainboard_avg_karsten),
                    str(stats.sideboard_decks_present),
                    _format_avg(stats.sideboard_avg_arithmetic),
                    _format_avg(stats.sideboard_avg_karsten),
                    _format_archetypes(stats),
                    _format_formats(legality_by_name.get(entry.card_name, [])),
                ]
            )
        self.card_list.set_rows(rows)

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()

    def _bind_header_tooltips(self) -> None:
        """Per-column tooltips, on the header where they belong.

        The old binding was ``EVT_MOTION`` on the list body, so hovering an
        actual column *header* -- a separate ``SysHeader32`` HWND that never
        forwards mouse events to the list -- showed nothing. The grid's column
        label window is a real wx window, so the same idea works here. The
        always-visible legend under the toolbar is the primary explanation; this
        is the per-column detail.
        """
        self.card_list.header.Bind(wx.EVT_MOTION, self._on_header_motion)
        self.card_list.header.Bind(wx.EVT_LEAVE_WINDOW, self._on_header_leave)

    def _on_header_motion(self, event: wx.MouseEvent) -> None:
        col = self.card_list.column_at(event.GetPosition().x)
        key = _HEADER_TOOLTIP_KEYS.get(col) if col is not None else None
        self._set_header_tooltip(self._t(key) if key else "")
        event.Skip()

    def _on_header_leave(self, event: wx.MouseEvent) -> None:
        self._set_header_tooltip("")
        event.Skip()

    def _set_header_tooltip(self, text: str) -> None:
        header = self.card_list.header
        current = header.GetToolTip()
        if (current.GetTip() if current else "") == text:
            return
        header.SetToolTip(text)
