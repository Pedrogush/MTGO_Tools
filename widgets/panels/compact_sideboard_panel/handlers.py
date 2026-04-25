"""Event handlers and public state setters for the compact sideboard panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

if TYPE_CHECKING:
    from widgets.panels.compact_sideboard_panel.protocol import CompactSideboardPanelProto

    _Base = CompactSideboardPanelProto
else:
    _Base = object


class CompactSideboardHandlersMixin(_Base):
    """Public setters, toggle callback, and list population for :class:`CompactSideboardPanel`."""

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
        self.status_label.SetLabel("Waiting for opponent\u2026")
        self.card_list.Clear()
        self.toggle_btn.Hide()
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
