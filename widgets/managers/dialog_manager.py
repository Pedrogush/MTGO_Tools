"""Dialog Manager - Lifecycle management for child windows."""

from collections.abc import Callable
from typing import Any

import wx
from loguru import logger


def _widget_exists(window: wx.Window | None) -> bool:
    """Check if a wx widget still exists and is shown.

    Args:
        window: The window to check

    Returns:
        True if window exists and is shown, False otherwise
    """
    if window is None:
        return False
    try:
        return bool(window.IsShown())
    except (RuntimeError, wx.PyDeadObjectError):
        return False


class DialogManager:
    """Manages lifecycle of child dialog windows.

    Responsibilities:
    - Opening and showing child dialogs (opponent tracker, timer, etc.)
    - Tracking open windows to prevent duplicates
    - Cleanup on parent close

    Usage:
        manager = DialogManager(parent_frame)
        manager.open_window('tracker', MTGOpponentDeckSpy, "Tracker", on_close)
        manager.close_all()
    """

    def __init__(self, parent: wx.Window):
        """Initialize the dialog manager.

        Args:
            parent: The parent window that owns managed dialogs
        """
        self.parent = parent
        self._windows: dict[str, wx.Window] = {}

    def open_window(
        self,
        attr_name: str,
        window_class: type,
        title: str,
        on_close: Callable[[wx.CloseEvent], None] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> wx.Window | None:
        """Open or focus a managed window.

        Args:
            attr_name: Unique identifier for this window
            window_class: Class to instantiate if window doesn't exist
            title: Window title (used in error messages)
            on_close: Optional callback for close event
            *args: Positional arguments passed to window constructor
            **kwargs: Keyword arguments passed to window constructor

        Returns:
            The window instance (new or existing), or None if creation failed
        """
        # Check if window already exists and is visible
        existing = self._windows.get(attr_name)
        if _widget_exists(existing):
            existing.Raise()
            return existing

        # Create new window
        try:
            window = window_class(self.parent, *args, **kwargs)

            # Bind close event to cleanup callback
            def handle_close(event: wx.CloseEvent) -> None:
                # Call user callback if provided
                if on_close:
                    on_close(event)
                # Clean up our tracking
                self._windows.pop(attr_name, None)
                # Allow default close behavior
                event.Skip()

            window.Bind(wx.EVT_CLOSE, handle_close)
            window.Show()

            # Store reference
            self._windows[attr_name] = window
            return window

        except Exception as exc:  # pragma: no cover - UI side-effects
            logger.error(f"Failed to open {title.lower()}: {exc}")
            wx.MessageBox(
                f"Unable to open {title.lower()}:\n{exc}",
                title,
                wx.OK | wx.ICON_ERROR,
            )
            return None

    def close_all(self) -> None:
        """Close and destroy all managed windows."""
        # Create a list copy to avoid modifying dict during iteration
        windows_to_close = list(self._windows.items())

        for _attr_name, window in windows_to_close:
            if _widget_exists(window):
                try:
                    window.Destroy()
                except (RuntimeError, wx.PyDeadObjectError):
                    # Window already destroyed
                    pass

        # Clear the dict
        self._windows.clear()

    def get_window(self, attr_name: str) -> wx.Window | None:
        """Retrieve an existing window by name.

        Args:
            attr_name: The window identifier

        Returns:
            The window instance or None if not found/not shown
        """
        window = self._windows.get(attr_name)
        if _widget_exists(window):
            return window
        return None
