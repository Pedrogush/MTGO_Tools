"""Bookend states for the card table panel: "nothing loaded" and "loading".

Both are pure, stateless ``wx`` construction helpers. The only contract is that
:func:`build_loading_state` stashes its heading ``wx.StaticText`` on the returned
panel as ``panel._label`` so ``handlers.show_loading`` can update it via
``self._loading_state._label``.

C5/C6: the empty state used to be a hand-rolled panel with its own hard-coded
English strings, its own ``wx.Font`` point sizes (13 and 10, neither on the type
ladder), a hand-mixed "dimmer than SUBDUED_TEXT" colour, and a 2:3
stretch-spacer split that put the block above centre for no stated reason. It is
:class:`widgets.empty_state.EmptyState` now, and its copy is translated.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from utils.constants import DARK_PANEL, SUBDUED_TEXT
from widgets.empty_state import EmptyState
from widgets.stylize import apply_type_level

_ZONE_KEYS = ("main", "side", "out")


def build_loading_state(parent: wx.Window) -> wx.Panel:
    panel = wx.Panel(parent)
    panel.SetBackgroundColour(DARK_PANEL)
    sizer = wx.BoxSizer(wx.VERTICAL)
    panel.SetSizer(sizer)

    sizer.AddStretchSpacer(1)
    label = wx.StaticText(panel, label="", style=wx.ALIGN_CENTRE_HORIZONTAL)
    label.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
    apply_type_level(label, "body")
    sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
    sizer.AddStretchSpacer(1)
    panel._label = label  # type: ignore[attr-defined]
    return panel


def build_empty_state(
    parent: wx.Window, zone: str, translate: Callable[[str], str] | None = None
) -> wx.Panel:
    """The "this zone has no cards" state for ``zone`` (``main``/``side``/``out``).

    ``translate`` is the owning panel's ``_t``; it is optional only so the
    existing tests that build a panel without a locale keep working, in which
    case the i18n key is shown rather than guessing an English fallback.
    """
    key = zone if zone in _ZONE_KEYS else "main"
    tr = translate or (lambda k: k)
    hint_key = f"tabs.empty.{key}.hint"
    hint = tr(hint_key)
    return EmptyState(
        parent,
        message=tr(f"tabs.empty.{key}"),
        hint=None if hint == hint_key else hint,
        surface="panel",
    )
