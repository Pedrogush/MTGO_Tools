"""AppState Manager - Window state persistence and restoration."""

from pathlib import Path

import wx
from loguru import logger


class AppStateManager:
    """Manages window state persistence and restoration.

    Responsibilities:
    - Loading window position/size preferences
    - Saving window position/size on change
    - Debounced save to avoid excessive file writes
    - Managing window preferences JSON file

    This class does NOT:
    - Handle application state (delegated to AppController)
    - Handle UI events (handled by AppEventCoordinator)
    - Build UI (handled by AppFrameBuilder)
    """

    def __init__(self, frame: wx.Frame, preferences_path: Path):
        """Initialize the state manager.

        Args:
            frame: The window to manage state for
            preferences_path: Path to the preferences JSON file
        """
        self.frame = frame
        self.preferences_path = preferences_path
        self._save_timer: wx.Timer | None = None

    def load_window_preferences(self) -> None:
        """Load and apply saved window position and size."""
        if not self.preferences_path.exists():
            return

        try:
            import json

            with open(self.preferences_path) as f:
                prefs = json.load(f)

            window_prefs = prefs.get("window", {})
            x = window_prefs.get("x")
            y = window_prefs.get("y")
            width = window_prefs.get("width")
            height = window_prefs.get("height")

            if all(v is not None for v in [x, y, width, height]):
                self.frame.SetPosition((x, y))
                self.frame.SetSize((width, height))
                logger.debug(f"Restored window position: ({x}, {y}), size: ({width}, {height})")
        except Exception as exc:
            logger.warning(f"Failed to load window preferences: {exc}")

    def save_window_settings(self) -> None:
        """Save current window position and size to preferences file."""
        try:
            import json

            pos = self.frame.GetPosition()
            size = self.frame.GetSize()

            prefs = {}
            if self.preferences_path.exists():
                with open(self.preferences_path) as f:
                    prefs = json.load(f)

            prefs["window"] = {
                "x": pos.x,
                "y": pos.y,
                "width": size.width,
                "height": size.height,
            }

            # Ensure parent directory exists
            self.preferences_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.preferences_path, "w") as f:
                json.dump(prefs, f, indent=2)

            logger.debug(
                f"Saved window settings: pos=({pos.x}, {pos.y}), size=({size.width}, {size.height})"
            )
        except Exception as exc:
            logger.error(f"Failed to save window settings: {exc}")

    def schedule_settings_save(self, delay_ms: int = 500) -> None:
        """Schedule a delayed save of window settings.

        Debounces rapid window changes to avoid excessive file writes.

        Args:
            delay_ms: Delay in milliseconds before saving
        """
        if self._save_timer and self._save_timer.IsRunning():
            self._save_timer.Stop()

        if not self._save_timer:
            self._save_timer = wx.Timer(self.frame)
            self.frame.Bind(wx.EVT_TIMER, lambda _: self.save_window_settings(), self._save_timer)

        self._save_timer.StartOnce(delay_ms)

    def cleanup(self) -> None:
        """Clean up resources (stop timers, save final state)."""
        if self._save_timer and self._save_timer.IsRunning():
            self._save_timer.Stop()
        self.save_window_settings()
