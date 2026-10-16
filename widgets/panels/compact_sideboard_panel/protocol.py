"""Shared ``self`` contract that the :class:`CompactSideboardPanel` mixins assume."""

from __future__ import annotations

from typing import Protocol

import wx

from widgets.collapse_toggle import CollapseToggle
from widgets.empty_state import EmptyState


class CompactSideboardPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CompactSideboardPanel``."""

    _current_entry: dict | None
    _play_first: bool
    _header_text: str
    _resizing: bool
    header_label: wx.StaticText
    toggle_btn: wx.Button
    collapse_btn: CollapseToggle
    _collapsed: bool
    _body_mode: str
    status_label: wx.StaticText
    card_list: wx.ListBox
    empty_state: EmptyState
