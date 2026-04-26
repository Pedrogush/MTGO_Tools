"""Shared ``self`` contract that the :class:`CompactSideboardPanel` mixins assume."""

from __future__ import annotations

from typing import Protocol

import wx


class CompactSideboardPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CompactSideboardPanel``."""

    _current_entry: dict | None
    _play_first: bool
    header_label: wx.StaticText
    toggle_btn: wx.Button
    status_label: wx.StaticText
    card_list: wx.ListBox
