"""Event handlers and public state setters for the sideboard guide panel."""

from __future__ import annotations

from collections.abc import Callable

import wx
import wx.dataview as dv


class SideboardGuidePanelHandlersMixin:
    """Public setters, button callbacks, and view refreshers for :class:`SideboardGuidePanel`."""

    entries: list[dict[str, str]]
    exclusions: list[str]
    guide_view: dv.DataViewListCtrl
    empty_state_panel: wx.Panel
    button_row: wx.Panel
    exclusions_label: wx.StaticText
    warning_label: wx.StaticText
    pin_btn: wx.Button
    on_add_entry: Callable[[], None]
    on_edit_entry: Callable[[], None]
    on_remove_entry: Callable[[], None]
    on_edit_exclusions: Callable[[], None]
    on_export_csv: Callable[[], None]
    on_import_csv: Callable[[], None]
    on_pin_guide: Callable[[], None] | None
    on_edit_flex_slots: Callable[[], None] | None

    # ============= Public API =============

    def set_entries(
        self, entries: list[dict[str, str]], exclusions: list[str] | None = None
    ) -> None:
        self.entries = entries
        self.exclusions = exclusions or []
        self._refresh_view()

    def clear(self) -> None:
        self.entries = []
        self.exclusions = []
        self._refresh_view()

    def set_warning(self, message: str) -> None:
        if message:
            self.warning_label.SetLabel(message)
            self.warning_label.Show()
        else:
            self.warning_label.Hide()
        self.Layout()

    # ============= Private Methods =============

    def _refresh_view(self) -> None:
        self.guide_view.DeleteAllItems()

        # Add entries (skip excluded archetypes)
        visible_entries = 0
        for entry in self.entries:
            if entry.get("archetype") in self.exclusions:
                continue
            self.guide_view.AppendItem(
                [
                    entry.get("archetype", ""),
                    self._format_card_list(entry.get("play_out", {})),
                    self._format_card_list(entry.get("play_in", {})),
                    self._format_card_list(entry.get("draw_out", {})),
                    self._format_card_list(entry.get("draw_in", {})),
                    entry.get("notes", ""),
                ]
            )
            visible_entries += 1

        # Toggle empty state visibility
        is_empty = visible_entries == 0
        self.guide_view.Show(not is_empty)
        self.empty_state_panel.Show(is_empty)
        self.button_row.Show(not is_empty)
        self.Layout()

        # Update exclusions label
        text = ", ".join(self.exclusions) if self.exclusions else "\u2014"
        self.exclusions_label.SetLabel(f"{self._t('guide.label.exclusions')}: {text}")

    def _on_add_clicked(self, _event: wx.Event) -> None:
        self.on_add_entry()

    def _on_edit_clicked(self, _event: wx.Event) -> None:
        self.on_edit_entry()

    def _on_remove_clicked(self, _event: wx.Event) -> None:
        self.on_remove_entry()

    def _on_exclusions_clicked(self, _event: wx.Event) -> None:
        self.on_edit_exclusions()

    def _on_export_clicked(self, _event: wx.Event) -> None:
        self.on_export_csv()

    def _on_import_clicked(self, _event: wx.Event) -> None:
        self.on_import_csv()

    def _on_pin_clicked(self, _event: wx.Event) -> None:
        if self.on_pin_guide:
            self.on_pin_guide()

    def _on_flex_slots_clicked(self, _event: wx.Event) -> None:
        if self.on_edit_flex_slots:
            self.on_edit_flex_slots()

    def set_pinned(self, pinned: bool) -> None:
        if pinned:
            self.pin_btn.SetLabel(self._t("guide.btn.pinned"))
        else:
            self.pin_btn.SetLabel(self._t("guide.btn.pin"))
