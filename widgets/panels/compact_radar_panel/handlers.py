"""Event handlers, public state setters, and list populators for the compact radar panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants.ui_layout import (
    COMPACT_RADAR_HEADER_WRAP_MARGIN,
    COMPACT_RADAR_MIN_WRAP_WIDTH,
)
from widgets.panels.compact_radar_panel.properties import (
    _TOP_MAINBOARD_LIMIT,
    _TOP_SIDEBOARD_LIMIT,
    RadarViewMode,
)
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from services.radar_service import RadarData
    from widgets.panels.compact_radar_panel.protocol import CompactRadarPanelProto

    _Base = CompactRadarPanelProto
else:
    _Base = object


class CompactRadarHandlersMixin(_Base):
    """Public API, toggle callback, and list population for :class:`CompactRadarPanel`."""

    # ============= Public API =============

    def _set_header_text(self, text: str) -> None:
        """Set the pane heading, wrapped to the width the panel actually has.

        The heading shares its row with the view toggle, so a long archetype
        name ("Radar: Gruul Basking Broodscale Combo") does not fit on one line
        in a narrow pane and ``wx.StaticText`` clips whatever runs past the
        edge. Wrapping keeps the whole archetype name readable.
        """
        self._header_text = text
        self.header_label.SetLabel(text)
        self.header_label.Wrap(self._header_wrap_width())

    def _header_wrap_width(self) -> int:
        toggle_w = (
            self.view_toggle_btn.GetSize().GetWidth() if self.view_toggle_btn.IsShown() else 0
        )
        width = self.GetClientSize().GetWidth() - toggle_w - COMPACT_RADAR_HEADER_WRAP_MARGIN
        return max(width, COMPACT_RADAR_MIN_WRAP_WIDTH)

    def _on_resized(self, event: wx.SizeEvent) -> None:
        """Re-wrap the heading for the pane's new width."""
        event.Skip()
        if self._resizing or not hasattr(self, "header_label"):
            return
        self._resizing = True
        try:
            # Lay out first: the wrap measures the panel's client width, which
            # the sizer has not applied to the children yet.
            self.Layout()
            self._set_header_text(self._header_text)
        finally:
            self._resizing = False

    def display_radar(self, radar: RadarData) -> None:
        self.current_radar = radar
        self._set_header_text(f"Radar: {radar.archetype_name}")
        self.view_toggle_btn.Show()
        self._show_list()
        self._populate_card_list()
        self.Show()
        relayout(self.GetParent())
        logger.debug(f"Compact radar displayed: {radar.archetype_name}")

    def clear(self) -> None:
        self.current_radar = None
        self._set_header_text("Radar: —")
        self.card_list.Clear()
        self.view_toggle_btn.Hide()
        self._show_empty(
            "Waiting for opponent\u2026",
            "The archetype radar fills in as soon as a match is detected.",
        )
        relayout(self.GetParent())

    # ---- S4: an empty pane says what it is waiting for, in the middle of the
    # space it is waiting in, instead of a caption above an empty bordered box.
    def _show_empty(self, message: str, hint: str | None = None) -> None:
        self.status_label.SetLabel("")
        self.status_label.Hide()
        self.card_list.Hide()
        self.empty_state.set_message(message, hint)
        self.empty_state.Show()
        # relayout, not a bare Layout: a runtime Show/Hide with only Layout()
        # leaves ghost pixels from the native controls that just vanished.
        relayout(self)

    def _show_list(self) -> None:
        self.empty_state.Hide()
        self.status_label.Show()
        self.card_list.Show()
        relayout(self)

    def set_loading(self, message: str = "Loading radar data...") -> None:
        self._set_header_text("Radar: Loading...")
        self.status_label.SetLabel(message)
        self.card_list.Clear()
        self.view_toggle_btn.Hide()
        self.Show()
        relayout(self.GetParent())

    def set_error(self, error_message: str) -> None:
        self._set_header_text("Radar: Error")
        self.status_label.SetLabel(error_message)
        self.card_list.Clear()
        self.view_toggle_btn.Hide()
        self.Show()
        relayout(self.GetParent())

    # ============= Private Methods =============

    def _on_toggle_view(self, _event: wx.CommandEvent) -> None:
        if self._view_mode == RadarViewMode.TOP_CARDS:
            self._view_mode = RadarViewMode.FULL_DECKLIST
        else:
            self._view_mode = RadarViewMode.TOP_CARDS
        self._update_toggle_button_label()
        self._populate_card_list()

    def _update_toggle_button_label(self) -> None:
        if self._view_mode == RadarViewMode.TOP_CARDS:
            self.view_toggle_btn.SetLabel("Full Decklist")
        else:
            self.view_toggle_btn.SetLabel("Top Cards")

    def _populate_card_list(self) -> None:
        if not self.current_radar:
            return

        if self._view_mode == RadarViewMode.TOP_CARDS:
            self._populate_top_cards()
        else:
            self._populate_full_decklist()

    def _populate_top_cards(self) -> None:
        radar = self.current_radar
        if not radar:
            return

        self.status_label.SetLabel(
            f"Top cards from {radar.total_decks_analyzed} decks | "
            f"{len(radar.mainboard_cards)} MB / {len(radar.sideboard_cards)} SB"
        )

        self.card_list.Clear()

        mainboard_display = min(_TOP_MAINBOARD_LIMIT, len(radar.mainboard_cards))
        if mainboard_display > 0:
            self.card_list.Append("─── Mainboard ───")
            for card in radar.mainboard_cards[:mainboard_display]:
                avg_copies = max(1, int(round(card.avg_copies)))
                line = f"{avg_copies}x {card.card_name} ({card.inclusion_rate:.0f}%)"
                self.card_list.Append(line)

        sideboard_display = min(_TOP_SIDEBOARD_LIMIT, len(radar.sideboard_cards))
        if sideboard_display > 0:
            self.card_list.Append("")
            self.card_list.Append("─── Sideboard ───")
            for card in radar.sideboard_cards[:sideboard_display]:
                avg_copies = max(1, int(round(card.avg_copies)))
                line = f"{avg_copies}x {card.card_name} ({card.inclusion_rate:.0f}%)"
                self.card_list.Append(line)

    def _populate_full_decklist(self) -> None:
        radar = self.current_radar
        if not radar:
            return

        mainboard_total = sum(max(1, round(c.avg_copies)) for c in radar.mainboard_cards)
        sideboard_total = sum(max(1, round(c.avg_copies)) for c in radar.sideboard_cards)
        self.status_label.SetLabel(
            f"Average decklist from {radar.total_decks_analyzed} decks | "
            f"{mainboard_total} MB / {sideboard_total} SB"
        )

        self.card_list.Clear()

        if radar.mainboard_cards:
            self.card_list.Append(f"─── Mainboard ({mainboard_total}) ───")
            for card in radar.mainboard_cards:
                count = max(1, round(card.avg_copies))
                self.card_list.Append(f"{count} {card.card_name}")

        if radar.sideboard_cards:
            self.card_list.Append("")
            self.card_list.Append(f"─── Sideboard ({sideboard_total}) ───")
            for card in radar.sideboard_cards:
                count = max(1, round(card.avg_copies))
                self.card_list.Append(f"{count} {card.card_name}")
