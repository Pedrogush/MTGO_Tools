"""Navigation, control-sync, and busy-state handlers for the metagame analysis viewer."""

from __future__ import annotations

import wx
from loguru import logger


class MetagameNavigationMixin:
    """Toolbar callbacks and control-state helpers for :class:`MetagameAnalysisFrame`."""

    current_format: str
    current_days: int
    base_day_offset: int
    min_days: int
    max_days: int
    max_day_offset: int
    format_choice: wx.Choice
    refresh_button: wx.Button
    days_prev_button: wx.Button
    days_next_button: wx.Button
    offset_prev_button: wx.Button
    offset_next_button: wx.Button
    days_value_box: wx.Panel
    days_value_label: wx.StaticText
    offset_value_box: wx.Panel
    offset_value_label: wx.StaticText
    status_label: wx.StaticText

    def on_format_change(self, event: wx.CommandEvent) -> None:
        self.current_format = self.format_choice.GetStringSelection().lower()
        self.refresh_data()

    def on_days_decrease(self, event: wx.CommandEvent) -> None:
        if self.current_days <= self.min_days:
            return
        self.current_days -= 1
        self._sync_navigation_controls()
        self.update_visualization()

    def on_days_increase(self, event: wx.CommandEvent) -> None:
        if self.current_days >= self.max_days:
            return
        self.current_days += 1
        self._sync_navigation_controls()
        self.update_visualization()

    def on_offset_decrease(self, event: wx.CommandEvent) -> None:
        if self.base_day_offset <= 0:
            return
        self.base_day_offset -= 1
        self._sync_navigation_controls()
        self.update_visualization()

    def on_offset_increase(self, event: wx.CommandEvent) -> None:
        if self.base_day_offset >= self.max_day_offset:
            return
        self.base_day_offset += 1
        self._sync_navigation_controls()
        self.update_visualization()

    def _sync_navigation_controls(self) -> None:
        self.days_value_label.SetLabel(str(self.current_days))
        self.offset_value_label.SetLabel(str(self.base_day_offset))
        self.days_value_box.Layout()
        self.offset_value_box.Layout()
        self.days_prev_button.Enable(self.current_days > self.min_days)
        self.days_next_button.Enable(self.current_days < self.max_days)
        self.offset_prev_button.Enable(self.base_day_offset > 0)
        self.offset_next_button.Enable(self.base_day_offset < self.max_day_offset)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        logger.debug(f"_set_busy called: busy={busy}, message={message}")
        self.refresh_button.Enable(not busy)
        self.days_prev_button.Enable((not busy) and self.current_days > self.min_days)
        self.days_next_button.Enable((not busy) and self.current_days < self.max_days)
        self.offset_prev_button.Enable((not busy) and self.base_day_offset > 0)
        self.offset_next_button.Enable((not busy) and self.base_day_offset < self.max_day_offset)

        if message:
            self.status_label.SetLabel(message)
        elif busy:
            self.status_label.SetLabel(self._t("research.loading_archetypes"))
        else:
            self.status_label.SetLabel(self._t("app.status.ready"))

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()
