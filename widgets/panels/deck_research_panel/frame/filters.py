"""Filter row builders for the deck research panel.

Builds the optional builder-switch button + info label, the format/archetype
selectors, the event-type/date row, and the placement/player-name row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import RESEARCH_VALUE_FIELD_MIN_WIDTH, SPACE_SM
from widgets.input_frame import create_text_input
from widgets.mode_switch import ModeSwitch
from widgets.panels.deck_research_panel.frame.centered_choice import _CenteredChoice
from widgets.panels.deck_research_panel.results_filter import (
    EVENT_TYPE_VALUES,
    PLACEMENT_FIELDS,
    PLACEMENT_OPERATORS,
)
from widgets.stylize import (
    stylize_choice,
    stylize_combobox,
    stylize_label,
)

if TYPE_CHECKING:
    from widgets.panels.deck_research_panel.protocol import DeckResearchPanelProto

    _Base = DeckResearchPanelProto
else:
    _Base = object


class FiltersBuilderMixin(_Base):
    """Builds the switch-button row and the three filter rows.

    Kept as a mixin (no ``__init__``) so :class:`DeckResearchPanel` remains the
    single source of truth for instance-state initialization.
    """

    # ------------------------------------------------------------------
    # Choice options: stored value vs displayed label
    # ------------------------------------------------------------------
    # A wx.Choice's items are what the user reads, and the two choices in the
    # placement row were built straight from the canonical value tuples -- so
    # phase 7's translated "Result" label sat above "Placement"/"Wins" in
    # pt-BR, and the row above it showed "All / Challenge / League / ...".
    #
    # The values cannot simply be translated in place: they are persisted in
    # deck_selector_settings.json, matched against in results_filter, and
    # crossed over the automation protocol. So the label is looked up here and
    # the *index* is the correspondence between the two lists, which is why
    # get/set go through _option_value / _select_option rather than through
    # Get/SetStringSelection.

    def _option_labels(self, values: tuple[str, ...], prefix: str) -> list[str]:
        """Translated labels for *values*, falling back to the value itself.

        The fallback is deliberate rather than defensive: the four MTGO event
        series (Challenge, League, Showcase, Last Chance) are proper nouns and
        have no catalogue entry in either locale, so they fall through to
        themselves in both.
        """
        return [
            self._labels.get(f"{prefix}{value.lower().replace(' ', '_')}", value)
            for value in values
        ]

    @staticmethod
    def _option_value(choice: wx.Choice, values: tuple[str, ...]) -> str:
        index = choice.GetSelection()
        return values[index] if 0 <= index < len(values) else values[0]

    @staticmethod
    def _select_option(choice: wx.Choice, values: tuple[str, ...], value: str) -> None:
        choice.SetSelection(values.index(value) if value in values else 0)

    def _build_switch_button(self, sizer: wx.Sizer) -> None:
        """F2: the mode switch, showing which mode this is rather than the other one.

        This was a full-width ``wx.Button`` labelled "Deck Builder" — the mode
        you were *not* in — sitting where a section heading sits. See
        :mod:`widgets.mode_switch` for what replaced it and why it reuses the
        deck workspace's segmented-toggle idiom rather than inventing a switch.
        """
        if self._on_switch_to_builder is None:
            return
        self.mode_switch = ModeSwitch(
            self,
            modes=(
                ("research", self._labels.get("mode_research", "Research")),
                ("builder", self._labels.get("mode_builder", "Builder")),
            ),
            current="research",
            on_select=lambda _value: self._on_switch_to_builder(),  # type: ignore[misc]
            tooltips={"builder": self._labels.get("switch_to_builder_tooltip", "")},
        )
        sizer.Add(self.mode_switch, 0, wx.ALL, SPACE_SM)

        info_label = wx.StaticText(
            self,
            label=self._labels.get("info", "Deck research: search MTG decks by property"),
        )
        stylize_label(info_label, subtle=True, level="body")
        sizer.Add(info_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

    def _build_format_archetype_row(self, sizer: wx.Sizer) -> None:
        format_arch_row = wx.BoxSizer(wx.HORIZONTAL)

        format_col = wx.BoxSizer(wx.VERTICAL)
        format_label = wx.StaticText(self, label=self._labels.get("format", "Format"))
        stylize_label(format_label, subtle=True, level="body")
        format_col.Add(format_label, 0)

        self.format_choice = wx.Choice(self, choices=self.format_options)
        self.format_choice.SetStringSelection(self.initial_format)
        stylize_choice(self.format_choice)
        if tip := self._labels.get("format_tooltip"):
            self.format_choice.SetToolTip(tip)
        self.format_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._on_format_changed())
        format_col.Add(self.format_choice, 0, wx.EXPAND | wx.TOP, SPACE_SM)
        format_arch_row.Add(format_col, 1, wx.EXPAND | wx.RIGHT, SPACE_SM)

        archetype_col = wx.BoxSizer(wx.VERTICAL)
        archetype_label = wx.StaticText(self, label=self._labels.get("archetype", "Archetype"))
        stylize_label(archetype_label, subtle=True, level="body")
        archetype_col.Add(archetype_label, 0)

        self.archetype_combo = wx.ComboBox(self, style=wx.CB_READONLY)
        stylize_combobox(self.archetype_combo)
        if tip := self._labels.get("archetypes_tooltip", ""):
            self.archetype_combo.SetToolTip(tip)
        self.archetype_combo.Bind(wx.EVT_COMBOBOX, lambda _evt: self._on_archetype_selected())
        archetype_col.Add(self.archetype_combo, 0, wx.EXPAND | wx.TOP, SPACE_SM)

        format_arch_row.Add(archetype_col, 1, wx.EXPAND)
        sizer.Add(format_arch_row, 0, wx.EXPAND | wx.ALL, SPACE_SM)

        self.archetype_list = self.archetype_combo
        self.archetype_dropdown = self.archetype_combo
        self.search_ctrl = self.archetype_combo

    def _build_event_date_row(self, sizer: wx.Sizer) -> None:
        event_date_labels = wx.BoxSizer(wx.HORIZONTAL)
        event_label = wx.StaticText(self, label=self._labels.get("event", "Event"))
        stylize_label(event_label, subtle=True, level="body")
        date_label = wx.StaticText(self, label=self._labels.get("date", "Date"))
        stylize_label(date_label, subtle=True, level="body")
        event_date_labels.Add(event_label, 1, wx.RIGHT, SPACE_SM)
        event_date_labels.Add(date_label, 1)
        sizer.Add(event_date_labels, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)

        event_date_row = wx.BoxSizer(wx.HORIZONTAL)
        self.event_type_choice = wx.Choice(
            self,
            choices=self._option_labels(EVENT_TYPE_VALUES, "event_type_"),
        )
        self.event_type_choice.SetSelection(0)
        stylize_choice(self.event_type_choice)
        if self._on_event_type_filter is not None:
            self.event_type_choice.Bind(
                wx.EVT_CHOICE,
                lambda _evt: self._on_event_type_filter(),  # type: ignore[misc]
            )
        event_date_row.Add(self.event_type_choice, 1, wx.EXPAND | wx.RIGHT, SPACE_SM)

        date_field = create_text_input(self, style=wx.TE_PROCESS_ENTER)
        self.date_filter = date_field.ctrl
        self.date_filter.SetHint(self._labels.get("date_hint", "YYYY-MM-DD"))
        if self._on_date_filter is not None:
            self.date_filter.Bind(wx.EVT_TEXT, lambda _evt: self._on_date_filter())  # type: ignore[misc]
        event_date_row.Add(date_field, 1, wx.EXPAND)
        sizer.Add(event_date_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

    def _build_placement_player_row(self, sizer: wx.Sizer) -> None:
        row3_labels = wx.BoxSizer(wx.HORIZONTAL)
        # Found by phase 4: this label read "Placement" while the choice under it
        # toggles between **Placement** and **Wins**, so the column heading was
        # wrong half the time and contradicted the control it labelled. The row
        # filters on a deck's *result*, of which placement and wins are the two
        # readings; the field choice says which.
        placement_label = wx.StaticText(self, label=self._labels.get("result", "Result"))
        stylize_label(placement_label, subtle=True, level="body")
        player_name_label = wx.StaticText(
            self, label=self._labels.get("player_name", "Player name")
        )
        stylize_label(player_name_label, subtle=True, level="body")
        row3_labels.Add(placement_label, 1, wx.RIGHT, SPACE_SM)
        row3_labels.Add(player_name_label, 1)
        sizer.Add(row3_labels, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)

        row3 = wx.BoxSizer(wx.HORIZONTAL)

        placement_row = wx.BoxSizer(wx.HORIZONTAL)
        self.placement_op_choice = _CenteredChoice(self, choices=list(PLACEMENT_OPERATORS))
        self.placement_op_choice.SetSelection(0)
        stylize_choice(self.placement_op_choice)
        if self._on_placement_filter is not None:
            self.placement_op_choice.Bind(
                wx.EVT_COMBOBOX,
                lambda _evt: self._on_placement_filter(),  # type: ignore[misc]
            )
        placement_row.Add(self.placement_op_choice, 0, wx.EXPAND | wx.RIGHT, SPACE_SM)

        self.placement_field_choice = _CenteredChoice(
            self, choices=self._option_labels(PLACEMENT_FIELDS, "placement_field_")
        )
        self.placement_field_choice.SetSelection(0)
        stylize_choice(self.placement_field_choice)
        if self._on_placement_filter is not None:
            self.placement_field_choice.Bind(
                wx.EVT_COMBOBOX,
                lambda _evt: self._on_placement_filter(),  # type: ignore[misc]
            )
        placement_row.Add(self.placement_field_choice, 0, wx.EXPAND | wx.RIGHT, SPACE_SM)

        # The row's three controls are what set the whole left column's minimum
        # width (see RESEARCH_VALUE_FIELD_MIN_WIDTH). Without an explicit floor
        # this field reports wxMSW's 110px wx.TextCtrl best width whatever it
        # holds, and the row is paired at equal proportion against the
        # player-name field, so wxBoxSizer doubles it into the panel's minimum.
        # It still stretches (proportion 1 below); this only says how narrow it
        # may get.
        placement_value_field = create_text_input(
            self,
            size=(RESEARCH_VALUE_FIELD_MIN_WIDTH, -1),
            style=wx.TE_PROCESS_ENTER,
        )
        self.placement_value_filter = placement_value_field.ctrl
        self.placement_value_filter.SetHint(self._labels.get("placement_hint", "value"))
        if self._on_placement_filter is not None:
            self.placement_value_filter.Bind(
                wx.EVT_TEXT,
                lambda _evt: self._on_placement_filter(),  # type: ignore[misc]
            )
        placement_row.Add(placement_value_field, 1, wx.EXPAND)

        row3.Add(placement_row, 1, wx.EXPAND | wx.RIGHT, SPACE_SM)

        player_name_field = create_text_input(self, style=wx.TE_PROCESS_ENTER)
        self.player_name_filter = player_name_field.ctrl
        self.player_name_filter.SetHint(self._labels.get("player_name_hint", "Player name..."))
        if self._on_player_name_filter is not None:
            self.player_name_filter.Bind(
                wx.EVT_TEXT,
                lambda _evt: self._on_player_name_filter(),  # type: ignore[misc]
            )
        row3.Add(player_name_field, 1, wx.EXPAND)
        sizer.Add(row3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)
