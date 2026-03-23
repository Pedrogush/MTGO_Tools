"""Panel for browsing MTG deck archetypes and filtering by format."""

from collections.abc import Callable

import wx

from utils.constants import DARK_PANEL, PADDING_MD
from utils.stylize import (
    stylize_button,
    stylize_choice,
    stylize_label,
    stylize_listbox,
    stylize_textctrl,
)


class DeckResearchPanel(wx.Panel):
    """Panel for selecting format, searching archetypes, and browsing tournament data."""

    def __init__(
        self,
        parent: wx.Window,
        format_options: list[str],
        initial_format: str,
        on_format_changed: Callable[[], None],
        on_archetype_filter: Callable[[], None],
        on_archetype_selected: Callable[[], None],
        on_reload_archetypes: Callable[[], None],
        on_switch_to_builder: Callable[[], None] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)

        # Store callbacks
        self._on_format_changed = on_format_changed
        self._on_archetype_filter = on_archetype_filter
        self._on_archetype_selected = on_archetype_selected
        self._on_reload_archetypes = on_reload_archetypes
        self._on_switch_to_builder = on_switch_to_builder

        # Store initial format
        self.initial_format = initial_format
        self.format_options = format_options
        self._labels = labels or {}

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the research panel UI."""
        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Deck Builder navigation button
        if self._on_switch_to_builder is not None:
            builder_btn = wx.Button(
                self, label=self._labels.get("switch_to_builder", "Deck Builder")
            )
            stylize_button(builder_btn)
            builder_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_switch_to_builder())  # type: ignore[misc]
            sizer.Add(builder_btn, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Format selection
        format_label = wx.StaticText(self, label=self._labels.get("format", "Format"))
        stylize_label(format_label)
        sizer.Add(format_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, PADDING_MD)

        self.format_choice = wx.Choice(self, choices=self.format_options)
        self.format_choice.SetStringSelection(self.initial_format)
        stylize_choice(self.format_choice)
        self.format_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._on_format_changed())
        sizer.Add(self.format_choice, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Search control
        self.search_ctrl = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowSearchButton(True)
        self.search_ctrl.SetHint(self._labels.get("search_hint", "Search archetypes..."))
        self.search_ctrl.Bind(wx.EVT_TEXT, lambda _evt: self._on_archetype_filter())
        stylize_textctrl(self.search_ctrl)
        sizer.Add(self.search_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Archetype list
        self.archetype_list = wx.ListBox(self, style=wx.LB_SINGLE)
        stylize_listbox(self.archetype_list)
        self.archetype_list.Bind(wx.EVT_LISTBOX, lambda _evt: self._on_archetype_selected())
        sizer.Add(self.archetype_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Reload button
        refresh_button = wx.Button(
            self, label=self._labels.get("reload_archetypes", "Reload Archetypes")
        )
        stylize_button(refresh_button)
        refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self._on_reload_archetypes())
        sizer.Add(refresh_button, 0, wx.EXPAND | wx.ALL, PADDING_MD)

    def get_selected_format(self) -> str:
        """Get the currently selected format."""
        return self.format_choice.GetStringSelection()

    def get_search_query(self) -> str:
        """Get the current search query."""
        return self.search_ctrl.GetValue().strip().lower()

    def get_selected_archetype_index(self) -> int:
        """Get the index of the selected archetype (-1 if none selected)."""
        idx = self.archetype_list.GetSelection()
        return idx if idx != wx.NOT_FOUND else -1

    def set_loading_state(self) -> None:
        """Set the panel to loading state."""
        self.archetype_list.Clear()
        self.archetype_list.Append(self._labels.get("loading_archetypes", "Loading..."))
        self.archetype_list.Disable()

    def set_error_state(self) -> None:
        """Set the panel to error state."""
        self.archetype_list.Clear()
        self.archetype_list.Append(
            self._labels.get("failed_archetypes", "Failed to load archetypes.")
        )

    def populate_archetypes(self, archetype_names: list[str]) -> None:
        """
        Populate the archetype list with names.

        Args:
            archetype_names: List of archetype names to display
        """
        self.archetype_list.Clear()
        if not archetype_names:
            self.archetype_list.Append(self._labels.get("no_archetypes", "No archetypes found."))
            self.archetype_list.Disable()
            return

        for name in archetype_names:
            self.archetype_list.Append(name)
        self.archetype_list.Enable()

    def enable_controls(self) -> None:
        """Enable all interactive controls."""
        self.archetype_list.Enable()
        self.format_choice.Enable()
        self.search_ctrl.Enable()

    def disable_controls(self) -> None:
        """Disable all interactive controls."""
        self.archetype_list.Disable()
        self.format_choice.Disable()
        self.search_ctrl.Disable()
