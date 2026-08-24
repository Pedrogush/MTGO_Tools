"""Event handlers and public state setters for the compact sideboard panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants.ui_layout import (
    COMPACT_SIDEBOARD_MIN_WRAP_WIDTH,
    COMPACT_SIDEBOARD_NOTE_WRAP_MARGIN,
)
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from widgets.panels.compact_sideboard_panel.protocol import CompactSideboardPanelProto

    _Base = CompactSideboardPanelProto
else:
    _Base = object


class CompactSideboardHandlersMixin(_Base):
    """Public setters, toggle callback, and list population for :class:`CompactSideboardPanel`."""

    def _set_header_text(self, text: str) -> None:
        """Set the pane heading, wrapped to the width the panel actually has.

        The heading shares its row with the On Play/On Draw toggle, so a long
        archetype name ("Guide: Goryo's Vengeance") does not fit on one line in
        a narrow column and ``wx.StaticText`` simply clips what does not fit.
        Wrapping it keeps the whole archetype name readable.
        """
        self._header_text = text
        self.header_label.SetLabel(text)
        self.header_label.Wrap(self._header_wrap_width())

    def _header_wrap_width(self) -> int:
        toggle_w = self.toggle_btn.GetSize().GetWidth() if self.toggle_btn.IsShown() else 0
        width = self.GetClientSize().GetWidth() - toggle_w - COMPACT_SIDEBOARD_NOTE_WRAP_MARGIN
        return max(width, COMPACT_SIDEBOARD_MIN_WRAP_WIDTH)

    def _on_resized(self, event: wx.SizeEvent) -> None:
        """Re-wrap the heading and the notes for the panel's new width."""
        event.Skip()
        if self._resizing or not hasattr(self, "header_label"):
            return
        self._resizing = True
        try:
            # Lay out first: both re-wraps measure their control's client width,
            # and the children still carry the *previous* width until the sizer
            # has run for the new one.
            self.Layout()
            self._set_header_text(self._header_text)
            self._populate_list()
        finally:
            self._resizing = False

    def display_entry(self, entry: dict, archetype_name: str) -> None:
        self._current_entry = entry
        self._set_header_text(f"Guide: {archetype_name}")
        self.toggle_btn.Show()
        self._show_list()
        self._populate_list()
        self.Show()
        relayout(self.GetParent())
        logger.debug(f"Compact sideboard guide displayed for: {archetype_name}")

    def clear(self) -> None:
        self._current_entry = None
        self._set_header_text("Guide: —")
        self.card_list.Clear()
        self.toggle_btn.Hide()
        self._show_empty(
            "Waiting for opponent\u2026",
            "Your sideboard plan appears here once the matchup is known.",
        )
        relayout(self.GetParent())

    def set_no_guide(self, archetype_name: str) -> None:
        self._current_entry = None
        self._set_header_text(f"Guide: {archetype_name}")
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
        self._set_header_text("Guide: —")
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
            for line in self._wrap_note_lines(notes):
                self.card_list.Append(f"  {line}")

    def _wrap_note_lines(self, notes: str) -> list[str]:
        """Break free-text notes into lines that fit the list's width.

        ``wx.ListBox`` neither wraps nor scrolls horizontally, so a note longer
        than the column was silently cut off mid-sentence. Measuring with the
        list's own font is the only way to know where to break: the guide text
        is proportional, so a character count would be wrong at both ends.
        """
        width = max(
            self.card_list.GetClientSize().GetWidth() - COMPACT_SIDEBOARD_NOTE_WRAP_MARGIN,
            COMPACT_SIDEBOARD_MIN_WRAP_WIDTH,
        )
        wrapped: list[str] = []
        for paragraph in notes.splitlines():
            current = ""
            for word in paragraph.split():
                candidate = f"{current} {word}".strip()
                if not current or self.card_list.GetTextExtent(candidate)[0] <= width:
                    current = candidate
                else:
                    wrapped.append(current)
                    current = word
            wrapped.append(current)
        return wrapped
