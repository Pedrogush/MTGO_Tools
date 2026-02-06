"""
Compact Radar Panel - Displays archetype card frequency in a small format.

Designed for embedding in the opponent tracker overlay.
Shows top mainboard and sideboard cards with inclusion rates.
"""

from __future__ import annotations

import wx
from loguru import logger

from services.radar_service import RadarData
from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT


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

        self._build_ui()
        self.Hide()

    def _build_ui(self) -> None:
        """Build the compact panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Header
        self.header_label = wx.StaticText(self, label="Radar: Loading...")
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        font = self.header_label.GetFont()
        font = font.Bold()
        self.header_label.SetFont(font)
        sizer.Add(self.header_label, 0, wx.ALL, 4)

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

    def display_radar(self, radar: RadarData) -> None:
        """
        Display radar data in compact format.

        Args:
            radar: RadarData to display
        """
        self.current_radar = radar

        # Update header
        self.header_label.SetLabel(f"Radar: {radar.archetype_name}")

        # Update status
        self.status_label.SetLabel(
            f"From {radar.total_decks_analyzed} decks | "
            f"{len(radar.mainboard_cards)} MB / {len(radar.sideboard_cards)} SB cards"
        )

        # Clear and populate list
        self.card_list.Clear()

        # Add mainboard section (top 10-15 cards)
        mainboard_display = min(15, len(radar.mainboard_cards))
        if mainboard_display > 0:
            self.card_list.Append("─── Mainboard ───")
            for card in radar.mainboard_cards[:mainboard_display]:
                # Format: "4x CardName (95%)"
                avg_copies = int(round(card.avg_copies))
                line = f"{avg_copies}x {card.card_name} ({card.inclusion_rate:.0f}%)"
                self.card_list.Append(line)

        # Add sideboard section (top 5-8 cards)
        sideboard_display = min(8, len(radar.sideboard_cards))
        if sideboard_display > 0:
            self.card_list.Append("")
            self.card_list.Append("─── Sideboard ───")
            for card in radar.sideboard_cards[:sideboard_display]:
                avg_copies = int(round(card.avg_copies))
                line = f"{avg_copies}x {card.card_name} ({card.inclusion_rate:.0f}%)"
                self.card_list.Append(line)

        # Show the panel
        self.Show()
        self.GetParent().Layout()

        logger.debug(f"Compact radar displayed: {radar.archetype_name}")

    def clear(self) -> None:
        """Clear the radar display and hide panel."""
        self.current_radar = None
        self.header_label.SetLabel("Radar: Loading...")
        self.status_label.SetLabel("")
        self.card_list.Clear()
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
        self.Show()
        self.GetParent().Layout()
