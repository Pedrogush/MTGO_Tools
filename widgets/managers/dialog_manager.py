"""Dialog Manager - Lifecycle management for child windows."""

from typing import Callable

import wx


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
    ) -> wx.Window:
        """Open or focus a managed window.

        Args:
            attr_name: Unique identifier for this window
            window_class: Class to instantiate if window doesn't exist
            title: Window title
            on_close: Optional callback for close event

        Returns:
            The window instance (new or existing)
        """
        raise NotImplementedError("To be implemented in Step 2")

    def close_all(self) -> None:
        """Close and destroy all managed windows."""
        raise NotImplementedError("To be implemented in Step 2")

    def get_window(self, attr_name: str) -> wx.Window | None:
        """Retrieve an existing window by name.

        Args:
            attr_name: The window identifier

        Returns:
            The window instance or None if not found
        """
        raise NotImplementedError("To be implemented in Step 2")
