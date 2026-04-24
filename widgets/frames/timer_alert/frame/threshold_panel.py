"""Threshold entry widget (MM:SS input + remove button) used inside the timer alert frame."""

from __future__ import annotations

import re

import wx

from utils.constants import (
    DARK_ALT,
    DARK_BG,
    LIGHT_TEXT,
    PADDING_BASE,
    TIMER_ALERT_DEFAULT_THRESHOLD_VALUE,
    TIMER_ALERT_REMOVE_BUTTON_SIZE,
    TIMER_ALERT_THRESHOLD_INPUT_SIZE,
)

# Built-in Windows sounds (always available)
SOUND_OPTIONS = {
    "Beep": "SystemAsterisk",
    "Alert": "SystemExclamation",
    "Warning": "SystemHand",
    "Question": "SystemQuestion",
    "Default": "SystemDefault",
}


class ThresholdPanel(wx.Panel):
    """Individual threshold entry with MM:SS format."""

    def __init__(self, parent: wx.Window, on_remove: callable = None) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(DARK_BG)
        self.on_remove_callback = on_remove

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(sizer)

        # MM:SS input
        self.time_input = wx.TextCtrl(
            self, size=TIMER_ALERT_THRESHOLD_INPUT_SIZE, value=TIMER_ALERT_DEFAULT_THRESHOLD_VALUE
        )
        self._stylize_entry(self.time_input)
        sizer.Add(self.time_input, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_BASE)

        # Remove button
        self.remove_btn = wx.Button(self, label="✕", size=TIMER_ALERT_REMOVE_BUTTON_SIZE)
        self._stylize_remove_button(self.remove_btn)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove)
        sizer.Add(self.remove_btn, 0, wx.ALIGN_CENTER_VERTICAL)

    def _stylize_entry(self, entry: wx.TextCtrl) -> None:
        entry.SetBackgroundColour(DARK_ALT)
        entry.SetForegroundColour(LIGHT_TEXT)

    def _stylize_remove_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(wx.Colour(139, 35, 35))
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _on_remove(self, _event: wx.CommandEvent) -> None:
        if self.on_remove_callback:
            self.on_remove_callback(self)

    def get_seconds(self) -> int | None:
        value = self.time_input.GetValue().strip()
        match = re.match(r"^(\d+):(\d{2})$", value)
        if not match:
            return None
        minutes, seconds = match.groups()
        return int(minutes) * 60 + int(seconds)

    def set_enabled(self, enabled: bool) -> None:
        self.time_input.Enable(enabled)
        self.remove_btn.Enable(enabled)
