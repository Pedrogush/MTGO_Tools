"""Shared ``self`` contract that the :class:`CardPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import wx
import wx.html

from utils.mana_icon_factory import ManaIconFactory


class CardPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardPanel``."""

    mana_icons: ManaIconFactory
    _t: Callable[..., str]

    # State
    # ``_current_meta`` may be a plain dict or a ``CardEntry`` Struct — both
    # expose ``.get(key)`` and ``__getitem__``.
    _current_meta: Any
    _current_printing: dict[str, Any] | None
    _current_format: str | None
    _current_archetype: dict[str, Any] | None
    _current_radar: Any | None

    # UI widgets
    notebook: wx.Notebook
    oracle_html: wx.html.HtmlWindow
    stats_card_label: wx.StaticText
    stats_format_header: wx.StaticText
    stats_format_total: wx.StaticText
    stats_format_avg: wx.StaticText
    stats_archetype_header: wx.StaticText
    stats_main_header: wx.StaticText
    stats_main_total: wx.StaticText
    stats_main_avg: wx.StaticText
    stats_main_karsten: wx.StaticText
    stats_main_inclusion: wx.StaticText
    stats_side_header: wx.StaticText
    stats_side_total: wx.StaticText
    stats_side_avg: wx.StaticText
    stats_side_karsten: wx.StaticText
    stats_side_inclusion: wx.StaticText
