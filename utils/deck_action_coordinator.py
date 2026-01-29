"""Coordinates deck actions like copy, save, and daily average."""

from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

if TYPE_CHECKING:
    from controllers.app_controller import AppController


class DeckActionCoordinator:
    """Handles deck copy, save, and averaging operations."""

    def __init__(
        self,
        controller: "AppController",
        get_zone_cards: Callable[[], dict],
        on_status: Callable[[str], None],
    ):
        self.controller = controller
        self.get_zone_cards = get_zone_cards
        self.on_status = on_status

    def copy_to_clipboard(self, parent: wx.Window) -> None:
        """Copy current deck to clipboard."""
        zone_cards = self.get_zone_cards()
        deck_content = self.controller.build_deck_text(zone_cards).strip()

        if not deck_content:
            wx.MessageBox("No deck to copy.", "Copy Deck", wx.OK | wx.ICON_INFORMATION)
            return

        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(deck_content))
            finally:
                wx.TheClipboard.Close()
            self.on_status("Deck copied to clipboard.")
        else:
            wx.MessageBox("Could not access clipboard.", "Copy Deck", wx.OK | wx.ICON_WARNING)

    def save_to_file(self, parent: wx.Window, current_format: str) -> tuple[str, str] | None:
        """Save current deck to file and database."""
        zone_cards = self.get_zone_cards()
        deck_content = self.controller.build_deck_text(zone_cards).strip()

        if not deck_content:
            wx.MessageBox("Load a deck first.", "Save Deck", wx.OK | wx.ICON_INFORMATION)
            return None

        # Get default name
        default_name = "saved_deck"
        current_deck = self.controller.deck_repo.get_current_deck()
        if current_deck:
            from widgets.handlers.app_event_handlers import AppEventHandlers

            default_name = AppEventHandlers.format_deck_name(current_deck).replace(" | ", "_")

        # Prompt for name
        dlg = wx.TextEntryDialog(parent, "Deck name:", "Save Deck", default_name=default_name)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return None

        deck_name = dlg.GetValue().strip() or default_name
        dlg.Destroy()

        # Save deck
        try:
            file_path, deck_id = self.controller.save_deck(
                deck_name=deck_name,
                deck_content=deck_content,
                format_name=current_format,
                deck=current_deck,
            )
        except OSError as exc:
            wx.MessageBox(
                f"Failed to write deck file:\n{exc}",
                "Save Deck",
                wx.OK | wx.ICON_ERROR,
            )
            return None

        message = f"Deck saved to {file_path}"
        if deck_id:
            message += f"\nDatabase ID: {deck_id}"

        wx.MessageBox(message, "Deck Saved", wx.OK | wx.ICON_INFORMATION)
        self.on_status("Deck saved successfully.")

        return file_path, deck_id
