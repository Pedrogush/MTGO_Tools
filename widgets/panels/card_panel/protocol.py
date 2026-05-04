"""Shared ``self`` contract that the :class:`CardPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

import wx
import wx.html

from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.card_panel.mana_rasterizer import CardPanelManaRasterizer
from widgets.panels.card_panel.rule_popup import RulePopupFrame


class CardPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardPanel``."""

    mana_icons: ManaIconFactory
    mana_rasterizer: CardPanelManaRasterizer
    _t: Callable[..., str]
    # Optional callable returning a fresh keyword lookup; the panel calls this
    # on each render so updates from a background refresh are picked up.
    # The mapping value type matches ``services.comp_rules_service.KeywordEntry``
    # but is loose-typed here so the protocol stays free of service imports.
    _keyword_lookup_source: Callable[[], Mapping[str, Any]] | None
    _rule_popup: RulePopupFrame | None

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
