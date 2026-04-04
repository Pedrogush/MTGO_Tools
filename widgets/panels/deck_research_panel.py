"""Panel for browsing MTG deck archetypes and filtering by format."""

import math
from collections.abc import Callable

import wx

from utils.constants import (
    APP_FRAME_SUMMARY_MIN_HEIGHT,
    ARCHETYPE_LIST_HEIGHT,
    DARK_PANEL,
    PADDING_MD,
)
from utils.stylize import (
    stylize_button,
    stylize_choice,
    stylize_label,
    stylize_listbox,
    stylize_textctrl,
)
from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.deck_results_list import DeckResultsList

_NUM_ARCHETYPE_COLS = 3


class ArchetypeMultiColumnList(wx.Panel):
    """Archetype list displayed in 3 equal columns for better space utilization."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent)
        self._items: list[str] = []
        self._selected_index: int = wx.NOT_FOUND
        self._on_select_callback: Callable[[], None] | None = None

        self._boxes: list[wx.ListBox] = []
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        for i in range(_NUM_ARCHETYPE_COLS):
            box = wx.ListBox(self, style=wx.LB_SINGLE)
            stylize_listbox(box)
            box.Bind(wx.EVT_LISTBOX, self._on_box_select)
            padding = PADDING_MD if i < _NUM_ARCHETYPE_COLS - 1 else 0
            sizer.Add(box, 1, wx.EXPAND | wx.RIGHT, padding)
            self._boxes.append(box)
        self.SetSizer(sizer)

    def _num_rows(self) -> int:
        n = len(self._items)
        return math.ceil(n / _NUM_ARCHETYPE_COLS) if n > 0 else 0

    def _on_box_select(self, event: wx.CommandEvent) -> None:
        src_box = event.GetEventObject()
        col = self._boxes.index(src_box)
        row = src_box.GetSelection()
        if row == wx.NOT_FOUND:
            return
        num_rows = self._num_rows()
        if num_rows == 0:
            return
        global_idx = col * num_rows + row
        if global_idx >= len(self._items):
            return
        for i, box in enumerate(self._boxes):
            if i != col:
                box.SetSelection(wx.NOT_FOUND)
        self._selected_index = global_idx
        if self._on_select_callback is not None:
            self._on_select_callback()

    def _rebuild_columns(self) -> None:
        for box in self._boxes:
            box.Freeze()
        try:
            n = len(self._items)
            num_rows = math.ceil(n / _NUM_ARCHETYPE_COLS) if n > 0 else 0
            for col, box in enumerate(self._boxes):
                box.Clear()
                start = col * num_rows
                end = min(start + num_rows, n)
                for i in range(start, end):
                    box.Append(self._items[i])
        finally:
            for box in self._boxes:
                box.Thaw()

    def Bind(self, event, handler=None, source=None, id=wx.ID_ANY, id2=wx.ID_ANY) -> None:  # type: ignore[override]
        if event is wx.EVT_LISTBOX:
            self._on_select_callback = handler
        else:
            super().Bind(event, handler, source, id, id2)

    def Clear(self) -> None:  # type: ignore[override]
        self._items.clear()
        self._selected_index = wx.NOT_FOUND
        for box in self._boxes:
            box.Clear()

    def Append(self, item: str) -> int:  # type: ignore[override]
        self._items.append(item)
        self._rebuild_columns()
        return len(self._items) - 1

    def GetCount(self) -> int:
        return len(self._items)

    def GetSelection(self) -> int:
        return self._selected_index

    def SetSelection(self, n: int) -> None:  # type: ignore[override]
        if n < 0:
            self._selected_index = wx.NOT_FOUND
            for box in self._boxes:
                box.SetSelection(wx.NOT_FOUND)
            return
        if n >= len(self._items):
            return
        self._selected_index = n
        num_rows = self._num_rows()
        if num_rows == 0:
            return
        col = n // num_rows
        row = n % num_rows
        for i, box in enumerate(self._boxes):
            box.SetSelection(row if i == col else wx.NOT_FOUND)

    def Enable(self, enable: bool = True) -> bool:  # type: ignore[override]
        for box in self._boxes:
            box.Enable(enable)
        return True

    def Disable(self) -> bool:  # type: ignore[override]
        return self.Enable(False)

    def SetToolTip(self, tip: str | wx.ToolTip) -> None:  # type: ignore[override]
        tooltip = tip if isinstance(tip, wx.ToolTip) else wx.ToolTip(tip)
        for box in self._boxes:
            box.SetToolTip(tooltip)


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
        on_deck_selected: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_daily_average: Callable[[], None] | None = None,
        on_load: Callable[[], None] | None = None,
        on_event_type_filter: Callable[[], None] | None = None,
        on_result_filter: Callable[[], None] | None = None,
        on_player_name_filter: Callable[[], None] | None = None,
        on_date_filter: Callable[[], None] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)

        # Store callbacks
        self._on_format_changed = on_format_changed
        self._on_archetype_filter = on_archetype_filter
        self._on_archetype_selected = on_archetype_selected
        self._on_reload_archetypes = on_reload_archetypes
        self._on_switch_to_builder = on_switch_to_builder
        self._on_deck_selected = on_deck_selected
        self._on_copy = on_copy
        self._on_save = on_save
        self._on_daily_average = on_daily_average
        self._on_load = on_load
        self._on_event_type_filter = on_event_type_filter
        self._on_result_filter = on_result_filter
        self._on_player_name_filter = on_player_name_filter
        self._on_date_filter = on_date_filter

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

        # Row 1: Deck Builder navigation button (full width)
        if self._on_switch_to_builder is not None:
            builder_btn = wx.Button(
                self, label=self._labels.get("switch_to_builder", "Deck Builder")
            )
            stylize_button(builder_btn)
            builder_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_switch_to_builder())  # type: ignore[misc]
            sizer.Add(builder_btn, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Format selector (above archetype row)
        format_label = wx.StaticText(self, label=self._labels.get("format", "Format"))
        stylize_label(format_label)
        sizer.Add(format_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, PADDING_MD)

        self.format_choice = wx.Choice(self, choices=self.format_options)
        self.format_choice.SetStringSelection(self.initial_format)
        stylize_choice(self.format_choice)
        if tip := self._labels.get("format_tooltip"):
            self.format_choice.SetToolTip(tip)
        self.format_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._on_format_changed())
        sizer.Add(self.format_choice, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Row 2: Archetype selector (left) + Event Type placeholder (right)
        row2 = wx.BoxSizer(wx.HORIZONTAL)

        self.search_ctrl = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowSearchButton(True)
        self.search_ctrl.SetHint(self._labels.get("search_hint", "Search archetypes..."))
        if tip := self._labels.get("search_tooltip"):
            self.search_ctrl.SetToolTip(tip)
        self.search_ctrl.Bind(wx.EVT_TEXT, lambda _evt: self._on_archetype_filter())
        stylize_textctrl(self.search_ctrl)
        row2.Add(self.search_ctrl, 1, wx.EXPAND | wx.RIGHT, PADDING_MD)

        # Event Type filter
        self.event_type_choice = wx.Choice(
            self,
            choices=["All", "Challenge", "League", "Showcase", "Last Chance"],
        )
        self.event_type_choice.SetSelection(0)
        stylize_choice(self.event_type_choice)
        if self._on_event_type_filter is not None:
            self.event_type_choice.Bind(
                wx.EVT_CHOICE, lambda _evt: self._on_event_type_filter()  # type: ignore[misc]
            )
        row2.Add(self.event_type_choice, 1, wx.EXPAND)

        sizer.Add(row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Archetype list (3-column layout)
        self.archetype_list = ArchetypeMultiColumnList(self)
        self.archetype_list.SetMinSize((-1, ARCHETYPE_LIST_HEIGHT))
        self.archetype_list.SetMaxSize((-1, ARCHETYPE_LIST_HEIGHT))
        if tip := self._labels.get("archetypes_tooltip"):
            self.archetype_list.SetToolTip(tip)
        self.archetype_list.Bind(wx.EVT_LISTBOX, lambda _evt: self._on_archetype_selected())
        sizer.Add(self.archetype_list, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Reload button
        refresh_button = wx.Button(
            self, label=self._labels.get("reload_archetypes", "Reload Archetypes")
        )
        stylize_button(refresh_button)
        if tip := self._labels.get("reload_tooltip"):
            refresh_button.SetToolTip(tip)
        refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self._on_reload_archetypes())
        sizer.Add(refresh_button, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Row 3: Result filter placeholder (left) + Player Name filter placeholder (right)
        row3 = wx.BoxSizer(wx.HORIZONTAL)

        self.result_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.result_filter.SetHint(self._labels.get("result_hint", "Result..."))
        stylize_textctrl(self.result_filter)
        if self._on_result_filter is not None:
            self.result_filter.Bind(wx.EVT_TEXT, lambda _evt: self._on_result_filter())  # type: ignore[misc]
        row3.Add(self.result_filter, 1, wx.EXPAND | wx.RIGHT, PADDING_MD)

        self.player_name_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.player_name_filter.SetHint(self._labels.get("player_name_hint", "Player name..."))
        stylize_textctrl(self.player_name_filter)
        if self._on_player_name_filter is not None:
            self.player_name_filter.Bind(wx.EVT_TEXT, lambda _evt: self._on_player_name_filter())  # type: ignore[misc]
        row3.Add(self.player_name_filter, 1, wx.EXPAND)

        sizer.Add(row3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Row 4: Date filter (full width)
        self.date_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.date_filter.SetHint(self._labels.get("date_hint", "YYYY-MM-DD"))
        stylize_textctrl(self.date_filter)
        if self._on_date_filter is not None:
            self.date_filter.Bind(wx.EVT_TEXT, lambda _evt: self._on_date_filter())  # type: ignore[misc]
        sizer.Add(self.date_filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # --- Deck results bottom section ---
        self._build_deck_results_section(sizer)

    def _build_deck_results_section(self, sizer: wx.Sizer) -> None:
        """Build the action buttons, summary text, and deck results list at the bottom."""
        # Row 5: Deck action buttons (above deck results)
        self.deck_action_buttons = DeckActionButtons(
            self,
            on_copy=self._on_copy,
            on_save=self._on_save,
            on_daily_average=self._on_daily_average,
            on_load=self._on_load,
            labels={
                "daily_average": self._labels.get("daily_average", "Today's Average"),
                "copy": self._labels.get("copy", "Copy"),
                "load_deck": self._labels.get("load_deck", "Load Deck"),
                "save_deck": self._labels.get("save_deck", "Save Deck"),
                "daily_average_tooltip": self._labels.get("daily_average_tooltip", ""),
                "copy_tooltip": self._labels.get("copy_tooltip", ""),
                "load_deck_tooltip": self._labels.get("load_deck_tooltip", ""),
                "save_deck_tooltip": self._labels.get("save_deck_tooltip", ""),
            },
        )
        sizer.Add(
            self.deck_action_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD
        )

        # Summary text
        self.summary_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.NO_BORDER,
        )
        stylize_textctrl(self.summary_text, multiline=True)
        self.summary_text.SetMinSize((-1, APP_FRAME_SUMMARY_MIN_HEIGHT))
        sizer.Add(self.summary_text, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Row 6: Deck results list (fills remaining space)
        self.deck_list = DeckResultsList(self)
        if self._on_deck_selected is not None:
            self.deck_list.Bind(wx.EVT_LISTBOX, lambda _evt: self._on_deck_selected())  # type: ignore[misc]
        sizer.Add(self.deck_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Expose button references for backward compatibility
        self.daily_average_button = self.deck_action_buttons.daily_average_button
        self.copy_button = self.deck_action_buttons.copy_button
        self.load_button = self.deck_action_buttons.load_button
        self.save_button = self.deck_action_buttons.save_button

    def get_event_type_filter(self) -> str:
        """Get the selected event type filter ('All' means no filter)."""
        return self.event_type_choice.GetStringSelection()

    def set_event_type_filter(self, value: str) -> None:
        """Set the event type filter without triggering a change event."""
        if not self.event_type_choice.SetStringSelection(value):
            self.event_type_choice.SetSelection(0)

    def reset_event_type_filter(self) -> None:
        """Reset the event type filter to 'All'."""
        self.event_type_choice.SetSelection(0)

    def get_result_filter(self) -> str:
        """Get the current result filter text (partial match against deck result field)."""
        return self.result_filter.GetValue().strip().lower()

    def set_result_filter(self, value: str) -> None:
        """Set the result filter text without triggering a change event."""
        self.result_filter.ChangeValue(value)

    def reset_result_filter(self) -> None:
        """Clear the result filter input."""
        self.result_filter.ChangeValue("")

    def get_player_name_filter(self) -> str:
        """Get the current player name filter text (partial, case-insensitive)."""
        return self.player_name_filter.GetValue().strip().lower()

    def set_player_name_filter(self, value: str) -> None:
        """Set the player name filter text without triggering a change event."""
        self.player_name_filter.ChangeValue(value)

    def reset_player_name_filter(self) -> None:
        """Clear the player name filter input."""
        self.player_name_filter.ChangeValue("")

    def get_date_filter(self) -> str:
        """Get the current date filter text (prefix match against deck date field)."""
        return self.date_filter.GetValue().strip()

    def set_date_filter(self, value: str) -> None:
        """Set the date filter text without triggering a change event."""
        self.date_filter.ChangeValue(value)

    def reset_date_filter(self) -> None:
        """Clear the date filter input."""
        self.date_filter.ChangeValue("")

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
