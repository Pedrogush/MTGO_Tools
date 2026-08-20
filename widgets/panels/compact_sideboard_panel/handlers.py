"""Event handlers and public state setters for the compact sideboard panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from widgets.wx_layout import relayout

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
        self._show_list()
        self._populate_list()
        self.Show()
        relayout(self.GetParent())
        logger.debug(f"Compact sideboard guide displayed for: {archetype_name}")

    def clear(self) -> None:
        self._current_entry = None
        self.header_label.SetLabel("Guide: —")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self._show_empty(
            "Waiting for opponent\u2026",
            "Your sideboard plan appears here once the matchup is known.",
        )
        relayout(self.GetParent())

    def set_no_guide(self, archetype_name: str) -> None:
        self._current_entry = None
        self.header_label.SetLabel(f"Guide: {archetype_name}")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self._show_empty(
            "No guide entry for this matchup.",
            "Add one in the Sideboard Guide tab of the pinned deck.",
        )
        self.Show()
        relayout(self.GetParent())

    def set_no_pinned_deck(self) -> None:
        self._current_entry = None
        self.header_label.SetLabel("Guide: —")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self._show_empty(
            "No deck pinned.",
            "Pin a deck's guide in the Deck Selector to enable this.",
        )
        self.Show()
        relayout(self.GetParent())

    # ---- S4: see the compact radar panel.
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
