"""Read-only accessors for the deck research panel filters."""

from __future__ import annotations

import wx


class DeckResearchPropertiesMixin:
    """Filter getters for :class:`DeckResearchPanel`.

    Kept as a mixin (no ``__init__``) so :class:`DeckResearchPanel` remains
    the single source of truth for instance-state initialization.
    """

    event_type_choice: wx.Choice
    placement_op_choice: wx.ComboBox
    placement_field_choice: wx.ComboBox
    placement_value_filter: wx.TextCtrl
    player_name_filter: wx.TextCtrl
    date_filter: wx.TextCtrl
    format_choice: wx.Choice
    archetype_combo: wx.ComboBox

    def get_event_type_filter(self) -> str:
        return self.event_type_choice.GetStringSelection()

    def get_placement_filter(self) -> tuple[str, str, str]:
        return (
            self.placement_op_choice.GetStringSelection(),
            self.placement_field_choice.GetStringSelection(),
            self.placement_value_filter.GetValue().strip(),
        )

    def get_player_name_filter(self) -> str:
        return self.player_name_filter.GetValue().strip().lower()

    def get_date_filter(self) -> str:
        return self.date_filter.GetValue().strip()

    def get_selected_format(self) -> str:
        return self.format_choice.GetStringSelection()

    def get_search_query(self) -> str:
        return ""

    def get_selected_archetype_index(self) -> int:
        idx = self.archetype_combo.GetSelection()
        return idx if idx != wx.NOT_FOUND else -1
