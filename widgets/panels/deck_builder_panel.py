from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from services.radar_service import RadarData
from utils.constants import DARK_ALT, DARK_PANEL, FORMAT_OPTIONS, LIGHT_TEXT, SUBDUED_TEXT
from utils.mana_icon_factory import ManaIconFactory
from utils.stylize import (
    stylize_button,
    stylize_choice,
    stylize_label,
    stylize_textctrl,
)
from widgets.buttons.mana_button import create_mana_button


class _SearchResultsView(wx.ListCtrl):
    """Virtual ListCtrl for efficiently displaying large card search results."""

    def __init__(self, parent: wx.Window, style: int):
        super().__init__(parent, style=style | wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self._data: list[dict[str, Any]] = []

    def SetData(self, data: list[dict[str, Any]]) -> None:
        """Set the data source and refresh the display."""
        self._data = data
        self.SetItemCount(len(data))
        self.Refresh()

    def OnGetItemText(self, item: int, column: int) -> str:
        """Return text for the given item and column."""
        if item < 0 or item >= len(self._data):
            return ""

        card = self._data[item]
        if column == 0:
            return card.get("name", "Unknown")
        elif column == 1:
            mana_cost = card.get("mana_cost", "")
            return mana_cost if mana_cost else "—"
        return ""

    def GetItemText(self, row: int, col: int = 0) -> str:
        """Legacy method for test compatibility."""
        return self.OnGetItemText(row, col)


class DeckBuilderPanel(wx.Panel):
    """Panel for searching and filtering MTG cards by various properties."""

    _SEARCH_DEBOUNCE_MS = 300

    def __init__(
        self,
        parent: wx.Window,
        mana_icons: ManaIconFactory,
        on_switch_to_research: Callable[[], None],
        on_ensure_card_data: Callable[[], None],
        open_mana_keyboard: Callable[[], None],
        on_search: Callable[[], None],
        on_clear: Callable[[], None],
        on_result_selected: Callable[[int | None], None],
        on_open_radar_dialog: Callable[[], RadarData | None] | None = None,
    ) -> None:
        super().__init__(parent)

        # Store dependencies
        self.mana_icons = mana_icons
        self._on_switch_to_research = on_switch_to_research
        self._on_ensure_card_data = on_ensure_card_data
        self._open_mana_keyboard = open_mana_keyboard
        self._on_search_callback = on_search
        self._on_clear_callback = on_clear
        self._on_result_selected_callback = on_result_selected
        self._on_open_radar_dialog = on_open_radar_dialog

        # State variables
        self.inputs: dict[str, wx.TextCtrl] = {}
        self.mana_exact_cb: wx.CheckBox | None = None
        self.mv_comparator: wx.Choice | None = None
        self.mv_value: wx.TextCtrl | None = None
        self.format_checks: list[wx.CheckBox] = []
        self.color_checks: dict[str, wx.CheckBox] = {}
        self.color_mode_choice: wx.Choice | None = None
        self.results_ctrl: _SearchResultsView | None = None
        self.status_label: wx.StaticText | None = None
        self.results_cache: list[dict[str, Any]] = []
        self._search_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_search_timer, self._search_timer)

        # Radar state
        self.active_radar: RadarData | None = None
        self.radar_enabled: bool = False
        self.radar_zone: str = "both"  # "mainboard", "sideboard", or "both"

        # Build the UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the complete UI for the deck builder panel."""
        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Back button
        back_btn = wx.Button(self, label="Deck Research")
        stylize_button(back_btn)
        back_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_back_clicked())
        sizer.Add(back_btn, 0, wx.EXPAND | wx.ALL, 6)

        # Info label
        info = wx.StaticText(self, label="Deck Builder: search MTG cards by property.")
        stylize_label(info, True)
        sizer.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Search fields
        field_specs = [
            ("name", "Card Name", "e.g. Ragavan"),
            ("type", "Type Line", "Artifact Creature"),
            ("mana", "Mana Cost", "Curly braces like {1}{G} or shorthand (e.g. GGG)"),
            ("text", "Oracle Text", "Keywords or abilities"),
        ]
        for key, label_text, hint in field_specs:
            lbl = wx.StaticText(self, label=label_text)
            stylize_label(lbl, True)
            sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, 6)
            ctrl = wx.TextCtrl(self)
            stylize_textctrl(ctrl)
            ctrl.SetHint(hint)
            ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
            sizer.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
            self.inputs[key] = ctrl

            # Mana cost field gets extra controls
            if key == "mana":
                # Exact match checkbox
                match_row = wx.BoxSizer(wx.HORIZONTAL)
                match_label = wx.StaticText(self, label="Match")
                stylize_label(match_label, True)
                match_row.Add(match_label, 0, wx.RIGHT, 6)
                exact_cb = wx.CheckBox(self, label="Exact symbols")
                exact_cb.SetForegroundColour(LIGHT_TEXT)
                exact_cb.SetBackgroundColour(DARK_PANEL)
                match_row.Add(exact_cb, 0)
                self.mana_exact_cb = exact_cb
                exact_cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
                match_row.AddStretchSpacer(1)
                sizer.Add(match_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

                # Mana symbol keyboard
                keyboard_row = wx.BoxSizer(wx.HORIZONTAL)
                keyboard_row.AddStretchSpacer(1)
                for token in ["W", "U", "B", "R", "G", "C", "X"]:
                    btn = create_mana_button(self, token, self._append_mana_symbol, self.mana_icons)
                    keyboard_row.Add(btn, 0, wx.ALL, 2)
                all_btn = wx.Button(self, label="All", size=(52, 28))
                stylize_button(all_btn)
                all_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._open_mana_keyboard())
                keyboard_row.Add(all_btn, 0, wx.ALL, 2)
                keyboard_row.AddStretchSpacer(1)
                sizer.Add(
                    keyboard_row, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4
                )

        # Mana value filter
        mv_row = wx.BoxSizer(wx.HORIZONTAL)
        mv_label = wx.StaticText(self, label="Mana Value Filter")
        stylize_label(mv_label, True)
        mv_row.Add(mv_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        mv_choice = wx.Choice(self, choices=["Any", "<", "≤", "=", "≥", ">"])
        mv_choice.SetSelection(0)
        stylize_choice(mv_choice)
        self.mv_comparator = mv_choice
        mv_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        mv_row.Add(mv_choice, 0, wx.RIGHT, 6)
        mv_value = wx.TextCtrl(self)
        stylize_textctrl(mv_value)
        mv_value.SetHint("e.g. 3")
        self.mv_value = mv_value
        mv_value.Bind(wx.EVT_TEXT, self._on_filters_changed)
        mv_row.Add(mv_value, 1)
        sizer.Add(mv_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Format checkboxes
        formats_label = wx.StaticText(self, label="Formats")
        stylize_label(formats_label, True)
        sizer.Add(formats_label, 0, wx.LEFT | wx.RIGHT, 6)
        formats_grid = wx.FlexGridSizer(0, 2, 4, 8)
        for fmt in FORMAT_OPTIONS:
            cb = wx.CheckBox(self, label=fmt)
            cb.SetForegroundColour(LIGHT_TEXT)
            cb.SetBackgroundColour(DARK_PANEL)
            formats_grid.Add(cb, 0, wx.RIGHT, 6)
            cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
            self.format_checks.append(cb)
        sizer.Add(formats_grid, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Color identity filter
        color_label = wx.StaticText(self, label="Color Identity Filter")
        stylize_label(color_label, True)
        sizer.Add(color_label, 0, wx.LEFT | wx.RIGHT, 6)

        color_mode = wx.Choice(self, choices=["Any", "At least", "Exactly", "Not these"])
        color_mode.SetSelection(0)
        stylize_choice(color_mode)
        self.color_mode_choice = color_mode
        color_mode.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        sizer.Add(color_mode, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        colors_row = wx.BoxSizer(wx.HORIZONTAL)
        for code, label in [
            ("W", "White"),
            ("U", "Blue"),
            ("B", "Black"),
            ("R", "Red"),
            ("G", "Green"),
            ("C", "Colorless"),
        ]:
            cb = wx.CheckBox(self, label=label)
            cb.SetForegroundColour(LIGHT_TEXT)
            cb.SetBackgroundColour(DARK_PANEL)
            colors_row.Add(cb, 0, wx.RIGHT, 6)
            cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
            self.color_checks[code] = cb
        sizer.Add(colors_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Clear button
        controls = wx.BoxSizer(wx.HORIZONTAL)
        clear_btn = wx.Button(self, label="Clear Filters")
        stylize_button(clear_btn)
        clear_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_clear())
        controls.Add(clear_btn, 0, wx.RIGHT, 6)

        # Radar toggle checkbox
        self.radar_cb = wx.CheckBox(self, label="Use Radar Filter")
        self.radar_cb.SetForegroundColour(LIGHT_TEXT)
        self.radar_cb.SetBackgroundColour(DARK_PANEL)
        self.radar_cb.Bind(wx.EVT_CHECKBOX, self._on_radar_toggle)
        controls.Add(self.radar_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        # Radar zone choice
        self.radar_zone_choice = wx.Choice(self, choices=["Both", "Mainboard", "Sideboard"])
        self.radar_zone_choice.SetSelection(0)
        stylize_choice(self.radar_zone_choice)
        self.radar_zone_choice.Enable(False)
        self.radar_zone_choice.Bind(wx.EVT_CHOICE, self._on_radar_zone_changed)
        controls.Add(self.radar_zone_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        # Open Radar button
        self.open_radar_btn = wx.Button(self, label="Open Radar...")
        stylize_button(self.open_radar_btn)
        self.open_radar_btn.Bind(wx.EVT_BUTTON, self._on_open_radar)
        controls.Add(self.open_radar_btn, 0)

        controls.AddStretchSpacer(1)
        sizer.Add(controls, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Results list (virtual ListCtrl for handling large datasets)
        results = _SearchResultsView(self, style=0)
        results.InsertColumn(0, "Name", width=230)
        results.InsertColumn(1, "Mana Cost", width=120)
        results.SetBackgroundColour(DARK_ALT)
        results.SetForegroundColour(LIGHT_TEXT)
        results.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_result_item_selected)
        results.Bind(wx.EVT_LEFT_DOWN, self._on_results_left_down)
        sizer.Add(results, 1, wx.EXPAND | wx.ALL, 6)
        self.results_ctrl = results

        # Status label
        status = wx.StaticText(self, label="Results update automatically as you type.")
        status.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.status_label = status

    def _on_back_clicked(self) -> None:
        """Handle back button click."""
        self._on_switch_to_research()

    def _on_result_item_selected(self, event: wx.ListEvent) -> None:
        """Handle result list item selection."""
        if not self.results_ctrl:
            return
        idx = event.GetIndex()
        if idx == wx.NOT_FOUND:
            return
        self._on_result_selected(idx)

    def _on_results_left_down(self, event: wx.MouseEvent) -> None:
        if not self.results_ctrl:
            event.Skip()
            return
        idx, _ = self.results_ctrl.HitTest(event.GetPosition())
        if idx != wx.NOT_FOUND and self.results_ctrl.IsSelected(idx):
            self.clear_result_selection()
            self._on_result_selected(None)
            return
        event.Skip()

    def _append_mana_symbol(self, token: str) -> None:
        """Append a mana symbol to the mana cost field."""
        ctrl = self.inputs.get("mana")
        if not ctrl:
            return
        symbol = token.strip().upper()
        if not symbol:
            return
        text = symbol if symbol.startswith("{") else f"{{{symbol}}}"
        ctrl.ChangeValue(ctrl.GetValue() + text)
        ctrl.SetFocus()
        self._schedule_search()

    def get_filters(self) -> dict[str, Any]:
        """Get all current filter values."""
        filters = {key: ctrl.GetValue().strip() for key, ctrl in self.inputs.items()}
        filters["mana_exact"] = self.mana_exact_cb.IsChecked() if self.mana_exact_cb else False
        filters["mv_comparator"] = (
            self.mv_comparator.GetStringSelection() if self.mv_comparator else "Any"
        )
        mv_value_text = self.mv_value.GetValue().strip() if self.mv_value else ""
        filters["mv_value"] = mv_value_text
        filters["formats"] = [cb.GetLabel().lower() for cb in self.format_checks if cb.IsChecked()]
        filters["color_mode"] = (
            self.color_mode_choice.GetStringSelection() if self.color_mode_choice else "Any"
        )
        filters["selected_colors"] = [
            code for code, cb in self.color_checks.items() if cb.IsChecked()
        ]

        # Add radar filter if enabled
        filters["radar_enabled"] = self.radar_enabled
        if self.radar_enabled and self.active_radar:
            from services.radar_service import get_radar_service

            radar_service = get_radar_service()
            filters["radar_cards"] = radar_service.get_radar_card_names(
                self.active_radar, self.radar_zone
            )
        else:
            filters["radar_cards"] = set()

        return filters

    def clear_filters(self) -> None:
        """Clear all filter controls."""
        for ctrl in self.inputs.values():
            ctrl.ChangeValue("")
        self.results_cache = []
        if self.results_ctrl:
            self.results_ctrl.SetData([])

        if self.status_label:
            self.status_label.SetLabel("Filters cleared.")
        if self.mana_exact_cb:
            self.mana_exact_cb.SetValue(False)
        if self.mv_comparator:
            self.mv_comparator.SetSelection(0)
        if self.mv_value:
            self.mv_value.ChangeValue("")
        for cb in self.format_checks:
            cb.SetValue(False)
        if self.color_mode_choice:
            self.color_mode_choice.SetSelection(0)
        for cb in self.color_checks.values():
            cb.SetValue(False)

        # Clear radar filter
        self.radar_enabled = False
        self.active_radar = None
        if hasattr(self, "radar_cb"):
            self.radar_cb.SetValue(False)
            self.radar_zone_choice.Enable(False)
        self._schedule_search()

    def update_results(self, results: list[dict[str, Any]]) -> None:
        """Update the results list with search results."""
        self.results_cache = results
        if not self.results_ctrl:
            return
        self.results_ctrl.SetData(results)
        if self.status_label:
            count = len(results)
            self.status_label.SetLabel(f"Showing {count} card{'s' if count != 1 else ''}.")

    def get_result_at_index(self, idx: int) -> dict[str, Any] | None:
        """Get the result card data at the given index."""
        if idx < 0 or idx >= len(self.results_cache):
            return None
        return self.results_cache[idx]

    def get_selected_result(self) -> dict[str, Any] | None:
        """Return the currently selected search result, if any."""
        if not self.results_ctrl:
            return None
        selected = self.results_ctrl.GetFirstSelected()
        return self.get_result_at_index(selected) if selected != wx.NOT_FOUND else None

    def clear_result_selection(self) -> None:
        if not self.results_ctrl:
            return
        selected = self.results_ctrl.GetFirstSelected()
        if selected != wx.NOT_FOUND:
            self.results_ctrl.Select(selected, on=0)

    def _on_search(self) -> None:
        """Trigger search callback."""
        self._on_search_callback()

    def _on_filters_changed(self, event: wx.Event | None = None) -> None:
        """Handle any filter change by scheduling a search."""
        self._schedule_search()
        if event:
            event.Skip()

    def _on_clear(self) -> None:
        """Handle clear button click."""
        self._on_clear_callback()

    def _on_result_selected(self, idx: int | None) -> None:
        """Handle result list item selection."""
        self._on_result_selected_callback(idx)

    def _schedule_search(self) -> None:
        """Debounce search execution when filters change."""
        if not self._search_timer:
            return
        if self._search_timer.IsRunning():
            self._search_timer.Stop()
        self._search_timer.StartOnce(self._SEARCH_DEBOUNCE_MS)

    def _on_search_timer(self, _event: wx.TimerEvent) -> None:
        """Run the search after the debounce timer fires."""
        self._on_search()

    # ============= Radar Integration =============

    def _on_radar_toggle(self, event: wx.Event) -> None:
        """Handle radar filter checkbox toggle."""
        self.radar_enabled = self.radar_cb.IsChecked()
        self.radar_zone_choice.Enable(self.radar_enabled)

        if self.radar_enabled and not self.active_radar:
            wx.MessageBox(
                "Please open a radar using the 'Open Radar...' button.",
                "No Radar Loaded",
                wx.OK | wx.ICON_INFORMATION,
            )
            self.radar_cb.SetValue(False)
            self.radar_enabled = False
            self.radar_zone_choice.Enable(False)
        self._schedule_search()

    def _on_radar_zone_changed(self, event: wx.Event) -> None:
        """Handle radar zone selection change."""
        selection = self.radar_zone_choice.GetSelection()
        zone_map = {0: "both", 1: "mainboard", 2: "sideboard"}
        self.radar_zone = zone_map.get(selection, "both")
        self._schedule_search()

    def _on_open_radar(self, event: wx.Event) -> None:
        """Handle open radar button click."""
        if self._on_open_radar_dialog:
            radar = self._on_open_radar_dialog()
            if radar:
                self.set_active_radar(radar)

    def set_active_radar(self, radar: RadarData) -> None:
        """
        Set the active radar for filtering.

        Args:
            radar: RadarData to use for filtering
        """
        self.active_radar = radar
        self.radar_enabled = True
        self.radar_cb.SetValue(True)
        self.radar_zone_choice.Enable(True)

        if self.status_label:
            self.status_label.SetLabel(
                f"Radar active: {radar.archetype_name} "
                f"({len(radar.mainboard_cards)} MB, {len(radar.sideboard_cards)} SB cards)"
            )
        self._schedule_search()
