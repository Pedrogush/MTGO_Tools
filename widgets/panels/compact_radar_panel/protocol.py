"""Shared ``self`` contract that the :class:`CompactRadarPanel` mixins assume."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import wx

from widgets.panels.compact_radar_panel.properties import RadarViewMode

if TYPE_CHECKING:
    from services.radar_service import RadarData


class CompactRadarPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CompactRadarPanel``."""

    current_radar: RadarData | None
    _view_mode: RadarViewMode
    header_label: wx.StaticText
    view_toggle_btn: wx.Button
    status_label: wx.StaticText
    card_list: wx.ListBox
