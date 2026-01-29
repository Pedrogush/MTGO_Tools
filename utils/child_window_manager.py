"""Manager for child window lifecycle."""

import wx

from utils.ui_helpers import open_child_window, widget_exists


class ChildWindowManager:
    """Manages child window references and lifecycle."""

    def __init__(self, parent: wx.Frame):
        self.parent = parent
        self.windows: dict[str, wx.Window | None] = {}

    def open_or_focus(
        self,
        attr_name: str,
        window_class: type[wx.Window],
        title: str,
    ) -> None:
        """Open a child window or focus if already open."""
        current = self.windows.get(attr_name)
        if widget_exists(current):
            current.Raise()
            return

        def on_close(event: wx.CloseEvent) -> None:
            self.windows[attr_name] = None
            event.Skip()

        window = open_child_window(self.parent, attr_name, window_class, title, on_close)
        self.windows[attr_name] = window

    def get_window(self, attr_name: str) -> wx.Window | None:
        """Get a child window by name."""
        return self.windows.get(attr_name)

    def close_all(self) -> None:
        """Close all managed child windows."""
        for attr_name, window in self.windows.items():
            if widget_exists(window):
                window.Destroy()
                self.windows[attr_name] = None
