"""Public enable/disable setters for the deck action button panel."""

from __future__ import annotations

import wx


class DeckActionButtonsPropertiesMixin:
    """Enable/disable accessors for :class:`DeckActionButtons`."""

    load_button: wx.Button
    save_button: wx.Button
    daily_average_button: wx.Button
    copy_button: wx.Button

    def enable_daily_average(self, enable: bool = True) -> None:
        if enable:
            self.daily_average_button.Enable()
        else:
            self.daily_average_button.Disable()

    def enable_copy(self, enable: bool = True) -> None:
        if enable:
            self.copy_button.Enable()
        else:
            self.copy_button.Disable()

    def enable_save(self, enable: bool = True) -> None:
        if enable:
            self.save_button.Enable()
        else:
            self.save_button.Disable()

    def enable_deck_actions(self, enable: bool = True) -> None:
        self.enable_copy(enable)
        self.enable_save(enable)

    def enable_load(self, enable: bool = True) -> None:
        if enable:
            self.load_button.Enable()
        else:
            self.load_button.Disable()
