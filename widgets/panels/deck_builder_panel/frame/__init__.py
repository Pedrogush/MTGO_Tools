"""Deck builder panel UI construction package.

The :class:`DeckBuilderPanel` itself owns the panel state and orchestrates the
top-to-bottom layout, while each builder mixin
(:mod:`basic_filters`, :mod:`advanced_filters`, :mod:`results_pane`) is
responsible for constructing a specific section of the UI.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from services.radar_service import RadarData
from utils.constants import DARK_PANEL
from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.deck_builder_panel.frame.advanced_filters import AdvancedFiltersBuilderMixin
from widgets.panels.deck_builder_panel.frame.basic_filters import BasicFiltersBuilderMixin
from widgets.panels.deck_builder_panel.frame.results_pane import ResultsPaneBuilderMixin
from widgets.panels.deck_builder_panel.frame.search_results_view import _SearchResultsView
from widgets.panels.deck_builder_panel.handlers import DeckBuilderPanelHandlersMixin
from widgets.panels.deck_builder_panel.properties import DeckBuilderPanelPropertiesMixin


class DeckBuilderPanel(
    DeckBuilderPanelHandlersMixin,
    DeckBuilderPanelPropertiesMixin,
    BasicFiltersBuilderMixin,
    AdvancedFiltersBuilderMixin,
    ResultsPaneBuilderMixin,
    wx.Panel,
):
    """Panel for searching and filtering MTG cards by various properties."""

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
        on_add_to_main: Callable[[str], None] | None = None,
        on_add_to_side: Callable[[str], None] | None = None,
        on_add_to_active_zone: Callable[[str], None] | None = None,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent)

        self._locale = locale

        # Store dependencies
        self.mana_icons = mana_icons
        self._on_switch_to_research = on_switch_to_research
        self._on_ensure_card_data = on_ensure_card_data
        self._open_mana_keyboard = open_mana_keyboard
        self._on_search_callback = on_search
        self._on_clear_callback = on_clear
        self._on_result_selected_callback = on_result_selected
        self._on_add_to_main = on_add_to_main
        self._on_add_to_side = on_add_to_side
        self._on_add_to_active_zone = on_add_to_active_zone

        # State variables
        self.inputs: dict[str, wx.TextCtrl] = {}
        self.mana_exact_cb: wx.CheckBox | None = None
        self.mv_comparator: wx.Choice | None = None
        self.mv_value: wx.TextCtrl | None = None
        self.format_choice: wx.Choice | None = None
        self.color_checks: dict[str, wx.ToggleButton] = {}
        self.color_mode_choice: wx.Choice | None = None
        self.text_mode_choice: wx.Choice | None = None
        self.results_ctrl: _SearchResultsView | None = None
        self.status_label: wx.StaticText | None = None
        self._add_main_btn: wx.Button | None = None
        self._add_side_btn: wx.Button | None = None
        self._adv_panel: wx.Panel | None = None
        self._adv_toggle_btn: wx.Button | None = None
        self.results_cache: list[dict[str, Any]] = []
        self._search_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_search_timer, self._search_timer)

        # Radar state
        self.active_radar: RadarData | None = None
        self.radar_enabled: bool = False
        self.radar_zone: str = "both"  # "mainboard", "sideboard", or "both"
        self.format_pool_cb: wx.CheckBox | None = None

        # Build the UI
        self._build_ui()

    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self._build_header(sizer)
        self._build_basic_filters(sizer)
        self._build_advanced_filters(sizer)
        self._build_action_controls(sizer)
        self._build_results_list(sizer)
        self._build_add_zone_buttons(sizer)
        self._build_status_label(sizer)


__all__ = ["DeckBuilderPanel"]
