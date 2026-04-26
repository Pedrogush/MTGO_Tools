"""Shared ``self`` contract that the :class:`CardInspectorPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import wx

from utils.card_data import CardDataManager
from utils.card_images import CardImageRequest
from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.card_image_display import CardImageDisplay
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl


class CardInspectorPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardInspectorPanel``."""

    card_manager: CardDataManager | None
    mana_icons: ManaIconFactory
    active_zone: str | None
    inspector_printings: list[dict[str, Any]]
    inspector_current_printing: int
    inspector_current_card_name: str | None
    printing_label_width: int
    image_cache: Any
    bulk_data_by_name: dict[str, list[dict[str, Any]]] | None
    _image_available: bool
    _loading_printing: bool
    _image_request_handler: Callable[[CardImageRequest], None] | None
    _selected_card_handler: Callable[[CardImageRequest | None], None] | None
    _printings_request_handler: Callable[[str], None] | None
    _printings_request_inflight: str | None
    _has_selection: bool
    _failed_image_requests: set[tuple[str, str]]
    _image_request_name: str | None
    _image_lookup_gen: int

    card_image_display: CardImageDisplay
    image_column_panel: wx.Panel
    image_text_panel: wx.Panel
    image_text_ctrl: ManaSymbolRichCtrl
    nav_panel: wx.Panel
    prev_btn: wx.Button
    next_btn: wx.Button
    printing_label: wx.StaticText
    loading_label: wx.StaticText
    details_panel: wx.Panel
    name_label: wx.StaticText
    cost_container: wx.Panel
    cost_sizer: wx.BoxSizer
    type_label: wx.StaticText
    stats_label: wx.StaticText
    text_ctrl: ManaSymbolRichCtrl

    def _resolve_image_request_name(
        self, card: dict[str, Any], meta: dict[str, Any] | None
    ) -> str | None: ...
    def _request_matches_current(self, request: CardImageRequest) -> bool: ...
    def _failure_key(self, request: CardImageRequest) -> tuple[str, str]: ...
