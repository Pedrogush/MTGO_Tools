"""Public state setters and control toggles for the deck research panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from widgets.panels.deck_research_panel.protocol import DeckResearchPanelProto

    _Base = DeckResearchPanelProto
else:
    _Base = object


class DeckResearchHandlersMixin(_Base):
    """UI-mutating setters, resets, and enable/disable helpers for :class:`DeckResearchPanel`."""

    def set_event_type_filter(self, value: str) -> None:
        if not self.event_type_choice.SetStringSelection(value):
            self.event_type_choice.SetSelection(0)

    def reset_event_type_filter(self) -> None:
        self.event_type_choice.SetSelection(0)

    def set_placement_filter(self, op: str, field: str, value: str) -> None:
        if not self.placement_op_choice.SetStringSelection(op):
            self.placement_op_choice.SetSelection(0)
        if not self.placement_field_choice.SetStringSelection(field):
            self.placement_field_choice.SetSelection(0)
        self.placement_value_filter.ChangeValue(value)

    def reset_placement_filter(self) -> None:
        self.placement_op_choice.SetSelection(0)
        self.placement_field_choice.SetSelection(0)
        self.placement_value_filter.ChangeValue("")

    def set_player_name_filter(self, value: str) -> None:
        self.player_name_filter.ChangeValue(value)

    def reset_player_name_filter(self) -> None:
        self.player_name_filter.ChangeValue("")

    def set_date_filter(self, value: str) -> None:
        self.date_filter.ChangeValue(value)

    def reset_date_filter(self) -> None:
        self.date_filter.ChangeValue("")

    def set_loading_state(self) -> None:
        self.archetype_combo.Clear()
        self.archetype_combo.Append(self._labels.get("loading_archetypes", "Loading..."))
        self.archetype_combo.SetSelection(0)
        self.archetype_combo.Disable()

    def set_error_state(self) -> None:
        self.archetype_combo.Clear()
        self.archetype_combo.Append(
            self._labels.get("failed_archetypes", "Failed to load archetypes.")
        )
        self.archetype_combo.SetSelection(0)

    def populate_archetypes(self, archetype_names: list[str]) -> None:
        self.archetype_combo.Clear()
        if not archetype_names:
            self.archetype_combo.Append(self._labels.get("no_archetypes", "No archetypes found."))
            self.archetype_combo.SetSelection(0)
            self.archetype_combo.Disable()
        else:
            for name in archetype_names:
                self.archetype_combo.Append(name)
            self.archetype_combo.SetSelection(0)
            self.archetype_combo.Enable()

    def enable_controls(self) -> None:
        self.archetype_combo.Enable()
        self.format_choice.Enable()

    def disable_controls(self) -> None:
        self.archetype_combo.Disable()
        self.format_choice.Disable()
