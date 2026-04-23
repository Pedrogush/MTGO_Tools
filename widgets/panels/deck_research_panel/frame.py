"""UI construction for the deck research panel."""

from __future__ import annotations

from collections.abc import Callable

import wx
import wx.adv
import wx.html

from utils.constants import (
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_MD,
)
from utils.deck_results_filter import PLACEMENT_FIELDS, PLACEMENT_OPERATORS
from utils.stylize import (
    stylize_button,
    stylize_choice,
    stylize_label,
    stylize_textctrl,
)
from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.lists.deck_results_list import DeckResultsList
from widgets.panels.deck_research_panel.handlers import DeckResearchHandlersMixin
from widgets.panels.deck_research_panel.properties import DeckResearchPropertiesMixin


class _CenteredChoice(wx.adv.OwnerDrawnComboBox):
    """Read-only combo box that center-aligns text and fits its width to its widest item."""

    _BUTTON_AND_PADDING_PX = 36

    def __init__(self, parent: wx.Window, choices: list[str]) -> None:
        super().__init__(parent, choices=choices, style=wx.CB_READONLY)
        self._fit_to_widest_choice(choices)

    def _fit_to_widest_choice(self, choices: list[str]) -> None:
        if not choices:
            return
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        max_text_w = max(dc.GetTextExtent(c)[0] for c in choices)
        width = max_text_w + self._BUTTON_AND_PADDING_PX
        self.SetMinSize(wx.Size(width, -1))
        self.SetInitialSize(wx.Size(width, -1))

    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, item: int, flags: int) -> None:  # noqa: N802
        if item == wx.NOT_FOUND:
            return
        text = self.GetString(item)
        tw, th = dc.GetTextExtent(text)
        x = rect.x + (rect.width - tw) // 2
        y = rect.y + (rect.height - th) // 2
        dc.DrawText(text, x, y)


