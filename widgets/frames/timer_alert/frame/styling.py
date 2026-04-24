"""Small wx styling helpers shared by the timer alert frame's section builders."""

from __future__ import annotations

import wx

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT


class StylingMixin:
    """Reusable wx widget styling helpers.

    Kept as a mixin (no ``__init__``) so :class:`TimerAlertFrame` remains the
    single source of truth for instance-state initialization.
    """

    def _static_text(self, parent: wx.Window, label: str) -> wx.StaticText:
        text = wx.StaticText(parent, label=label)
        text.SetForegroundColour(LIGHT_TEXT)
        text.SetBackgroundColour(DARK_BG)
        return text

    def _stylize_choice(self, choice: wx.Choice) -> None:
        choice.SetBackgroundColour(DARK_ALT)
        choice.SetForegroundColour(LIGHT_TEXT)

    def _stylize_spin(self, ctrl: wx.SpinCtrl) -> None:
        ctrl.SetBackgroundColour(DARK_ALT)
        ctrl.SetForegroundColour(LIGHT_TEXT)

    def _stylize_primary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_ACCENT)
        button.SetForegroundColour(wx.Colour(12, 14, 18))
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)
