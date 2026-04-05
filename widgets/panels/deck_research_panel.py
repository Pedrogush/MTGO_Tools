"""Panel for browsing MTG deck archetypes and filtering by format."""

from __future__ import annotations

from collections.abc import Callable

import wx

from utils.constants import (
    APP_FRAME_SUMMARY_MIN_HEIGHT,
    DARK_ACCENT,
    DARK_ALT,
    DARK_PANEL,
    LIGHT_TEXT,
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

# ---------------------------------------------------------------------------
# Searchable combo helpers
# ---------------------------------------------------------------------------


class _ArchetypePopup(wx.ComboPopup):
    """Custom popup for the searchable archetype combo: search box + list."""

    _POPUP_MIN_W = 200
    _POPUP_MAX_H = 300

    def __init__(self, on_search: Callable[[], None]) -> None:
        super().__init__()
        self._on_search = on_search
        self._panel: wx.Panel | None = None
        self._search: wx.TextCtrl | None = None
        self._listbox: wx.ListBox | None = None
        self._buffered_items: list[str] = []

    # ------------------------------------------------------------------ wx interface

    def Create(self, parent: wx.Window) -> bool:
        self._panel = wx.Panel(parent, style=wx.BORDER_NONE)
        self._panel.SetBackgroundColour(wx.Colour(*DARK_ALT))

        sizer = wx.BoxSizer(wx.VERTICAL)

        self._search = wx.TextCtrl(self._panel, style=wx.TE_PROCESS_ENTER | wx.BORDER_SIMPLE)
        self._search.SetBackgroundColour(wx.Colour(*DARK_PANEL))
        self._search.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
        self._search.SetHint("Search…")
        sizer.Add(self._search, 0, wx.EXPAND | wx.ALL, 4)

        sep = wx.StaticLine(self._panel)
        sep.SetBackgroundColour(wx.Colour(*DARK_ACCENT))
        sizer.Add(sep, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        self._listbox = wx.ListBox(self._panel, style=wx.LB_SINGLE | wx.BORDER_NONE)
        stylize_listbox(self._listbox)
        sizer.Add(self._listbox, 1, wx.EXPAND | wx.ALL, 4)

        self._panel.SetSizer(sizer)

        # Populate from buffer (items set before popup was created)
        for item in self._buffered_items:
            self._listbox.Append(item)
        self._buffered_items = []

        self._search.Bind(wx.EVT_TEXT, self._on_search_text)
        self._listbox.Bind(wx.EVT_LISTBOX, self._on_item_clicked)
        return True

    def GetControl(self) -> wx.Window:
        return self._panel  # type: ignore[return-value]

    def OnPopup(self) -> None:
        if self._search:
            self._search.SetFocus()

    def GetAdjustedSize(self, min_w: int, pref_h: int, max_h: int) -> wx.Size:
        return wx.Size(max(min_w, self._POPUP_MIN_W), min(self._POPUP_MAX_H, max(max_h, 80)))

    # ------------------------------------------------------------------ event handlers

    def _on_search_text(self, _evt: wx.Event) -> None:
        self._on_search()

    def _on_item_clicked(self, _evt: wx.Event) -> None:
        if self._listbox is None:
            return
        sel = self._listbox.GetStringSelection()
        combo = self.GetComboCtrl()
        if combo:
            combo.SetValue(sel)
        self.Dismiss()
        # Propagate as EVT_CHOICE so the panel's on_archetype_selected fires
        combo_ctrl = self.GetComboCtrl()
        if combo_ctrl:
            evt = wx.CommandEvent(wx.wxEVT_CHOICE, combo_ctrl.GetId())
            wx.PostEvent(combo_ctrl, evt)

    # ------------------------------------------------------------------ data API

    def get_search_text(self) -> str:
        return self._search.GetValue().strip().lower() if self._search else ""

    def get_item_count(self) -> int:
        if self._listbox is not None:
            return self._listbox.GetCount()
        return len(self._buffered_items)

    def get_selection(self) -> int:
        if self._listbox is None:
            return -1
        idx = self._listbox.GetSelection()
        return -1 if idx == wx.NOT_FOUND else idx

    def set_selection(self, idx: int) -> None:
        if self._listbox is None:
            return
        if 0 <= idx < self._listbox.GetCount():
            self._listbox.SetSelection(idx)
            combo = self.GetComboCtrl()
            if combo:
                combo.SetValue(self._listbox.GetString(idx))

    def set_items(self, names: list[str]) -> None:
        if self._listbox is not None:
            self._listbox.Clear()
            for name in names:
                self._listbox.Append(name)
        else:
            self._buffered_items = list(names)

    def clear(self) -> None:
        self._buffered_items = []
        if self._listbox is not None:
            self._listbox.Clear()
        if self._search is not None:
            self._search.ChangeValue("")


class _SearchableArchetypeCombo(wx.ComboCtrl):
    """A ComboCtrl whose popup contains a search box followed by a list.

    Exposes a subset of the wx.Choice/wx.ListBox API used by the rest of the
    app (GetCount, GetSelection, SetSelection, Clear, Append, Enable, Disable)
    so callers do not need to know about the internal popup.
    """

    def __init__(
        self,
        parent: wx.Window,
        on_archetype_filter: Callable[[], None],
        on_archetype_selected: Callable[[], None],
        hint: str = "",
        tooltip: str = "",
    ) -> None:
        super().__init__(parent, style=wx.CB_READONLY | wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(*DARK_ALT))
        self.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
        if hint:
            self.SetHint(hint)
        if tooltip:
            self.SetToolTip(tooltip)

        self._popup = _ArchetypePopup(on_archetype_filter)
        self.SetPopupControl(self._popup)

        # Track item names and selection index independently of whether the
        # popup widget has been realised yet (Create() is called lazily).
        self._item_names: list[str] = []
        self._selected_idx: int = -1

        self.Bind(wx.EVT_CHOICE, lambda _e: on_archetype_selected())

    # ------------------------------------------------------------------ list API

    def Clear(self) -> None:
        self._item_names = []
        self._selected_idx = -1
        self.SetValue("")
        self._popup.clear()

    def Append(self, name: str) -> None:
        self._item_names.append(name)
        if self._popup._listbox is not None:
            self._popup._listbox.Append(name)
        else:
            self._popup._buffered_items.append(name)

    def GetCount(self) -> int:
        return len(self._item_names)

    def GetSelection(self) -> int:
        # Prefer the live popup selection if the popup has been shown
        live = self._popup.get_selection()
        return live if live >= 0 else self._selected_idx

    def SetSelection(self, idx: int) -> None:
        self._selected_idx = idx
        if 0 <= idx < len(self._item_names):
            self.SetValue(self._item_names[idx])
        self._popup.set_selection(idx)

    def get_search_text(self) -> str:
        return self._popup.get_search_text()

    def populate(self, names: list[str]) -> None:
        self._item_names = list(names)
        self._selected_idx = -1
        self.SetValue("")
        self._popup.set_items(names)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------


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
        on_reload_archetypes: Callable[[], None] | None = None,
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

        self._on_format_changed = on_format_changed
        self._on_archetype_filter = on_archetype_filter
        self._on_archetype_selected = on_archetype_selected
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

        self.initial_format = initial_format
        self.format_options = format_options
        self._labels = labels or {}

        self._build_ui()

    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Row 0: Deck Research / Deck Builder toggle button
        if self._on_switch_to_builder is not None:
            builder_btn = wx.Button(
                self, label=self._labels.get("switch_to_builder", "Deck Builder")
            )
            stylize_button(builder_btn)
            builder_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_switch_to_builder())  # type: ignore[misc]
            sizer.Add(builder_btn, 0, wx.EXPAND | wx.ALL, PADDING_MD)

            info_label = wx.StaticText(
                self,
                label=self._labels.get("info", "Deck research: search MTG decks by property"),
            )
            stylize_label(info_label, subtle=True)
            sizer.Add(info_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Row 1: Format | Archetype (side by side)
        format_arch_row = wx.BoxSizer(wx.HORIZONTAL)

        # Format column
        format_col = wx.BoxSizer(wx.VERTICAL)
        format_label = wx.StaticText(self, label=self._labels.get("format", "Format"))
        stylize_label(format_label, subtle=True)
        format_col.Add(format_label, 0)

        self.format_choice = wx.Choice(self, choices=self.format_options)
        self.format_choice.SetStringSelection(self.initial_format)
        stylize_choice(self.format_choice)
        if tip := self._labels.get("format_tooltip"):
            self.format_choice.SetToolTip(tip)
        self.format_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._on_format_changed())
        format_col.Add(self.format_choice, 0, wx.EXPAND | wx.TOP, PADDING_MD)
        format_arch_row.Add(format_col, 1, wx.EXPAND | wx.RIGHT, PADDING_MD)

        # Archetype column: label + searchable combo
        archetype_col = wx.BoxSizer(wx.VERTICAL)
        archetype_label = wx.StaticText(self, label=self._labels.get("archetype", "Archetype"))
        stylize_label(archetype_label, subtle=True)
        archetype_col.Add(archetype_label, 0)

        self.archetype_combo = _SearchableArchetypeCombo(
            self,
            on_archetype_filter=self._on_archetype_filter,
            on_archetype_selected=self._on_archetype_selected,
            hint=self._labels.get("search_hint", "Select archetype…"),
            tooltip=self._labels.get("archetypes_tooltip", ""),
        )
        archetype_col.Add(self.archetype_combo, 0, wx.EXPAND | wx.TOP, PADDING_MD)

        format_arch_row.Add(archetype_col, 1, wx.EXPAND)
        sizer.Add(format_arch_row, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Backward-compat aliases
        self.archetype_list = self.archetype_combo
        self.archetype_dropdown = self.archetype_combo
        # search_ctrl kept as alias pointing at the combo for any callers that
        # just need .GetValue() / .Enable() / .Disable()
        self.search_ctrl = self.archetype_combo

        # Row 2: Event type filter
        event_label = wx.StaticText(self, label=self._labels.get("event", "Event"))
        stylize_label(event_label, subtle=True)
        sizer.Add(event_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, PADDING_MD)

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
        sizer.Add(self.event_type_choice, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Row 3: Result | Player name
        row3_labels = wx.BoxSizer(wx.HORIZONTAL)
        result_label = wx.StaticText(self, label=self._labels.get("result", "Result"))
        stylize_label(result_label, subtle=True)
        player_name_label = wx.StaticText(
            self, label=self._labels.get("player_name", "Player name")
        )
        stylize_label(player_name_label, subtle=True)
        row3_labels.Add(result_label, 1, wx.RIGHT, PADDING_MD)
        row3_labels.Add(player_name_label, 1)
        sizer.Add(row3_labels, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)

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
            self.player_name_filter.Bind(
                wx.EVT_TEXT, lambda _evt: self._on_player_name_filter()  # type: ignore[misc]
            )
        row3.Add(self.player_name_filter, 1, wx.EXPAND)
        sizer.Add(row3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Row 4: Date filter
        date_label = wx.StaticText(self, label=self._labels.get("date", "Date"))
        stylize_label(date_label, subtle=True)
        sizer.Add(date_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, PADDING_MD)

        self.date_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.date_filter.SetHint(self._labels.get("date_hint", "YYYY-MM-DD"))
        stylize_textctrl(self.date_filter)
        if self._on_date_filter is not None:
            self.date_filter.Bind(wx.EVT_TEXT, lambda _evt: self._on_date_filter())  # type: ignore[misc]
        sizer.Add(self.date_filter, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        self._build_deck_results_section(sizer)

    def _build_deck_results_section(self, sizer: wx.Sizer) -> None:
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

        self.summary_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.NO_BORDER,
        )
        stylize_textctrl(self.summary_text, multiline=True)
        self.summary_text.SetMinSize((-1, APP_FRAME_SUMMARY_MIN_HEIGHT))
        sizer.Add(self.summary_text, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        self.deck_list = DeckResultsList(self)
        if self._on_deck_selected is not None:
            self.deck_list.Bind(wx.EVT_LISTBOX, lambda _evt: self._on_deck_selected())  # type: ignore[misc]
        sizer.Add(self.deck_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        self.daily_average_button = self.deck_action_buttons.daily_average_button
        self.copy_button = self.deck_action_buttons.copy_button
        self.load_button = self.deck_action_buttons.load_button
        self.save_button = self.deck_action_buttons.save_button

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_event_type_filter(self) -> str:
        return self.event_type_choice.GetStringSelection()

    def set_event_type_filter(self, value: str) -> None:
        if not self.event_type_choice.SetStringSelection(value):
            self.event_type_choice.SetSelection(0)

    def reset_event_type_filter(self) -> None:
        self.event_type_choice.SetSelection(0)

    def get_result_filter(self) -> str:
        return self.result_filter.GetValue().strip().lower()

    def set_result_filter(self, value: str) -> None:
        self.result_filter.ChangeValue(value)

    def reset_result_filter(self) -> None:
        self.result_filter.ChangeValue("")

    def get_player_name_filter(self) -> str:
        return self.player_name_filter.GetValue().strip().lower()

    def set_player_name_filter(self, value: str) -> None:
        self.player_name_filter.ChangeValue(value)

    def reset_player_name_filter(self) -> None:
        self.player_name_filter.ChangeValue("")

    def get_date_filter(self) -> str:
        return self.date_filter.GetValue().strip()

    def set_date_filter(self, value: str) -> None:
        self.date_filter.ChangeValue(value)

    def reset_date_filter(self) -> None:
        self.date_filter.ChangeValue("")

    def get_selected_format(self) -> str:
        return self.format_choice.GetStringSelection()

    def get_search_query(self) -> str:
        """Return the current archetype search text (typed inside the combo popup)."""
        return self.archetype_combo.get_search_text()

    def get_selected_archetype_index(self) -> int:
        idx = self.archetype_combo.GetSelection()
        return idx if idx >= 0 else -1

    def set_loading_state(self) -> None:
        self.archetype_combo.Clear()
        self.archetype_combo.SetValue(self._labels.get("loading_archetypes", "Loading..."))
        self.archetype_combo.Disable()

    def set_error_state(self) -> None:
        self.archetype_combo.Clear()
        self.archetype_combo.SetValue(
            self._labels.get("failed_archetypes", "Failed to load archetypes.")
        )

    def populate_archetypes(self, archetype_names: list[str]) -> None:
        self.archetype_combo.populate(archetype_names)
        if not archetype_names:
            self.archetype_combo.SetValue(
                self._labels.get("no_archetypes", "No archetypes found.")
            )
            self.archetype_combo.Disable()
        else:
            self.archetype_combo.Enable()

    def enable_controls(self) -> None:
        self.archetype_combo.Enable()
        self.format_choice.Enable()

    def disable_controls(self) -> None:
        self.archetype_combo.Disable()
        self.format_choice.Disable()
