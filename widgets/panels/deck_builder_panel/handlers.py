"""Event handlers, UI populators, and public state setters for the deck builder panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from services.radar_service import RadarData
from utils.constants import BUILDER_SEARCH_DEBOUNCE_MS

if TYPE_CHECKING:
    from widgets.panels.deck_builder_panel.protocol import DeckBuilderPanelProto

    _Base = DeckBuilderPanelProto
else:
    _Base = object


class DeckBuilderPanelHandlersMixin(_Base):
    """Event callbacks, workers, public setters, and UI populators for :class:`DeckBuilderPanel`."""

    def _on_back_clicked(self) -> None:
        self._on_switch_to_research()

    def _on_adv_toggle(self, _event: wx.Event) -> None:
        if self._adv_panel is None or self._adv_toggle_btn is None:
            return
        shown = self._adv_panel.IsShown()
        self._adv_panel.Show(not shown)
        self._adv_toggle_btn.SetLabel(
            self._t("builder.btn.adv_filters_hide")
            if not shown
            else self._t("builder.btn.adv_filters_show")
        )
        self._adv_panel.Layout()
        self.Layout()

    def _on_result_item_selected(self, event: wx.ListEvent) -> None:
        if not self.results_ctrl:
            return
        idx = event.GetIndex()
        if idx == wx.NOT_FOUND:
            return
        self._on_result_selected(idx)
        self._update_add_buttons()

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

    def _on_result_activated(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        self._add_result_by_index(idx)

    def _on_result_key_down(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == ord("+") and not event.ControlDown():
            if self.results_ctrl:
                selected = self.results_ctrl.GetFirstSelected()
                if selected != wx.NOT_FOUND:
                    self._add_result_by_index(selected)
                    return
        event.Skip()

    def _add_result_by_index(self, idx: int) -> None:
        card = self.get_result_at_index(idx)
        if card and self._on_add_to_active_zone:
            name = card.get("name")
            if name:
                self._on_add_to_active_zone(name)

    def _on_add_to_zone(self, zone: str) -> None:
        card = self.get_selected_result()
        if not card:
            return
        name = card.get("name")
        if not name:
            return
        if zone == "main" and self._on_add_to_main:
            self._on_add_to_main(name)
        elif zone == "side" and self._on_add_to_side:
            self._on_add_to_side(name)

    def _update_add_buttons(self) -> None:
        has_selection = self.get_selected_result() is not None
        if self._add_main_btn:
            self._add_main_btn.Enable(has_selection and bool(self._on_add_to_main))
        if self._add_side_btn:
            self._add_side_btn.Enable(has_selection and bool(self._on_add_to_side))

    def _append_mana_symbol(self, token: str) -> None:
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

    def clear_filters(self) -> None:
        for ctrl in self.inputs.values():
            ctrl.ChangeValue("")
        self.results_cache = []
        if self.results_ctrl:
            self.results_ctrl.SetData([])

        if self.status_label:
            self.status_label.SetLabel("Filters cleared.")
        if self.mana_exact_cb:
            self.mana_exact_cb.SetValue(False)
        if self.text_mode_choice:
            self.text_mode_choice.SetSelection(0)
        if self.mv_comparator:
            self.mv_comparator.SetSelection(0)
        if self.mv_value:
            self.mv_value.ChangeValue("")
        if self.format_choice:
            self.format_choice.SetSelection(0)
        if self.format_pool_cb:
            self.format_pool_cb.SetValue(False)
            self.format_pool_cb.Enable(False)
        if self.color_mode_choice:
            self.color_mode_choice.SetSelection(0)
        for cb in self.color_checks.values():
            cb.SetValue(False)

        # Clear radar filter
        self.radar_enabled = False
        self.radar_zone = "both"
        self.active_radar = None
        if hasattr(self, "radar_cb"):
            self.radar_cb.SetValue(False)
            self.radar_zone_choice.Enable(False)
            self.radar_zone_choice.SetSelection(0)
        self._schedule_search()

    def update_results(self, results: list[dict[str, Any]]) -> None:
        self.results_cache = results
        if not self.results_ctrl:
            return
        self.results_ctrl.SetData(results)
        if self.status_label:
            count = len(results)
            self.status_label.SetLabel(f"Showing {count} card{'s' if count != 1 else ''}.")

    def clear_result_selection(self) -> None:
        if not self.results_ctrl:
            return
        selected = self.results_ctrl.GetFirstSelected()
        if selected != wx.NOT_FOUND:
            self.results_ctrl.Select(selected, on=0)
        self._update_add_buttons()

    def _on_search(self) -> None:
        self._on_search_callback()

    def _on_filters_changed(self, event: wx.Event | None = None) -> None:
        self._sync_format_pool_state()
        self._schedule_search()
        if event:
            event.Skip()

    def _on_clear(self) -> None:
        self._on_clear_callback()

    def _on_result_selected(self, idx: int | None) -> None:
        self._on_result_selected_callback(idx)

    def _schedule_search(self) -> None:
        if not self._search_timer:
            return
        if self._search_timer.IsRunning():
            self._search_timer.Stop()
        self._search_timer.StartOnce(BUILDER_SEARCH_DEBOUNCE_MS)

    def _on_search_timer(self, _event: wx.TimerEvent) -> None:
        self._on_search()

    def _sync_format_pool_state(self) -> None:
        if self.format_choice is None or self.format_pool_cb is None:
            return
        has_selected_format = self.format_choice.GetSelection() > 0
        self.format_pool_cb.Enable(has_selected_format)
        if not has_selected_format and self.format_pool_cb.IsChecked():
            self.format_pool_cb.SetValue(False)

    # ============= Radar Integration =============

    def _on_radar_toggle(self, event: wx.Event) -> None:
        self.radar_enabled = self.radar_cb.IsChecked()
        self.radar_zone_choice.Enable(self.radar_enabled)

        if self.radar_enabled and not self.active_radar:
            wx.MessageBox(
                "Please open a radar using the 'Radar' button in the toolbar.",
                "No Radar Loaded",
                wx.OK | wx.ICON_INFORMATION,
            )
            self.radar_cb.SetValue(False)
            self.radar_enabled = False
            self.radar_zone_choice.Enable(False)
        self._schedule_search()

    def _on_radar_zone_changed(self, event: wx.Event) -> None:
        selection = self.radar_zone_choice.GetSelection()
        zone_map = {0: "both", 1: "mainboard", 2: "sideboard"}
        self.radar_zone = zone_map.get(selection, "both")
        self._schedule_search()

    def set_active_radar(self, radar: RadarData) -> None:
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
