"""The left panel's mode switch (F2).

What it replaces
----------------
A single full-width ``wx.Button`` at the top of the left panel, labelled with the
mode you are **not** in. Two defects in one control:

* **It read as a section header.** Full-width, at the very top of the panel,
  above a caption — that is the shape of a heading, not of a control, and phase 2
  only made it quieter (the saturated fill became ``secondary``); it did not
  change the shape.
* **Its label named the destination.** In Deck Research the button said "Deck
  Builder". So the one string with the most visual weight on the panel named the
  mode you were *not* looking at, and the only way to read the current mode was
  the grey subtitle underneath it.

What this is
------------
The app's existing segmented-toggle idiom, which already sits ~400px away on the
deck workspace as ``Grid`` / ``Table`` / ``Pile``: one chip per mode, the current
one wearing the app's single selection token (``stylize_button(kind="toggle",
selected=True)``), the other a ghost chip. Both modes are named, exactly one is
lit, and the control is sized to its labels rather than to the panel — so it
stops occupying the position and width of a heading.

Reusing that idiom rather than inventing a switch was deliberate: this app had
four selection idioms before phase 2 and the redesign's acceptance criteria ask
for one. A segmented control *is* a selection.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import wx

from utils.constants import MODE_SWITCH_HEIGHT, MODE_SWITCH_PADDING_X, SPACE_XS
from widgets.stylize import size_compact_button, stylize_button, surface_colour


class ModeSwitch(wx.Panel):
    """A segmented control: one chip per mode, the current one selected.

    :param modes: ``((value, label), ...)`` in display order.
    :param current: the value that is selected.
    :param on_select: called with the chosen value. It is **not** called for a
        click on the already-selected chip — a segmented control is a selection,
        and re-selecting what is already selected is a no-op, not a toggle.
    :param surface: the surface the chips sit on, so the ghost fill steps off the
        right background (see :func:`widgets.stylize.stylize_button`).
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        modes: Sequence[tuple[str, str]],
        current: str,
        on_select: Callable[[str], None],
        surface: str = "panel",
        tooltips: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(surface_colour(surface))
        self._surface = surface
        self._current = current
        self._on_select = on_select
        self._buttons: dict[str, wx.Button] = {}

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(sizer)

        for index, (value, label) in enumerate(modes):
            button = wx.Button(self, label=label, style=wx.BU_EXACTFIT)
            # Skip empties: a call site that has no string for a chip should get
            # no tooltip, not an empty popup.
            if tooltips and tooltips.get(value):
                button.SetToolTip(tooltips[value])
            button.Bind(wx.EVT_BUTTON, lambda _evt, v=value: self._choose(v))
            self._buttons[value] = button
            sizer.Add(button, 0, wx.LEFT if index else 0, SPACE_XS if index else 0)

        self._restyle()

    # ------------------------------------------------------------------
    def set_current(self, value: str) -> None:
        """Light the chip for ``value`` without firing ``on_select``."""
        if value == self._current or value not in self._buttons:
            return
        self._current = value
        self._restyle()

    @property
    def current(self) -> str:
        return self._current

    def _choose(self, value: str) -> None:
        if value == self._current:
            return
        self._on_select(value)

    def _restyle(self) -> None:
        for value, button in self._buttons.items():
            stylize_button(
                button,
                kind="toggle",
                selected=value == self._current,
                surface=self._surface,
            )
            # BU_EXACTFIT sizes to the text extent plus ~2px, and the selected
            # chip is bold; size_compact_button measures the bold face either
            # way, so the row keeps one width as the selection moves.
            size_compact_button(
                button, pad_x=MODE_SWITCH_PADDING_X, height=MODE_SWITCH_HEIGHT
            )
            button.Refresh()
        self.Layout()


__all__ = ["ModeSwitch"]
