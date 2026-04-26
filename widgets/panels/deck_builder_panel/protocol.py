"""Shared ``self`` contract that the :class:`DeckBuilderPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import wx

from services.radar_service import RadarData
from utils.mana_icon_factory import ManaIconFactory


class DeckBuilderPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckBuilderPanel``."""

    _locale: str | None
    mana_icons: ManaIconFactory

    _on_switch_to_research: Callable[[], None]
    _on_ensure_card_data: Callable[[], None]
    _open_mana_keyboard: Callable[[], None]
    _on_search_callback: Callable[[], None]
    _on_clear_callback: Callable[[], None]
    _on_result_selected_callback: Callable[[int | None], None]
    _on_add_to_main: Callable[[str], None] | None
    _on_add_to_side: Callable[[str], None] | None
    _on_add_to_active_zone: Callable[[str], None] | None

    inputs: dict[str, wx.TextCtrl]
    mana_exact_cb: wx.CheckBox | None
    mv_comparator: wx.Choice | None
    mv_value: wx.TextCtrl | None
    format_choice: wx.Choice | None
    color_checks: dict[str, wx.ToggleButton]
    color_mode_choice: wx.Choice | None
    text_mode_choice: wx.Choice | None
    results_ctrl: Any
    status_label: wx.StaticText | None
    _add_main_btn: wx.Button | None
    _add_side_btn: wx.Button | None
    _adv_panel: wx.Panel | None
    _adv_toggle_btn: wx.Button | None
    results_cache: list[dict[str, Any]]
    _search_timer: wx.Timer

    active_radar: RadarData | None
    radar_enabled: bool
    radar_zone: str
    format_pool_cb: wx.CheckBox | None
    radar_cb: wx.CheckBox
    radar_zone_choice: wx.Choice

    def _t(self, key: str, **kwargs: object) -> str: ...
    def get_filters(self) -> dict[str, Any]: ...
    def get_result_at_index(self, idx: int) -> dict[str, Any] | None: ...
    def get_selected_result(self) -> dict[str, Any] | None: ...
