"""
Compact Sideboard Panel - Shows matchup-specific sideboarding plan in the opponent tracker.

Displays the cards to side in/out and notes for the detected opponent archetype,
sourced from the pinned deck's sideboard guide.
"""

from __future__ import annotations

import wx
from loguru import logger

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, PADDING_SM, SUBDUED_TEXT
from utils.constants.ui_layout import COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE


class CompactSideboardPanel(wx.Panel):
    """Compact panel for displaying a single sideboard guide entry in the opponent tracker."""

    def __init__(self, parent: wx.Window):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self._current_entry: dict | None = None
        self._play_first: bool = True  # True = on play, False = on draw

        self._build_ui()
        self.Hide()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Header row: archetype label + play/draw toggle
        header = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header, 0, wx.EXPAND | wx.ALL, PADDING_SM)

        self.header_label = wx.StaticText(self, label="Guide: —")
        self.header_label.SetForegroundColour(LIGHT_TEXT)
        font = self.header_label.GetFont()
        self.header_label.SetFont(font.Bold())
        header.Add(self.header_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.toggle_btn = wx.Button(self, label="On Draw", size=COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE)
        self.toggle_btn.SetBackgroundColour(DARK_BG)
        self.toggle_btn.SetForegroundColour(LIGHT_TEXT)
        self.toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_play_draw)
        self.toggle_btn.Hide()
        header.Add(self.toggle_btn, 0, wx.LEFT, PADDING_SM)

        # Status label (no guide found / no pinned deck)
        self.status_label = wx.StaticText(self, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

        # Cards list
        self.card_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.card_list.SetBackgroundColour(DARK_BG)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.card_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

    # ============= Public API =============

    def display_entry(self, entry: dict, archetype_name: str) -> None:
        self._current_entry = entry
        self.header_label.SetLabel(f"Guide: {archetype_name}")
        self.toggle_btn.Show()
        self._populate_list()
        self.Show()
        self.GetParent().Layout()
        logger.debug(f"Compact sideboard guide displayed for: {archetype_name}")

    def clear(self) -> None:
        self._current_entry = None
        self.header_label.SetLabel("Guide: —")
        self.status_label.SetLabel("")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self.Hide()
        self.GetParent().Layout()

    def set_no_guide(self, archetype_name: str) -> None:
        self._current_entry = None
        self.header_label.SetLabel(f"Guide: {archetype_name}")
        self.status_label.SetLabel("No guide entry for this matchup.")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self.Show()
        self.GetParent().Layout()

    def set_no_pinned_deck(self) -> None:
        self._current_entry = None
        self.header_label.SetLabel("Guide: —")
        self.status_label.SetLabel("Pin a deck's guide in the Deck Selector to enable this.")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self.Show()
        self.GetParent().Layout()

    # ============= Private Methods =============

    def _on_toggle_play_draw(self, _event: wx.CommandEvent) -> None:
        self._play_first = not self._play_first
        self.toggle_btn.SetLabel("On Draw" if self._play_first else "On Play")
        self._populate_list()

    def _populate_list(self) -> None:
        entry = self._current_entry
        if not entry:
            return

        self.card_list.Clear()
        self.status_label.SetLabel("")

        if self._play_first:
            out_cards = entry.get("play_out", {})
            in_cards = entry.get("play_in", {})
            scenario = "On Play"
        else:
            out_cards = entry.get("draw_out", {})
            in_cards = entry.get("draw_in", {})
            scenario = "On Draw"

        self.card_list.Append(f"─── {scenario} ───")

        if out_cards:
            self.card_list.Append("  OUT:")
            for name, qty in sorted(out_cards.items()):
                self.card_list.Append(f"    -{qty} {name}")

        if in_cards:
            self.card_list.Append("  IN:")
            for name, qty in sorted(in_cards.items()):
                self.card_list.Append(f"    +{qty} {name}")

        if not out_cards and not in_cards:
            self.card_list.Append("  (no changes)")

        notes = entry.get("notes", "").strip()
        if notes:
            self.card_list.Append("")
            self.card_list.Append("Notes:")
            for line in notes.splitlines():
                self.card_list.Append(f"  {line}")


__all__ = ["CompactSideboardPanel"]
