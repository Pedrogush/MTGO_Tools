"""Static placeholder builders for the card table panel's bookend states.

These are pure, stateless ``wx`` construction helpers (empty-state and
loading-state panels) with their own constant tables. They are intentionally
free functions with no coupling to :class:`CardTablePanel` instance state — the
only contract is that :func:`build_loading_state` stashes the heading
``wx.StaticText`` on the returned panel as ``panel._label`` so
``handlers.show_loading`` can update it via ``self._loading_state._label``.
"""

from __future__ import annotations

import wx

from utils.constants import DARK_PANEL, SUBDUED_TEXT

_EMPTY_STATE_HEADING_SIZE = 13
_EMPTY_STATE_HINT_SIZE = 10
_EMPTY_STATE_HEADING_GAP = 6

_ZONE_EMPTY_HEADING = {
    "main": "No deck loaded",
    "side": "Sideboard is empty",
    "out": "No cards out",
}
_ZONE_EMPTY_HINT = {
    "main": "Select a deck from the list, or load one from file",
}


def build_loading_state(parent: wx.Window) -> wx.Panel:
    panel = wx.Panel(parent)
    panel.SetBackgroundColour(DARK_PANEL)
    sizer = wx.BoxSizer(wx.VERTICAL)
    panel.SetSizer(sizer)

    sizer.AddStretchSpacer(2)
    label = wx.StaticText(panel, label="")
    label.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
    label.SetFont(
        wx.Font(
            _EMPTY_STATE_HEADING_SIZE,
            wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
        )
    )
    sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
    sizer.AddStretchSpacer(3)
    panel._label = label  # type: ignore[attr-defined]
    return panel


def build_empty_state(parent: wx.Window, zone: str) -> wx.Panel:
    panel = wx.Panel(parent)
    panel.SetBackgroundColour(DARK_PANEL)
    sizer = wx.BoxSizer(wx.VERTICAL)
    panel.SetSizer(sizer)

    heading_text = _ZONE_EMPTY_HEADING.get(zone, "")
    hint_text = _ZONE_EMPTY_HINT.get(zone, "")

    sizer.AddStretchSpacer(2)

    if heading_text:
        heading = wx.StaticText(panel, label=heading_text)
        heading.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
        heading_font = wx.Font(
            _EMPTY_STATE_HEADING_SIZE,
            wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
        )
        heading.SetFont(heading_font)
        sizer.Add(
            heading,
            0,
            wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM,
            _EMPTY_STATE_HEADING_GAP,
        )

    if hint_text:
        hint = wx.StaticText(panel, label=hint_text)
        hint.SetForegroundColour(wx.Colour(*(max(c - 40, 0) for c in SUBDUED_TEXT)))
        hint_font = wx.Font(
            _EMPTY_STATE_HINT_SIZE,
            wx.FONTFAMILY_SWISS,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
        )
        hint.SetFont(hint_font)
        sizer.Add(hint, 0, wx.ALIGN_CENTER_HORIZONTAL)

    sizer.AddStretchSpacer(3)
    return panel
