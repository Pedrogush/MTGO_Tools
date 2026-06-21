"""Keyboard shortcut handlers for card / deck editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class CardShortcutHandlers(_Base):
    """Map keypresses to deck-edit actions on the selected/search card."""

    def _on_hotkey(self: AppFrame, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_F1 and not event.ControlDown():
            self._open_help()
            return

        if not event.ControlDown():
            # Plain +/-/Delete edit the quantity of the currently selected deck
            # card in whatever view (grid/table/pile) is showing. Skipped while a
            # text field has focus so they don't clobber normal typing.
            if not self._typing_in_text_field():
                if key_code in (ord("+"), wx.WXK_NUMPAD_ADD, ord("=")):
                    if self._handle_increment_shortcut():
                        return
                elif key_code in (ord("-"), wx.WXK_NUMPAD_SUBTRACT):
                    if self._handle_decrement_shortcut():
                        return
                elif key_code in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                    if self._handle_remove_shortcut():
                        return
            event.Skip()
            return
        handled = False

        if key_code in (ord("D"), ord("d")):
            self._show_left_panel("builder")
            handled = True
        elif key_code in (ord("R"), ord("r")):
            self._show_left_panel("research")
            handled = True
        elif key_code in (ord("1"), wx.WXK_NUMPAD1):
            handled = self._handle_increment_shortcut()
        elif key_code in (ord("2"), wx.WXK_NUMPAD2):
            handled = self._handle_decrement_shortcut()

        if handled:
            return
        event.Skip()

    @staticmethod
    def _typing_in_text_field() -> bool:
        """True when keyboard focus is on an editable text control.

        Used to suppress the bare +/-/Delete deck-edit shortcuts while the user
        is typing in a search box, deck-name field, notes area, etc.
        """
        focused = wx.Window.FindFocus()
        return isinstance(focused, (wx.TextCtrl, wx.SearchCtrl, wx.ComboBox))

    def _handle_increment_shortcut(self: AppFrame) -> bool:
        selection = self._get_selected_zone_card()
        if selection:
            zone, card = selection
            self._handle_zone_delta(zone, card["name"], 1)
            self._focus_card_in_zone(zone, card["name"])
            return True

        search_card = self._get_selected_search_card()
        if search_card:
            zone = self._get_active_zone_for_add()
            name = search_card.get("name")
            if name:
                self._handle_zone_delta(zone, name, 1)
                self._focus_card_in_zone(zone, name)
                return True
        return False

    def _handle_decrement_shortcut(self: AppFrame) -> bool:
        selection = self._get_selected_zone_card()
        if selection is None:
            return False
        zone, card = selection
        if zone not in {"main", "side"}:
            return False
        self._handle_zone_delta(zone, card["name"], -1)
        self._focus_card_in_zone(zone, card["name"])
        return True

    def _handle_remove_shortcut(self: AppFrame) -> bool:
        """Remove the selected card from its zone entirely (the [Del] shortcut)."""
        selection = self._get_selected_zone_card()
        if selection is None:
            return False
        zone, card = selection
        self._handle_zone_remove(zone, card["name"])
        return True
