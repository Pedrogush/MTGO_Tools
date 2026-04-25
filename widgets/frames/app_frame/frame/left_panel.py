"""Left simplebook construction (research/builder panels) for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_PANEL, FORMAT_OPTIONS
from widgets.panels.deck_builder_panel import DeckBuilderPanel
from widgets.panels.deck_research_panel import DeckResearchPanel

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class LeftPanelBuilderMixin(_Base):
    """Builds the left ``wx.Simplebook`` containing the research and builder panels.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    def _build_left_panel(self, parent: wx.Window) -> wx.Panel:
        left_panel = wx.Panel(parent)
        left_panel.SetBackgroundColour(DARK_PANEL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        left_panel.SetSizer(left_sizer)

        self.left_stack = wx.Simplebook(left_panel)
        self.left_stack.SetBackgroundColour(DARK_PANEL)
        left_sizer.Add(self.left_stack, 1, wx.EXPAND)

        self.research_panel = DeckResearchPanel(
            parent=self.left_stack,
            format_options=FORMAT_OPTIONS,
            initial_format=self.controller.current_format,
            on_format_changed=self.on_format_changed,
            on_archetype_filter=self.on_archetype_filter,
            on_archetype_selected=self.on_archetype_selected,
            on_reload_archetypes=lambda: self.fetch_archetypes(force=True),
            on_switch_to_builder=lambda: self._show_left_panel("builder"),
            on_deck_selected=self.on_deck_selected,
            on_copy=lambda: self.on_copy_clicked(None),
            on_save=lambda: self.on_save_clicked(None),
            on_daily_average=lambda: self.on_daily_average_clicked(None),
            on_load=self.on_load_deck_clicked,
            on_event_type_filter=self.on_event_type_filter_changed,
            on_placement_filter=self.on_placement_filter_changed,
            on_player_name_filter=self.on_player_name_filter_changed,
            on_date_filter=self.on_date_filter_changed,
            labels={
                "format": self._t("research.format"),
                "archetype": self._t("research.archetype"),
                "event": self._t("research.event"),
                "player_name": self._t("research.player_name"),
                "placement": self._t("research.placement"),
                "placement_hint": self._t("research.placement_hint"),
                "date": self._t("research.date"),
                "info": self._t("research.info"),
                "search_hint": self._t("research.search_hint"),
                "loading_archetypes": self._t("research.loading_archetypes"),
                "failed_archetypes": self._t("research.failed_archetypes"),
                "no_archetypes": self._t("research.no_archetypes"),
                "switch_to_builder": self._t("research.switch_to_builder"),
                "format_tooltip": self._t("research.tooltip.format"),
                "search_tooltip": self._t("research.tooltip.search"),
                "archetypes_tooltip": self._t("research.tooltip.archetypes"),
                "daily_average": self._t("deck_actions.daily_average"),
                "copy": self._t("deck_actions.copy"),
                "load_deck": self._t("deck_actions.load_deck"),
                "save_deck": self._t("deck_actions.save_deck"),
                "daily_average_tooltip": self._t("deck_actions.tooltip.daily_average"),
                "copy_tooltip": self._t("deck_actions.tooltip.copy"),
                "load_deck_tooltip": self._t("deck_actions.tooltip.load_deck"),
                "save_deck_tooltip": self._t("deck_actions.tooltip.save_deck"),
            },
        )
        self.left_stack.AddPage(self.research_panel, self._t("app.label.left_panel.research"))

        self.builder_panel = DeckBuilderPanel(
            parent=self.left_stack,
            mana_icons=self.mana_icons,
            on_switch_to_research=lambda: self._show_left_panel("research"),
            on_ensure_card_data=self.ensure_card_data_loaded,
            open_mana_keyboard=self._open_full_mana_keyboard,
            on_search=self._on_builder_search,
            on_clear=self._on_builder_clear,
            on_result_selected=self._on_builder_result_selected,
            on_add_to_main=lambda name: self._handle_zone_delta("main", name, 1),
            on_add_to_side=lambda name: self._handle_zone_delta("side", name, 1),
            on_add_to_active_zone=self._add_search_card_to_active_zone,
            locale=self.locale,
        )
        self.left_stack.AddPage(self.builder_panel, self._t("app.label.left_panel.builder"))
        self._show_left_panel(self.left_mode, force=True)

        return left_panel
