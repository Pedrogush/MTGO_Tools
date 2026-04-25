"""Filter row builders for the deck research panel.

Builds the optional builder-switch button + info label, the format/archetype
selectors, the event-type/date row, and the placement/player-name row.
"""

from __future__ import annotations

import wx

from utils.constants import PADDING_MD
from utils.deck_results_filter import PLACEMENT_FIELDS, PLACEMENT_OPERATORS
from utils.stylize import stylize_button, stylize_choice, stylize_label, stylize_textctrl
from widgets.panels.deck_research_panel.frame.centered_choice import _CenteredChoice


class FiltersBuilderMixin:
    """Builds the switch-button row and the three filter rows.

    Kept as a mixin (no ``__init__``) so :class:`DeckResearchPanel` remains the
    single source of truth for instance-state initialization.
    """

    format_choice: wx.Choice
    archetype_combo: wx.ComboBox
    archetype_list: wx.ComboBox
    archetype_dropdown: wx.ComboBox
    search_ctrl: wx.ComboBox
    event_type_choice: wx.Choice
    date_filter: wx.TextCtrl
    placement_op_choice: _CenteredChoice
    placement_field_choice: _CenteredChoice
    placement_value_filter: wx.TextCtrl
    player_name_filter: wx.TextCtrl

    def _build_switch_button(self, sizer: wx.Sizer) -> None:
        if self._on_switch_to_builder is None:
            return
        builder_btn = wx.Button(self, label=self._labels.get("switch_to_builder", "Deck Builder"))
        stylize_button(builder_btn)
        builder_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_switch_to_builder())  # type: ignore[misc]
        sizer.Add(builder_btn, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        info_label = wx.StaticText(
            self,
            label=self._labels.get("info", "Deck research: search MTG decks by property"),
        )
        stylize_label(info_label, subtle=True)
        sizer.Add(info_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

    def _build_format_archetype_row(self, sizer: wx.Sizer) -> None:
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

    def _build_event_date_row(self, sizer: wx.Sizer) -> None:
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

    def _build_placement_player_row(self, sizer: wx.Sizer) -> None:
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
