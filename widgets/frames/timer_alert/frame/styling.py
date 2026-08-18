"""Small wx styling helpers shared by the timer alert frame's section builders.

The widget-level helpers delegate to :mod:`widgets.stylize` so the timer window
picks up the phase-1 native-control theming (dark dropdowns, dark checkbox
glyphs, dark spin arrows) instead of quietly re-implementing an older subset of
it. The button helpers are now thin wrappers over ``stylize_button`` as well; they
stay as methods only because the section builders call them through ``self``.
"""

from __future__ import annotations

import wx

from utils.constants import DARK_BG, LIGHT_TEXT
from widgets.checkbox import DarkCheckBox
from widgets.stylize import (
    stylize_button,
    stylize_checkbox,
    stylize_choice,
    stylize_spinctrl,
)


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
        stylize_choice(choice)

    def _stylize_spin(self, ctrl: wx.SpinCtrl) -> None:
        stylize_spinctrl(ctrl)

    def _stylize_checkbox(self, ctrl: DarkCheckBox) -> None:
        stylize_checkbox(ctrl)

    def _stylize_primary_button(self, button: wx.Button) -> None:
        stylize_button(button, kind="primary")

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        stylize_button(button, kind="secondary")
