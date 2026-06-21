"""Printing-navigation handlers for the card inspector panel.

The prev/next/auto-save/save callbacks and the small helpers that snapshot the
current printing and emit the printing-changed / printing-selected events
(issue #792 board-art-sync surface).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from widgets.panels.card_inspector_panel.protocol import CardInspectorPanelProto

    _Base = CardInspectorPanelProto
else:
    _Base = object


class PrintingNavMixin(_Base):
    """Prev/next/save callbacks and printing-change event emitters."""

    def _current_printing_dict(self) -> dict[str, Any] | None:
        """Return the currently displayed printing as a plain dict, or None."""
        printings = self.inspector_printings
        if not printings:
            return None
        try:
            entry = printings[self.inspector_current_printing]
        except IndexError:
            return None
        if isinstance(entry, dict):
            return entry
        if hasattr(entry, "get"):
            keys = (
                "id",
                "set",
                "set_name",
                "collector_number",
                "released_at",
                "flavor_text",
                "artist",
            )
            return {key: entry.get(key) for key in keys}
        return None

    def _emit_printing_changed(self) -> None:
        if not self._printing_changed_handler:
            return
        self._printing_changed_handler(self._current_printing_dict())

    def _emit_printing_selected(self, *, persist: bool) -> None:
        """Tell the app a printing was chosen for the current card (issue #792)."""
        if not self._printing_selected_handler:
            return
        printing = self._current_printing_dict()
        if printing is None:
            return
        self._printing_selected_handler(printing, persist)

    def _on_autosave_toggle(self, _event: wx.Event) -> None:
        self._autosave_printing = self.autosave_checkbox.GetValue()
        # The explicit button is redundant while auto-save is on.
        self.save_art_btn.Show(not self._autosave_printing)
        relayout(self.save_panel)
        # Turning auto-save on persists the printing already on screen.
        if self._autosave_printing:
            self._emit_printing_selected(persist=True)

    def _on_save_printing(self, _event: wx.Event) -> None:
        self._emit_printing_selected(persist=True)

    def _on_prev_printing(self, _event: wx.Event) -> None:
        if self.inspector_current_printing > 0:
            self.inspector_current_printing -= 1
            self._emit_printing_changed()
            self._emit_printing_selected(persist=self._autosave_printing)
            self._load_current_printing_image()

    def _on_next_printing(self, _event: wx.Event) -> None:
        if self.inspector_current_printing < len(self.inspector_printings) - 1:
            self.inspector_current_printing += 1
            self._emit_printing_changed()
            self._emit_printing_selected(persist=self._autosave_printing)
            self._load_current_printing_image()

    def _set_printing_label(self, text: str) -> None:
        self.printing_label.SetLabel(text)
        if self.printing_label_width:
            self.printing_label.Wrap(self.printing_label_width)
        self.nav_panel.Layout()
