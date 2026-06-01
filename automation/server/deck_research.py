"""Deck-research command handlers: formats, archetypes, deck list/text, tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class DeckResearchMixin(_Base):
    """Format / archetype / deck-selection command handlers."""

    def _handle_set_format(self, format_name: str) -> dict[str, Any]:
        """Set the current format."""
        if self.frame.research_panel:
            research_panel = self.frame.research_panel
            research_panel.format_choice.SetStringSelection(format_name)
            # Trigger the format changed callback (no args needed)
            if hasattr(self.frame, "on_format_changed"):
                self.frame.on_format_changed()
            return {"format": format_name, "set": True}
        return {"set": False, "error": "Research panel not available"}

    def _handle_get_format(self) -> dict[str, Any]:
        """Get the current format."""
        format_name = ""
        if hasattr(self.frame, "controller"):
            format_name = self.frame.controller.current_format
        return {"format": format_name}

    def _handle_get_archetypes(self) -> dict[str, Any]:
        """Get list of archetypes."""
        archetypes = []
        if hasattr(self.frame, "filtered_archetypes"):
            archetypes = [
                {"name": a.get("name", "Unknown"), "url": a.get("url", "")}
                for a in self.frame.filtered_archetypes
            ]
        return {"archetypes": archetypes, "count": len(archetypes)}

    def _handle_select_archetype(
        self, index: int | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Select an archetype by index or name."""
        if self.frame.research_panel is None:
            return {"selected": False, "error": "Research panel not available"}

        research_panel = self.frame.research_panel

        if name is not None:
            # Find by name
            for i, archetype in enumerate(getattr(self.frame, "filtered_archetypes", [])):
                if archetype.get("name") == name:
                    index = i
                    break
            if index is None:
                return {"selected": False, "error": f"Archetype not found: {name}"}

        if index is not None:
            # Set selection in the list; +1 because "Any" occupies position 0
            research_panel.archetype_list.SetSelection(index + 1)
            # Trigger the selection callback (no args needed)
            if hasattr(self.frame, "on_archetype_selected"):
                self.frame.on_archetype_selected()
            return {"selected": True, "index": index}

        return {"selected": False, "error": "No index or name provided"}

    def _handle_get_deck_list(self) -> dict[str, Any]:
        """Get the list of decks in the deck list."""
        decks = []
        if hasattr(self.frame, "deck_list"):
            for i in range(self.frame.deck_list.GetCount()):
                decks.append(
                    {
                        "index": i,
                        "text": self.frame.deck_list.GetString(i),
                    }
                )
        return {"decks": decks, "count": len(decks)}

    def _handle_select_deck(self, index: int) -> dict[str, Any]:
        """Select a deck by index."""
        if not hasattr(self.frame, "deck_list"):
            return {"selected": False, "error": "Deck list not available"}

        if index < 0 or index >= self.frame.deck_list.GetCount():
            return {"selected": False, "error": f"Invalid index: {index}"}

        self.frame.deck_list.SetSelection(index)
        # Trigger selection event
        event = wx.CommandEvent(wx.wxEVT_LISTBOX, self.frame.deck_list.GetId())
        event.SetInt(index)
        event.SetEventObject(self.frame.deck_list)
        self.frame.deck_list.ProcessEvent(event)
        return {"selected": True, "index": index}

    def _handle_get_deck_text(self) -> dict[str, Any]:
        """Get the current deck text."""
        deck_text = ""
        if hasattr(self.frame, "controller"):
            deck_text = self.frame.controller.deck_repo.get_current_deck_text()
        return {"deck_text": deck_text}

    def _handle_switch_tab(self, tab_name: str) -> dict[str, Any]:
        """Switch to a specific tab in the deck tabs."""
        if not hasattr(self.frame, "deck_tabs"):
            return {"switched": False, "error": "Deck tabs not available"}

        notebook = self.frame.deck_tabs
        for i in range(notebook.GetPageCount()):
            if notebook.GetPageText(i).lower() == tab_name.lower():
                notebook.SetSelection(i)
                return {"switched": True, "tab": tab_name, "index": i}

        return {"switched": False, "error": f"Tab not found: {tab_name}"}

    def _handle_get_deck_notes(self) -> dict[str, Any]:
        """Get the current deck notes cards and resolved deck key."""
        deck_repo = self.frame.controller.deck_repo
        notes_panel = self.frame.deck_notes_panel
        return {
            "deck_key": deck_repo.get_current_deck_key(),
            "notes": notes_panel.get_notes(),
        }

    def _handle_set_current_deck(self, deck: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set the current deck identity used for deck-scoped stores."""
        deck_repo = self.frame.controller.deck_repo
        deck_repo.set_current_deck(deck)
        return {
            "deck_key": deck_repo.get_current_deck_key(),
        }
