"""Window size and position persistence manager."""

from typing import TYPE_CHECKING

import wx
from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller import AppController


class WindowPersistenceManager:
    """Manages saving and restoring window size/position."""

    def __init__(self, window: wx.Frame, controller: "AppController"):
        self.window = window
        self.controller = controller
        self._save_timer: wx.Timer | None = None

    def apply_saved_preferences(self) -> None:
        """Apply saved window size and position from session."""
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)

        if "window_size" in state:
            try:
                width, height = state["window_size"]
                self.window.SetSize(wx.Size(int(width), int(height)))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window size")

        if "screen_pos" in state:
            try:
                x, y = state["screen_pos"]
                self.window.SetPosition(wx.Point(int(x), int(y)))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window position")

    def schedule_save(self) -> None:
        """Schedule window settings save with debouncing."""
        if self._save_timer is None:
            self._save_timer = wx.Timer(self.window)
            self.window.Bind(wx.EVT_TIMER, self._flush_settings, self._save_timer)
        if self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_timer.StartOnce(600)

    def save_now(self) -> None:
        """Immediately save window settings."""
        pos = self.window.GetPosition()
        size = self.window.GetSize()
        self.controller.save_settings(
            window_size=(size.width, size.height), screen_pos=(pos.x, pos.y)
        )

    def _flush_settings(self, _event: wx.TimerEvent) -> None:
        """Timer callback to flush pending settings."""
        self.save_now()

    def cleanup(self) -> None:
        """Stop timer and cleanup resources."""
        if self._save_timer and self._save_timer.IsRunning():
            self._save_timer.Stop()
