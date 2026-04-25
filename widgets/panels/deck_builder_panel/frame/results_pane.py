"""Results pane construction (action toolbar, virtual results list, add buttons, status label)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    BUILDER_MANA_CANVAS_WIDTH,
    BUILDER_NAME_COL_DEFAULT_WIDTH,
    DARK_ALT,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_MD,
    PADDING_SM,
    SUBDUED_TEXT,
)
from utils.stylize import stylize_button, stylize_choice
from widgets.panels.deck_builder_panel.frame.search_results_view import _SearchResultsView

if TYPE_CHECKING:
    from utils.mana_icon_factory import ManaIconFactory


class ResultsPaneBuilderMixin:
    """Builds the action controls, results list, add-to-zone buttons, and status label.

    Kept as a mixin (no ``__init__``) so :class:`DeckBuilderPanel` remains the
    single source of truth for instance-state initialization.
    """

    mana_icons: ManaIconFactory
    results_ctrl: _SearchResultsView | None
    status_label: wx.StaticText | None
    _add_main_btn: wx.Button | None
    _add_side_btn: wx.Button | None
    format_pool_cb: wx.CheckBox | None
    radar_cb: wx.CheckBox
    radar_zone_choice: wx.Choice

    def _build_action_controls(self, parent_sizer: wx.Sizer) -> None:
        controls = wx.BoxSizer(wx.HORIZONTAL)
        clear_btn = wx.Button(self, label=self._t("builder.clear_filters"))
        stylize_button(clear_btn)
        clear_btn.SetToolTip("Reset all search filters")
        clear_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_clear())
        controls.Add(clear_btn, 0, wx.RIGHT, PADDING_MD)

        self.format_pool_cb = wx.CheckBox(self, label=self._t("builder.format_pool.use_filter"))
        self.format_pool_cb.SetForegroundColour(LIGHT_TEXT)
        self.format_pool_cb.SetBackgroundColour(DARK_PANEL)
        self.format_pool_cb.SetToolTip(
            "Show only cards that appear in the selected format's local card pool"
        )
        self.format_pool_cb.Enable(False)
        self.format_pool_cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
        controls.Add(self.format_pool_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_MD)

        # Radar toggle checkbox
        self.radar_cb = wx.CheckBox(self, label=self._t("builder.radar.use_filter"))
        self.radar_cb.SetForegroundColour(LIGHT_TEXT)
        self.radar_cb.SetBackgroundColour(DARK_PANEL)
        self.radar_cb.SetToolTip("Show only cards that appear in the loaded radar archetype")
        self.radar_cb.Bind(wx.EVT_CHECKBOX, self._on_radar_toggle)
        controls.Add(self.radar_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_MD)

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
        controls.Add(self.radar_zone_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_MD)

        controls.AddStretchSpacer(1)
        parent_sizer.Add(controls, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

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
        results.SetBackgroundColour(DARK_ALT)
        results.SetForegroundColour(LIGHT_TEXT)
        results.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_result_item_selected)
        results.Bind(wx.EVT_LEFT_DOWN, self._on_results_left_down)
        results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_result_activated)
        results.Bind(wx.EVT_KEY_DOWN, self._on_result_key_down)
        parent_sizer.Add(results, 1, wx.EXPAND | wx.LEFT, PADDING_MD)
        self.results_ctrl = results

    def _build_add_zone_buttons(self, parent_sizer: wx.Sizer) -> None:
        add_btns_row = wx.BoxSizer(wx.HORIZONTAL)
        add_main_btn = wx.Button(self, label=self._t("builder.add_to_main"))
        stylize_button(add_main_btn)
        add_main_btn.SetToolTip("Add the selected card to the mainboard")
        add_main_btn.Enable(False)
        add_main_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_add_to_zone("main"))
        add_btns_row.Add(add_main_btn, 1, wx.RIGHT, PADDING_SM)
        self._add_main_btn = add_main_btn

        add_side_btn = wx.Button(self, label=self._t("builder.add_to_side"))
        stylize_button(add_side_btn)
        add_side_btn.SetToolTip("Add the selected card to the sideboard")
        add_side_btn.Enable(False)
        add_side_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_add_to_zone("side"))
        add_btns_row.Add(add_side_btn, 1)
        self._add_side_btn = add_side_btn

        parent_sizer.Add(add_btns_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)

    def _build_status_label(self, parent_sizer: wx.Sizer) -> None:
        status = wx.StaticText(self, label=self._t("builder.status.results"))
        status.SetForegroundColour(SUBDUED_TEXT)
        parent_sizer.Add(status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)
        self.status_label = status
