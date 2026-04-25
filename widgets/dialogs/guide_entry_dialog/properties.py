"""Data getters and setters for the guide entry dialog."""

from __future__ import annotations

from typing import Any

import wx

from widgets.panels.sideboard_card_selector import SideboardCardSelector


class GuideEntryDialogPropertiesMixin:
    """Data accessors for :class:`GuideEntryDialog`."""

    archetype_ctrl: wx.ComboBox
    play_out_selector: SideboardCardSelector
    play_in_selector: SideboardCardSelector
    draw_out_selector: SideboardCardSelector
    draw_in_selector: SideboardCardSelector
    notes_ctrl: wx.TextCtrl
    enable_double_checkbox: wx.CheckBox

    def _load_data(self, data: dict[str, Any]) -> None:
        # Load play out/in
        if "play_out" in data:
            self.play_out_selector.set_selected_cards(data["play_out"])
        if "play_in" in data:
            self.play_in_selector.set_selected_cards(data["play_in"])

        # Load draw out/in
        if "draw_out" in data:
            self.draw_out_selector.set_selected_cards(data["draw_out"])
        if "draw_in" in data:
            self.draw_in_selector.set_selected_cards(data["draw_in"])

    def get_data(self) -> dict[str, Any]:
        return {
            "archetype": self.archetype_ctrl.GetValue().strip(),
            "play_out": self.play_out_selector.get_selected_cards(),
            "play_in": self.play_in_selector.get_selected_cards(),
            "draw_out": self.draw_out_selector.get_selected_cards(),
            "draw_in": self.draw_in_selector.get_selected_cards(),
            "notes": self.notes_ctrl.GetValue().strip(),
            "enable_double_entries": self.enable_double_checkbox.GetValue(),
        }
