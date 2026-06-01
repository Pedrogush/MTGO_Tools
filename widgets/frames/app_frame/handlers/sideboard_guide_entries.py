"""Dialog-driven sideboard guide entry CRUD handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from widgets.dialogs.guide_entry_dialog import GuideEntryDialog

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class SideboardGuideEntryHandlers(_Base):
    """Add/edit/remove guide entries, exclusions, flex slots, and view refresh."""

    def _refresh_guide_view(self: AppFrame) -> None:
        self.sideboard_guide_panel.set_entries(
            self.sideboard_guide_entries, self.sideboard_exclusions
        )

    def _on_add_guide_entry(self: AppFrame) -> None:
        names = [item.get("name", "") for item in self.archetypes]
        mainboard = self.zone_cards.get("main", [])
        sideboard = self.zone_cards.get("side", [])

        dlg = GuideEntryDialog(
            self,
            names,
            mainboard_cards=mainboard,
            sideboard_cards=sideboard,
            flex_slots=self.sideboard_flex_slots,
            locale=self.locale,
        )

        while True:
            result = dlg.ShowModal()
            if result == wx.ID_CANCEL:
                break

            data = dlg.get_data()
            if data.get("archetype"):
                archetype_name = data.get("archetype")
                enable_double = data.get("enable_double_entries", False)

                entry_data = {k: v for k, v in data.items() if k != "enable_double_entries"}

                if not enable_double:
                    existing_index = None
                    for i, entry in enumerate(self.sideboard_guide_entries):
                        if entry.get("archetype") == archetype_name:
                            existing_index = i
                            break

                    if existing_index is not None:
                        self.sideboard_guide_entries[existing_index] = entry_data
                    else:
                        self.sideboard_guide_entries.append(entry_data)
                else:
                    self.sideboard_guide_entries.append(entry_data)

                self._persist_guide_for_current()
                self._refresh_guide_view()

            if result == wx.ID_OK:
                break

        dlg.Destroy()

    def _on_edit_guide_entry(self: AppFrame) -> None:
        index = self.sideboard_guide_panel.get_selected_index()
        if index is None:
            wx.MessageBox(
                "Select an entry to edit.", "Sideboard Guide", wx.OK | wx.ICON_INFORMATION
            )
            return
        data = self.sideboard_guide_entries[index]
        names = [item.get("name", "") for item in self.archetypes]
        dlg = GuideEntryDialog(
            self,
            names,
            mainboard_cards=self.zone_cards.get("main", []),
            sideboard_cards=self.zone_cards.get("side", []),
            data=data,
            flex_slots=self.sideboard_flex_slots,
            locale=self.locale,
        )
        if dlg.ShowModal() == wx.ID_OK:
            updated = dlg.get_data()
            if updated.get("archetype"):
                self.sideboard_guide_entries[index] = updated
                self._persist_guide_for_current()
                self._refresh_guide_view()
        dlg.Destroy()

    def _on_remove_guide_entry(self: AppFrame) -> None:
        index = self.sideboard_guide_panel.get_selected_index()
        if index is None:
            wx.MessageBox(
                "Select an entry to remove.", "Sideboard Guide", wx.OK | wx.ICON_INFORMATION
            )
            return
        del self.sideboard_guide_entries[index]
        self._persist_guide_for_current()
        self._refresh_guide_view()

    def _on_edit_exclusions(self: AppFrame) -> None:
        archetype_names = [item.get("name", "") for item in self.archetypes]
        dlg = wx.MultiChoiceDialog(
            self,
            "Select archetypes to exclude from the printed guide.",
            "Sideboard Guide",
            archetype_names,
        )
        selected_indices = [
            archetype_names.index(name)
            for name in self.sideboard_exclusions
            if name in archetype_names
        ]
        dlg.SetSelections(selected_indices)
        if dlg.ShowModal() == wx.ID_OK:
            selections = dlg.GetSelections()
            self.sideboard_exclusions = [archetype_names[idx] for idx in selections]
            self._persist_guide_for_current()
            self._refresh_guide_view()
        dlg.Destroy()

    def _on_edit_flex_slots(self: AppFrame) -> None:
        mainboard_cards = self.zone_cards.get("main", [])
        if not mainboard_cards:
            wx.MessageBox("No mainboard cards loaded.", "Flex Slots", wx.OK | wx.ICON_INFORMATION)
            return

        card_names = [card["name"] for card in mainboard_cards]
        dlg = wx.MultiChoiceDialog(
            self,
            "Select mainboard cards that can be taken out during sideboarding (flex slots).\n"
            "These will be highlighted in the Out selectors when adding guide entries.",
            "Flex Slots",
            card_names,
        )
        selected_indices = [
            card_names.index(name) for name in self.sideboard_flex_slots if name in card_names
        ]
        dlg.SetSelections(selected_indices)
        if dlg.ShowModal() == wx.ID_OK:
            selections = dlg.GetSelections()
            self.sideboard_flex_slots = [card_names[idx] for idx in selections]
            self._persist_guide_for_current()
        dlg.Destroy()
