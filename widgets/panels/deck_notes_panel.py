"""
Deck Notes Panel - Simple text editor for deck notes.

Allows users to write and save notes about their decks.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_PANEL
from utils.stylize import stylize_button, stylize_textctrl

if TYPE_CHECKING:
    from repositories.deck_repository import DeckRepository
    from services.store_service import StoreService


class DeckNotesPanel(wx.Panel):
    """Panel for editing and saving deck notes."""

    def __init__(
        self,
        parent: wx.Window,
        deck_repo: DeckRepository,
        store_service: StoreService,
        notes_store: dict,
        notes_store_path: Path,
        on_status_update: Callable[[str], None],
        labels: dict[str, str] | None = None,
    ):
        """
        Initialize the deck notes panel.

        Args:
            parent: Parent window
            deck_repo: Repository for deck operations
            store_service: Service for storing/loading data
            notes_store: Dictionary containing deck notes
            notes_store_path: Path to notes store file
            on_status_update: Callback for status updates
            labels: Localized label strings
        """
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.deck_repo = deck_repo
        self.store_service = store_service
        self.notes_store = notes_store
        self.notes_store_path = notes_store_path
        self.on_status_update = on_status_update
        self._labels = labels or {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Text control for notes
        self.notes_text = wx.TextCtrl(self, style=wx.TE_MULTILINE)
        stylize_textctrl(self.notes_text, multiline=True)
        sizer.Add(self.notes_text, 1, wx.EXPAND | wx.ALL, 6)

        # Button row
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.save_btn = wx.Button(self, label=self._labels.get("button.save_notes", "Save Notes"))
        stylize_button(self.save_btn)
        self.save_btn.Bind(wx.EVT_BUTTON, self._on_save_clicked)
        buttons.Add(self.save_btn, 0, wx.RIGHT, 6)

        buttons.AddStretchSpacer(1)

    # ============= Public API =============

    def set_notes(self, notes: str) -> None:
        """
        Set the notes text.

        Args:
            notes: Notes text to display
        """
        self.notes_text.ChangeValue(notes)

    def get_notes(self) -> str:
        """
        Get the current notes text.

        Returns:
            Current notes text
        """
        return self.notes_text.GetValue()

    def clear(self) -> None:
        """Clear the notes text."""
        self.notes_text.ChangeValue("")

    def load_notes_for_current(self) -> None:
        """Load notes for the deck currently selected."""
        deck_key = self.deck_repo.get_current_deck_key()
        note = self.notes_store.get(deck_key, "")
        self.set_notes(note)

    def save_current_notes(self) -> None:
        """Persist notes for the currently selected deck."""
        deck_key = self.deck_repo.get_current_deck_key()
        self.notes_store[deck_key] = self.get_notes()
        self.store_service.save_store(self.notes_store_path, self.notes_store)
        self.on_status_update(self._labels.get("status.notes_saved", "Deck notes saved."))

    # ============= Private Methods =============

    def _on_save_clicked(self, _event: wx.Event) -> None:
        """Handle Save Notes button click."""
        self.save_current_notes()
