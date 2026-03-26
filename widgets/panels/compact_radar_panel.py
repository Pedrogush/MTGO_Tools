"""
Compact Radar Panel - Displays archetype card frequency in a small format.

Designed for embedding in the opponent tracker overlay.
Two view modes:
  - "Top Cards": Top 15 mainboard / 8 sideboard cards with inclusion rates
  - "Full Decklist": All cards as an average decklist (avg copies rounded)
"""

from __future__ import annotations

from enum import Enum

from loguru import logger

from services.radar_service import RadarData
from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.wx_compat import get_wx

wx = get_wx()


class RadarViewMode(Enum):
    """View modes for the compact radar panel."""

    TOP_CARDS = "top"
    FULL_DECKLIST = "full"


_TOP_MAINBOARD_LIMIT = 15
_TOP_SIDEBOARD_LIMIT = 8


class CompactRadarPanel(wx.Panel):
    """Compact panel for displaying radar data in small overlays."""

    def __init__(self, parent: wx.Window):
        """
        Initialize the compact radar panel.

        Args:
            parent: Parent window
        """
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.current_radar: RadarData | None = None
        self._view_mode: RadarViewMode = RadarViewMode.TOP_CARDS

        self._build_ui()
        self.Hide()

    def _build_ui(self) -> None:
        """Build the compact panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Header row: label + view toggle button
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 4)

        self.header_label = wx.StaticText(self, label="Radar: Loading...")
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        font = self.header_label.GetFont()
        font = font.Bold()
        self.header_label.SetFont(font)
        header_sizer.Add(self.header_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.view_toggle_btn = wx.Button(self, label="Full Decklist", size=(90, 22))
        self.view_toggle_btn.SetBackgroundColour(DARK_BG)
        self.view_toggle_btn.SetForegroundColour(LIGHT_TEXT)
        self.view_toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_view)
        self.view_toggle_btn.Hide()
        header_sizer.Add(self.view_toggle_btn, 0, wx.LEFT, 4)

        # Status label (for loading/errors)
        self.status_label = wx.StaticText(self, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        # Scrollable list for cards
        self.card_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.card_list.SetBackgroundColour(DARK_BG)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.card_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

    # ============= Public API =============

    @property
    def view_mode(self) -> RadarViewMode:
        """Current view mode."""
        return self._view_mode

    def display_radar(self, radar: RadarData) -> None:
        """
        Display radar data in the current view mode.

        Args:
            radar: RadarData to display
        """
        self.current_radar = radar
        self.header_label.SetLabel(f"Radar: {radar.archetype_name}")
        self.view_toggle_btn.Show()
        self._populate_card_list()
        self.Show()
        self.GetParent().Layout()
        logger.debug(f"Compact radar displayed: {radar.archetype_name}")

    def clear(self) -> None:
        """Clear the radar display and hide panel."""
        self.current_radar = None
        self.header_label.SetLabel("Radar: Loading...")
        self.status_label.SetLabel("")
        self.card_list.Clear()
        self.view_toggle_btn.Hide()
        self.Hide()
        self.GetParent().Layout()

    def set_loading(self, message: str = "Loading radar data...") -> None:
        """
        Show loading state.

        Args:
            message: Loading message to display
        """
        self.header_label.SetLabel("Radar: Loading...")
        self.status_label.SetLabel(message)
        self.card_list.Clear()
        self.view_toggle_btn.Hide()
        self.Show()
        self.GetParent().Layout()

    def set_error(self, error_message: str) -> None:
        """
        Show error state.

        Args:
            error_message: Error message to display
        """
        self.header_label.SetLabel("Radar: Error")
        self.status_label.SetLabel(error_message)
        self.card_list.Clear()
        self.view_toggle_btn.Hide()
        self.Show()
        self.GetParent().Layout()

    # ============= Private Methods =============

    def _on_toggle_view(self, _event: wx.CommandEvent) -> None:
        """Toggle between Top Cards and Full Decklist views."""
        if self._view_mode == RadarViewMode.TOP_CARDS:
            self._view_mode = RadarViewMode.FULL_DECKLIST
        else:
            self._view_mode = RadarViewMode.TOP_CARDS
        self._update_toggle_button_label()
        self._populate_card_list()

    def _update_toggle_button_label(self) -> None:
        """Update toggle button label to show the other view option."""
        if self._view_mode == RadarViewMode.TOP_CARDS:
            self.view_toggle_btn.SetLabel("Full Decklist")
        else:
            self.view_toggle_btn.SetLabel("Top Cards")

    def _populate_card_list(self) -> None:
        """Populate the card list based on the current view mode."""
        if not self.current_radar:
            return

        if self._view_mode == RadarViewMode.TOP_CARDS:
            self._populate_top_cards()
        else:
            self._populate_full_decklist()

    def _populate_top_cards(self) -> None:
        """Populate with top N mainboard/sideboard cards and inclusion rates."""
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
        """Populate with full average decklist (all cards, rounded avg copies)."""
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
