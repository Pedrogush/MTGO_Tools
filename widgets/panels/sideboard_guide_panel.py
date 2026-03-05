"""
Sideboard Guide Panel - Manages matchup-specific sideboarding strategies.

Allows users to create, edit, and manage guides for different matchups, including cards
to side in/out and matchup notes.
"""

from __future__ import annotations

from collections.abc import Callable

import wx
import wx.dataview as dv

from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.stylize import stylize_button


class SideboardGuidePanel(wx.Panel):
    """Panel that manages sideboard guides for matchups."""

    def __init__(
        self,
        parent: wx.Window,
        on_add_entry: Callable[[], None],
        on_edit_entry: Callable[[], None],
        on_remove_entry: Callable[[], None],
        on_edit_exclusions: Callable[[], None],
        on_export_csv: Callable[[], None],
        on_import_csv: Callable[[], None],
        labels: dict[str, str] | None = None,
    ):
        """
        Initialize the sideboard guide panel.

        Args:
            parent: Parent window
            on_add_entry: Callback for adding a new guide entry
            on_edit_entry: Callback for editing selected entry
            on_remove_entry: Callback for removing selected entry
            on_edit_exclusions: Callback for editing archetype exclusions
            on_export_csv: Callback for exporting guide to CSV
            on_import_csv: Callback for importing guide from CSV
        """
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.on_add_entry = on_add_entry
        self.on_edit_entry = on_edit_entry
        self.on_remove_entry = on_remove_entry
        self.on_edit_exclusions = on_edit_exclusions
        self.on_export_csv = on_export_csv
        self.on_import_csv = on_import_csv
        self._labels = labels or {}

        self.entries: list[dict[str, str]] = []
        self.exclusions: list[str] = []

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Guide entries list
        self.guide_view = dv.DataViewListCtrl(self, style=dv.DV_ROW_LINES)
        self.guide_view.AppendTextColumn(self._labels.get("col_archetype", "Archetype"), width=150)
        self.guide_view.AppendTextColumn(self._labels.get("col_play_out", "Play: Out"), width=150)
        self.guide_view.AppendTextColumn(self._labels.get("col_play_in", "Play: In"), width=150)
        self.guide_view.AppendTextColumn(self._labels.get("col_draw_out", "Draw: Out"), width=150)
        self.guide_view.AppendTextColumn(self._labels.get("col_draw_in", "Draw: In"), width=150)
        self.guide_view.AppendTextColumn(self._labels.get("col_notes", "Notes"), width=180)
        self.guide_view.SetBackgroundColour(DARK_ALT)
        self.guide_view.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.guide_view, 1, wx.EXPAND | wx.ALL, 6)

        # Button row
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.add_btn = wx.Button(self, label=self._labels.get("btn_add", "Add Entry"))
        stylize_button(self.add_btn)
        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add_clicked)
        buttons.Add(self.add_btn, 0, wx.RIGHT, 6)

        self.edit_btn = wx.Button(self, label=self._labels.get("btn_edit", "Edit Entry"))
        stylize_button(self.edit_btn)
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit_clicked)
        buttons.Add(self.edit_btn, 0, wx.RIGHT, 6)

        self.remove_btn = wx.Button(self, label=self._labels.get("btn_remove", "Remove Entry"))
        stylize_button(self.remove_btn)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove_clicked)
        buttons.Add(self.remove_btn, 0, wx.RIGHT, 6)

        self.exclusions_btn = wx.Button(
            self, label=self._labels.get("btn_exclusions", "Exclude Archetypes")
        )
        stylize_button(self.exclusions_btn)
        self.exclusions_btn.Bind(wx.EVT_BUTTON, self._on_exclusions_clicked)
        buttons.Add(self.exclusions_btn, 0, wx.RIGHT, 6)

        self.export_btn = wx.Button(self, label=self._labels.get("btn_export", "Export CSV"))
        stylize_button(self.export_btn)
        self.export_btn.Bind(wx.EVT_BUTTON, self._on_export_clicked)
        buttons.Add(self.export_btn, 0, wx.RIGHT, 6)

        self.import_btn = wx.Button(self, label=self._labels.get("btn_import", "Import CSV"))
        stylize_button(self.import_btn)
        self.import_btn.Bind(wx.EVT_BUTTON, self._on_import_clicked)
        buttons.Add(self.import_btn, 0)

        buttons.AddStretchSpacer(1)

        # Exclusions label
        self.exclusions_label = wx.StaticText(
            self, label=self._labels.get("exclusions_none", "Exclusions: \u2014")
        )
        self.exclusions_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.exclusions_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Warning label (hidden by default)
        self.warning_label = wx.StaticText(self, label="")
        self.warning_label.SetForegroundColour(wx.Colour(255, 165, 0))  # Orange
        self.warning_label.Hide()
        sizer.Add(self.warning_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

    # ============= Public API =============

    def set_entries(
        self, entries: list[dict[str, str]], exclusions: list[str] | None = None
    ) -> None:
        """
        Set the guide entries and exclusions.

        Args:
            entries: List of guide entry dictionaries
            exclusions: List of excluded archetype names
        """
        self.entries = entries
        self.exclusions = exclusions or []
        self._refresh_view()

    def get_entries(self) -> list[dict[str, str]]:
        """Get the current guide entries."""
        return self.entries

    def get_exclusions(self) -> list[str]:
        """Get the current excluded archetypes."""
        return self.exclusions

    def get_selected_index(self) -> int | None:
        """
        Get the index of the currently selected entry.

        Returns:
            Index of selected entry, or None if no selection
        """
        item = self.guide_view.GetSelection()
        if not item.IsOk():
            return None
        return self.guide_view.ItemToRow(item)

    def clear(self) -> None:
        """Clear all guide entries."""
        self.entries = []
        self.exclusions = []
        self._refresh_view()

    def set_warning(self, message: str) -> None:
        """
        Display a warning message.

        Args:
            message: Warning text to display (empty string to hide)
        """
        if message:
            self.warning_label.SetLabel(message)
            self.warning_label.Show()
        else:
            self.warning_label.Hide()
        self.Layout()

    # ============= Private Methods =============

    def _refresh_view(self) -> None:
        """Refresh the guide view display."""
        self.guide_view.DeleteAllItems()

        # Add entries (skip excluded archetypes)
        for entry in self.entries:
            if entry.get("archetype") in self.exclusions:
                continue
            self.guide_view.AppendItem(
                [
                    entry.get("archetype", ""),
                    self._format_card_list(entry.get("play_out", {})),
                    self._format_card_list(entry.get("play_in", {})),
                    self._format_card_list(entry.get("draw_out", {})),
                    self._format_card_list(entry.get("draw_in", {})),
                    entry.get("notes", ""),
                ]
            )

        # Update exclusions label
        if self.exclusions:
            text = ", ".join(self.exclusions)
            label = self._labels.get("exclusions", "Exclusions: {exclusions}").format(
                exclusions=text
            )
        else:
            label = self._labels.get("exclusions_none", "Exclusions: \u2014")
        self.exclusions_label.SetLabel(label)

    def _format_card_list(self, cards: dict[str, int] | str) -> str:
        """
        Format a card list for display.

        Args:
            cards: Either a dict mapping card name to quantity, or a string (for old format)

        Returns:
            Formatted string like "2x Lightning Bolt, 1x Mountain"
        """
        if isinstance(cards, str):
            # Old format - just return the string
            return cards

        if not cards:
            return ""

        # New format - dict of card name to quantity
        formatted = []
        for name, qty in sorted(cards.items()):
            formatted.append(f"{qty}x {name}")
        return ", ".join(formatted)

    def _on_add_clicked(self, _event: wx.Event) -> None:
        """Handle Add Entry button click."""
        self.on_add_entry()

    def _on_edit_clicked(self, _event: wx.Event) -> None:
        """Handle Edit Entry button click."""
        self.on_edit_entry()

    def _on_remove_clicked(self, _event: wx.Event) -> None:
        """Handle Remove Entry button click."""
        self.on_remove_entry()

    def _on_exclusions_clicked(self, _event: wx.Event) -> None:
        """Handle Exclude Archetypes button click."""
        self.on_edit_exclusions()

    def _on_export_clicked(self, _event: wx.Event) -> None:
        """Handle Export CSV button click."""
        self.on_export_csv()

    def _on_import_clicked(self, _event: wx.Event) -> None:
        """Handle Import CSV button click."""
        self.on_import_csv()
