"""
Toolbar Buttons - Shared utility buttons for the deck selector toolbar.

Provides quick-access buttons for opponent tracking, timers, history, and data tasks.
"""

from collections.abc import Callable

import wx


class ToolbarButtons(wx.Panel):
    """Panel containing the deck selector toolbar buttons."""

    def __init__(
        self,
        parent: wx.Window,
        on_open_opponent_tracker: Callable[[], None] | None = None,
        on_open_timer_alert: Callable[[], None] | None = None,
        on_open_match_history: Callable[[], None] | None = None,
        on_open_metagame_analysis: Callable[[], None] | None = None,
        on_load_collection: Callable[[], None] | None = None,
        on_download_card_images: Callable[[], None] | None = None,
        on_update_card_database: Callable[[], None] | None = None,
    ):
        """
        Initialize the toolbar button panel.

        Args:
            parent: Parent window
            on_open_opponent_tracker: Callback for "Opponent Tracker"
            on_open_timer_alert: Callback for "Timer Alert"
            on_open_match_history: Callback for "Match History"
            on_open_metagame_analysis: Callback for "Metagame Analysis"
            on_load_collection: Callback for "Load Collection"
            on_download_card_images: Callback for "Download Card Images"
            on_update_card_database: Callback for "Update Card Database"
        """
        super().__init__(parent)

        self._button_row = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self._button_row)

        self.opponent_tracker_button = self._add_button(
            "Opponent Tracker", on_open_opponent_tracker
        )
        self.timer_alert_button = self._add_button("Timer Alert", on_open_timer_alert)
        self.match_history_button = self._add_button("Match History", on_open_match_history)
        self.metagame_analysis_button = self._add_button(
            "Metagame Analysis", on_open_metagame_analysis
        )
        self.load_collection_button = self._add_button("Load Collection", on_load_collection)
        self.download_images_button = self._add_button(
            "Download Card Images", on_download_card_images
        )
        self.update_database_button = self._add_button(
            "Update Card Database", on_update_card_database
        )

        self._button_row.AddStretchSpacer(1)

    # ============= Helpers =============

    def _add_button(
        self, label: str, handler: Callable[[], None] | None, *, margin: int = 6
    ) -> wx.Button:
        """Create a toolbar button and bind its handler if provided."""
        button = wx.Button(self, label=label)
        if handler:
            button.Bind(wx.EVT_BUTTON, lambda _evt, cb=handler: cb())
        else:  # pragma: no cover - defensive fallback
            button.Disable()
        self._button_row.Add(button, 0, wx.RIGHT, margin)
        return button


__all__ = ["ToolbarButtons"]