class DeckResearchPanel(DeckResearchHandlersMixin, DeckResearchPropertiesMixin, wx.Panel):
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
        on_placement_filter: Callable[[], None] | None = None,
        on_player_name_filter: Callable[[], None] | None = None,
        on_date_filter: Callable[[], None] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)

        self._on_format_changed = on_format_changed
        self._on_archetype_selected = on_archetype_selected
        self._on_switch_to_builder = on_switch_to_builder
        self._on_deck_selected = on_deck_selected
        self._on_copy = on_copy
        self._on_save = on_save
        self._on_daily_average = on_daily_average
        self._on_load = on_load
        self._on_event_type_filter = on_event_type_filter
        self._on_placement_filter = on_placement_filter
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

        format_arch_row = wx.BoxSizer(wx.HORIZONTAL)

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

        archetype_col = wx.BoxSizer(wx.VERTICAL)
        archetype_label = wx.StaticText(self, label=self._labels.get("archetype", "Archetype"))
        stylize_label(archetype_label, subtle=True)
        archetype_col.Add(archetype_label, 0)

        self.archetype_combo = wx.ComboBox(self, style=wx.CB_READONLY)
        if tip := self._labels.get("archetypes_tooltip", ""):
            self.archetype_combo.SetToolTip(tip)
        self.archetype_combo.Bind(wx.EVT_COMBOBOX, lambda _evt: self._on_archetype_selected())
        archetype_col.Add(self.archetype_combo, 0, wx.EXPAND | wx.TOP, PADDING_MD)

        format_arch_row.Add(archetype_col, 1, wx.EXPAND)
        sizer.Add(format_arch_row, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        self.archetype_list = self.archetype_combo
        self.archetype_dropdown = self.archetype_combo
        self.search_ctrl = self.archetype_combo

        event_date_labels = wx.BoxSizer(wx.HORIZONTAL)
        event_label = wx.StaticText(self, label=self._labels.get("event", "Event"))
        stylize_label(event_label, subtle=True)
        date_label = wx.StaticText(self, label=self._labels.get("date", "Date"))
        stylize_label(date_label, subtle=True)
        event_date_labels.Add(event_label, 1, wx.RIGHT, PADDING_MD)
        event_date_labels.Add(date_label, 1)
        sizer.Add(event_date_labels, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)

        event_date_row = wx.BoxSizer(wx.HORIZONTAL)
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
        event_date_row.Add(self.event_type_choice, 1, wx.EXPAND | wx.RIGHT, PADDING_MD)

        self.date_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.date_filter.SetHint(self._labels.get("date_hint", "YYYY-MM-DD"))
        stylize_textctrl(self.date_filter)
        if self._on_date_filter is not None:
            self.date_filter.Bind(wx.EVT_TEXT, lambda _evt: self._on_date_filter())  # type: ignore[misc]
        event_date_row.Add(self.date_filter, 1, wx.EXPAND)
        sizer.Add(event_date_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        row3_labels = wx.BoxSizer(wx.HORIZONTAL)
        placement_label = wx.StaticText(self, label=self._labels.get("placement", "Placement"))
        stylize_label(placement_label, subtle=True)
        player_name_label = wx.StaticText(
            self, label=self._labels.get("player_name", "Player name")
        )
        stylize_label(player_name_label, subtle=True)
        row3_labels.Add(placement_label, 1, wx.RIGHT, PADDING_MD)
        row3_labels.Add(player_name_label, 1)
        sizer.Add(row3_labels, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)

        row3 = wx.BoxSizer(wx.HORIZONTAL)

        placement_row = wx.BoxSizer(wx.HORIZONTAL)
        self.placement_op_choice = _CenteredChoice(self, choices=list(PLACEMENT_OPERATORS))
        self.placement_op_choice.SetSelection(0)
        stylize_choice(self.placement_op_choice)
        if self._on_placement_filter is not None:
            self.placement_op_choice.Bind(
                wx.EVT_COMBOBOX, lambda _evt: self._on_placement_filter()  # type: ignore[misc]
            )
        placement_row.Add(self.placement_op_choice, 0, wx.EXPAND | wx.RIGHT, PADDING_MD)

        self.placement_field_choice = _CenteredChoice(self, choices=list(PLACEMENT_FIELDS))
        self.placement_field_choice.SetSelection(0)
        stylize_choice(self.placement_field_choice)
        if self._on_placement_filter is not None:
            self.placement_field_choice.Bind(
                wx.EVT_COMBOBOX, lambda _evt: self._on_placement_filter()  # type: ignore[misc]
            )
        placement_row.Add(self.placement_field_choice, 0, wx.EXPAND | wx.RIGHT, PADDING_MD)

        self.placement_value_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.placement_value_filter.SetHint(self._labels.get("placement_hint", "value"))
        stylize_textctrl(self.placement_value_filter)
        if self._on_placement_filter is not None:
            self.placement_value_filter.Bind(
                wx.EVT_TEXT, lambda _evt: self._on_placement_filter()  # type: ignore[misc]
            )
        placement_row.Add(self.placement_value_filter, 1, wx.EXPAND)

        row3.Add(placement_row, 1, wx.EXPAND | wx.RIGHT, PADDING_MD)

        self.player_name_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.player_name_filter.SetHint(self._labels.get("player_name_hint", "Player name..."))
        stylize_textctrl(self.player_name_filter)
        if self._on_player_name_filter is not None:
            self.player_name_filter.Bind(
                wx.EVT_TEXT, lambda _evt: self._on_player_name_filter()  # type: ignore[misc]
            )
        row3.Add(self.player_name_filter, 1, wx.EXPAND)
        sizer.Add(row3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

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

        summary_box = wx.StaticBox(
            self, label=self._labels.get("archetype_summary", "Archetype Summary")
        )
        summary_box.SetForegroundColour(LIGHT_TEXT)
        summary_box.SetBackgroundColour(DARK_PANEL)
        summary_sizer = wx.StaticBoxSizer(summary_box, wx.VERTICAL)

        self.summary_text = wx.html.HtmlWindow(
            summary_box,
            style=wx.html.HW_SCROLLBAR_NEVER | wx.NO_BORDER,
        )
        self.summary_text.SetBackgroundColour(wx.Colour(34, 39, 46))
        self.summary_text.SetBorders(-1)
        self.summary_text.SetMinSize((-1, 62))
        summary_sizer.Add(self.summary_text, 1, wx.EXPAND)
        sizer.Add(summary_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        results_box = wx.StaticBox(self, label=self._labels.get("deck_results", "Deck Results"))
        results_box.SetForegroundColour(LIGHT_TEXT)
        results_box.SetBackgroundColour(DARK_PANEL)
        results_sizer = wx.StaticBoxSizer(results_box, wx.VERTICAL)

        self.deck_list = DeckResultsList(results_box)
        if self._on_deck_selected is not None:
            self.deck_list.Bind(wx.EVT_LISTBOX, lambda _evt: self._on_deck_selected())  # type: ignore[misc]
        results_sizer.Add(self.deck_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)
        sizer.Add(results_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        self.daily_average_button = self.deck_action_buttons.daily_average_button
        self.copy_button = self.deck_action_buttons.copy_button
        self.load_button = self.deck_action_buttons.load_button
        self.save_button = self.deck_action_buttons.save_button
