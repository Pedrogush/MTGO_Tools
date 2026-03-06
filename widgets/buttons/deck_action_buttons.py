"""
Deck Action Buttons - Group of buttons for deck operations.

Provides Copy, Save, and Today's Average buttons with callback support.
"""

from collections.abc import Callable

import wx

from utils.stylize import stylize_button


class DeckActionButtons(wx.Panel):
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
        """
        Initialize the deck action buttons panel.

        Args:
            parent: Parent window
            on_copy: Callback when Copy button clicked
            on_save: Callback when Save Deck button clicked
            on_daily_average: Callback when Today's Average button clicked
            on_load: Callback when Load Deck button clicked
        """
        super().__init__(parent)

        self.on_copy = on_copy
        self.on_save = on_save
        self.on_daily_average = on_daily_average
        self.on_load = on_load
        self._labels = labels or {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the button panel UI."""
        col_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(col_sizer)

        # Row 1: Load Deck | Save Deck
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        col_sizer.Add(row1, 0, wx.EXPAND | wx.BOTTOM, 4)

        self.load_button = wx.Button(self, label=self._labels.get("load_deck", "Load Deck"))
        stylize_button(self.load_button)
        self.load_button.Bind(wx.EVT_BUTTON, self._on_load_clicked)
        row1.Add(self.load_button, 1, wx.RIGHT, 6)

        self.save_button = wx.Button(self, label=self._labels.get("save_deck", "Save Deck"))
        stylize_button(self.save_button)
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
        self.daily_average_button.Disable()
        self.daily_average_button.Bind(wx.EVT_BUTTON, self._on_daily_average_clicked)
        row2.Add(self.daily_average_button, 1, wx.RIGHT, 6)

        self.copy_button = wx.Button(self, label=self._labels.get("copy", "Copy"))
        stylize_button(self.copy_button)
        self.copy_button.Disable()
        self.copy_button.Bind(wx.EVT_BUTTON, self._on_copy_clicked)
        row2.Add(self.copy_button, 1)

    # ============= Public API =============

    def enable_daily_average(self, enable: bool = True) -> None:
        """Enable or disable the Today's Average button."""
        if enable:
            self.daily_average_button.Enable()
        else:
            self.daily_average_button.Disable()

    def enable_copy(self, enable: bool = True) -> None:
        """Enable or disable the Copy button."""
        if enable:
            self.copy_button.Enable()
        else:
            self.copy_button.Disable()

    def enable_save(self, enable: bool = True) -> None:
        """Enable or disable the Save Deck button."""
        if enable:
            self.save_button.Enable()
        else:
            self.save_button.Disable()

    def enable_deck_actions(self, enable: bool = True) -> None:
        """Enable or disable Copy and Save buttons (for when deck is loaded)."""
        self.enable_copy(enable)
        self.enable_save(enable)

    def enable_load(self, enable: bool = True) -> None:
        """Enable or disable the Load Deck button."""
        if enable:
            self.load_button.Enable()
        else:
            self.load_button.Disable()

    # ============= Private Methods =============

    def _on_daily_average_clicked(self, _event: wx.Event) -> None:
        """Handle Today's Average button click."""
        if self.on_daily_average:
            self.on_daily_average()

    def _on_copy_clicked(self, _event: wx.Event) -> None:
        """Handle Copy button click."""
        if self.on_copy:
            self.on_copy()

    def _on_load_clicked(self, _event: wx.Event) -> None:
        """Handle Load Deck button click."""
        if self.on_load:
            self.on_load()

    def _on_save_clicked(self, _event: wx.Event) -> None:
        """Handle Save Deck button click."""
        if self.on_save:
            self.on_save()
