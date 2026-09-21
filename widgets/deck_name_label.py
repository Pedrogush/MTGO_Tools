"""A deck name you can click to change.

Two views show the same name (the deck tables header and the history toolbar),
so the control is one class used twice rather than two labels kept in step by
hand. It renders the unnamed case in the secondary tone, because "No name
selected for this deck" is a prompt, not a name, and should not read like one.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from widgets.stylize import stylize_label


class DeckNameLabel(wx.StaticText):
    """A one-line deck name. Clicking it asks the frame to edit the name."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        on_click: Callable[[], None],
        surface: str = "panel",
        tooltip: str = "",
    ) -> None:
        super().__init__(parent, label="", style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE)
        self._on_click = on_click
        self._surface = surface
        self._named = False
        if tooltip:
            self.SetToolTip(tooltip)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self._apply_tone()

    def set_name(self, text: str, *, named: bool) -> None:
        """Show ``text``; ``named`` says whether it is a real name."""
        if named != self._named:
            self._named = named
            self._apply_tone()
        if self.GetLabel() != text:
            self.SetLabel(text)

    def _apply_tone(self) -> None:
        stylize_label(
            self,
            level="body",
            surface=self._surface,
            tone="primary" if self._named else "secondary",
        )

    def _on_left_up(self, _event: wx.MouseEvent) -> None:
        self._on_click()


__all__ = ["DeckNameLabel"]
