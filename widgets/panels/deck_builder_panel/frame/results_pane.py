"""Results pane construction (action toolbar, virtual results list, add buttons, status label)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    BUILDER_MANA_CANVAS_WIDTH,
    BUILDER_NAME_COL_DEFAULT_WIDTH,
    SPACE_SM,
    SPACE_XS,
    SUBDUED_TEXT,
)
from widgets.checkbox import DarkCheckBox
from widgets.empty_state import EmptyState
from widgets.panels.deck_builder_panel.frame.search_results_view import _SearchResultsView
from widgets.stylize import stylize_button, stylize_checkbox, stylize_choice, stylize_list_ctrl

if TYPE_CHECKING:
    from widgets.panels.deck_builder_panel.protocol import DeckBuilderPanelProto

    _Base = DeckBuilderPanelProto
else:
    _Base = object


class ResultsPaneBuilderMixin(_Base):
    """Builds the action controls, results list, add-to-zone buttons, and status label.

    Kept as a mixin (no ``__init__``) so :class:`DeckBuilderPanel` remains the
    single source of truth for instance-state initialization.
    """

    def _build_action_controls(self, parent_sizer: wx.Sizer) -> None:
        controls = wx.BoxSizer(wx.HORIZONTAL)
        clear_btn = wx.Button(self, label=self._t("builder.clear_filters"))
        stylize_button(clear_btn, kind="secondary")
        clear_btn.SetToolTip("Reset all search filters")
        clear_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_clear())
        controls.Add(clear_btn, 0, wx.RIGHT, SPACE_SM)
        # C5: hidden while the empty state is up, because the empty state's own
        # CTA *is* Clear Filters. Two identical buttons 20px apart is the same
        # defect Deck Notes had; the rest of this row stays, since those are the
        # filters the user needs in order to widen the search by hand.
        self._clear_filters_btn = clear_btn

        self.format_pool_cb = DarkCheckBox(self, label=self._t("builder.format_pool.use_filter"))
        stylize_checkbox(self.format_pool_cb, surface="panel")
        self.format_pool_cb.SetToolTip(
            "Show only cards that appear in the selected format's local card pool"
        )
        self.format_pool_cb.Enable(False)
        self.format_pool_cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
        controls.Add(self.format_pool_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        # Radar toggle checkbox
        self.radar_cb = DarkCheckBox(self, label=self._t("builder.radar.use_filter"))
        stylize_checkbox(self.radar_cb, surface="panel")
        self.radar_cb.SetToolTip("Show only cards that appear in the loaded radar archetype")
        self.radar_cb.Bind(wx.EVT_CHECKBOX, self._on_radar_toggle)
        controls.Add(self.radar_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        # Radar zone choice
        self.radar_zone_choice = wx.Choice(
            self,
            choices=[
                self._t("app.choice.source.both"),
                self._t("tabs.mainboard"),
                self._t("tabs.sideboard"),
            ],
        )
        self.radar_zone_choice.SetSelection(0)
        stylize_choice(self.radar_zone_choice)
        self.radar_zone_choice.SetToolTip("Limit radar filtering to mainboard, sideboard, or both")
        self.radar_zone_choice.Enable(False)
        self.radar_zone_choice.Bind(wx.EVT_CHOICE, self._on_radar_zone_changed)
        controls.Add(self.radar_zone_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        controls.AddStretchSpacer(1)
        parent_sizer.Add(controls, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

    def _build_results_list(self, parent_sizer: wx.Sizer) -> None:
        # Results list (virtual ListCtrl for handling large datasets)
        results = _SearchResultsView(self, style=0, mana_icons=self.mana_icons)
        # Column 0 is a hidden 0-width dummy that absorbs the Windows IMAGE_LIST_SMALL
        # indent (equal to the image-list item width).  Columns 1+ are sub-item columns
        # and are never indented by LVSIL_SMALL, so the Name cell is unindented.
        results.InsertColumn(0, "", width=0)
        results.InsertColumn(
            1,
            self._t("builder.col.name"),
            format=wx.LIST_FORMAT_LEFT,
            width=BUILDER_NAME_COL_DEFAULT_WIDTH,
        )
        results.InsertColumn(2, self._t("builder.col.mana_cost"), width=BUILDER_MANA_CANVAS_WIDTH)
        stylize_list_ctrl(results)
        results.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_result_item_selected)
        results.Bind(wx.EVT_LEFT_DOWN, self._on_results_left_down)
        results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_result_activated)
        results.Bind(wx.EVT_KEY_DOWN, self._on_result_key_down)
        # The virtual list emits cache hints for each row range it is about to
        # draw — the scroll signal driving image prefetch (issue #951).
        results.Bind(wx.EVT_LIST_CACHE_HINT, self._on_results_cache_hint)
        parent_sizer.Add(results, 1, wx.EXPAND | wx.LEFT, SPACE_SM)
        self.results_ctrl = results

        # C5: the builder had no empty state at all -- zero matches left a bare
        # ListCtrl with two column headers over ~200px of nothing, and the only
        # signal was "Showing 0 cards." in 10pt subdued text below it. The list
        # and this swap places; see handlers.update_results.
        self.results_empty_state = EmptyState(
            self,
            message=self._t("builder.empty.no_results"),
            hint=self._t("builder.empty.no_results.hint"),
            cta_label=self._t("builder.clear_filters"),
            on_cta=lambda _evt: self.clear_filters(),
            surface="alt",
        )
        self.results_empty_state.Hide()
        parent_sizer.Add(self.results_empty_state, 1, wx.EXPAND | wx.LEFT, SPACE_SM)

    def _build_add_zone_buttons(self, parent_sizer: wx.Sizer) -> None:
        add_btns_row = wx.BoxSizer(wx.HORIZONTAL)
        add_main_btn = wx.Button(self, label=self._t("builder.add_to_main"))
        # The builder's reason to exist: the one primary action on this surface.
        stylize_button(add_main_btn, kind="primary")
        add_main_btn.SetToolTip(
            "Add the selected card to the mainboard "
            "(shortcut: press 1-4 in the results list to add that many copies)"
        )
        add_main_btn.Enable(False)
        add_main_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_add_to_zone("main"))
        add_btns_row.Add(add_main_btn, 1, wx.RIGHT, SPACE_XS)
        self._add_main_btn = add_main_btn

        add_side_btn = wx.Button(self, label=self._t("builder.add_to_side"))
        stylize_button(add_side_btn, kind="secondary")
        add_side_btn.SetToolTip(
            "Add the selected card to the sideboard "
            "(shortcut: press Shift+1-4 in the results list to add that many copies)"
        )
        add_side_btn.Enable(False)
        add_side_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_add_to_zone("side"))
        add_btns_row.Add(add_side_btn, 1)
        self._add_side_btn = add_side_btn

        parent_sizer.Add(add_btns_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)

    def _build_status_label(self, parent_sizer: wx.Sizer) -> None:
        status = wx.StaticText(self, label=self._t("builder.status.results"))
        status.SetForegroundColour(SUBDUED_TEXT)
        parent_sizer.Add(status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)
        self.status_label = status
