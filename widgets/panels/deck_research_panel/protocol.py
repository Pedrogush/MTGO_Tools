"""Shared ``self`` contract that the :class:`DeckResearchPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import wx
import wx.html

from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.lists.deck_results_list import DeckResultsList
from widgets.panels.deck_research_panel.frame.centered_choice import _CenteredChoice


class DeckResearchPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckResearchPanel``."""

    initial_format: str
    format_options: list[str]
    _labels: dict[str, str]

    _on_format_changed: Callable[[], None]
    _on_archetype_selected: Callable[[], None]
    _on_switch_to_builder: Callable[[], None] | None
    _on_deck_selected: Callable[[], None] | None
    _on_copy: Callable[[], None] | None
    _on_save: Callable[[], None] | None
    _on_daily_average: Callable[[], None] | None
    _on_load: Callable[[], None] | None
    _on_event_type_filter: Callable[[], None] | None
    _on_placement_filter: Callable[[], None] | None
    _on_player_name_filter: Callable[[], None] | None
    _on_date_filter: Callable[[], None] | None

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

    deck_action_buttons: DeckActionButtons
    summary_text: wx.html.HtmlWindow
    deck_list: DeckResultsList
    daily_average_button: wx.Button
    copy_button: wx.Button
    load_button: wx.Button
    save_button: wx.Button
