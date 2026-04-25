"""
Deck Action Buttons - Group of buttons for deck operations.

Provides Copy, Save, and Today's Average buttons with callback support.
"""

from collections.abc import Callable

import wx

from utils.stylize import stylize_button
from widgets.buttons.deck_action_buttons.handlers import DeckActionButtonsHandlersMixin
from widgets.buttons.deck_action_buttons.properties import DeckActionButtonsPropertiesMixin


class DeckActionButtons(DeckActionButtonsHandlersMixin, DeckActionButtonsPropertiesMixin, wx.Panel):
    """Panel containing deck action buttons (Copy, Save, Today's Average)."""

    def __init__(
        self,
        parent: wx.Window,
        on_copy: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_daily_average: Callable[[], None] | None = None,
        on_load: Callable[[], None] | None = None,
        labels: dict[str, str] | None = None,
    ):
        super().__init__(parent)

        self.on_copy = on_copy
        self.on_save = on_save
        self.on_daily_average = on_daily_average
        self.on_load = on_load
        self._labels = labels or {}

        self._build_ui()

    def _build_ui(self) -> None:
        col_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(col_sizer)

        # Row 1: Load Deck | Save Deck
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        col_sizer.Add(row1, 0, wx.EXPAND | wx.BOTTOM, 4)

        self.load_button = wx.Button(self, label=self._labels.get("load_deck", "Load Deck"))
        stylize_button(self.load_button)
        if tip := self._labels.get("load_deck_tooltip"):
            self.load_button.SetToolTip(tip)
        self.load_button.Bind(wx.EVT_BUTTON, self._on_load_clicked)
        row1.Add(self.load_button, 1, wx.RIGHT, 6)

        self.save_button = wx.Button(self, label=self._labels.get("save_deck", "Save Deck"))
        stylize_button(self.save_button)
        if tip := self._labels.get("save_deck_tooltip"):
            self.save_button.SetToolTip(tip)
        self.save_button.Disable()
        self.save_button.Bind(wx.EVT_BUTTON, self._on_save_clicked)
        row1.Add(self.save_button, 1)

        # Row 2: Today's Average | Copy
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        col_sizer.Add(row2, 0, wx.EXPAND)

        self.daily_average_button = wx.Button(
            self, label=self._labels.get("daily_average", "Today's Average")
        )
        stylize_button(self.daily_average_button)
        if tip := self._labels.get("daily_average_tooltip"):
            self.daily_average_button.SetToolTip(tip)
        self.daily_average_button.Disable()
        self.daily_average_button.Bind(wx.EVT_BUTTON, self._on_daily_average_clicked)
        row2.Add(self.daily_average_button, 1, wx.RIGHT, 6)

        self.copy_button = wx.Button(self, label=self._labels.get("copy", "Copy"))
        stylize_button(self.copy_button)
        if tip := self._labels.get("copy_tooltip"):
            self.copy_button.SetToolTip(tip)
        self.copy_button.Disable()
        self.copy_button.Bind(wx.EVT_BUTTON, self._on_copy_clicked)
        row2.Add(self.copy_button, 1)
