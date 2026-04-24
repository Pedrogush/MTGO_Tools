"""Deck research panel UI construction package.

The :class:`DeckResearchPanel` itself owns the panel state and orchestrates the
top-to-bottom layout, while each builder mixin (:mod:`filters`,
:mod:`results_section`) is responsible for constructing a specific section.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from utils.constants import DARK_PANEL
from widgets.panels.deck_research_panel.frame.filters import FiltersBuilderMixin
from widgets.panels.deck_research_panel.frame.results_section import ResultsSectionBuilderMixin
from widgets.panels.deck_research_panel.handlers import DeckResearchHandlersMixin
from widgets.panels.deck_research_panel.properties import DeckResearchPropertiesMixin


class DeckResearchPanel(
    DeckResearchHandlersMixin,
    DeckResearchPropertiesMixin,
    FiltersBuilderMixin,
    ResultsSectionBuilderMixin,
    wx.Panel,
):
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

        self._build_switch_button(sizer)
        self._build_format_archetype_row(sizer)
        self._build_event_date_row(sizer)
        self._build_placement_player_row(sizer)
        self._build_deck_results_section(sizer)


__all__ = ["DeckResearchPanel"]
