"""Shared ``self`` contract that the :class:`CardBoxPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import wx

from utils.mana_icon_factory import ManaIconFactory


class CardBoxPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardBoxPanel``."""

    zone: str
    card: dict[str, Any]
    qty_label: wx.StaticText
    button_panel: wx.Panel
    _icon_factory: ManaIconFactory
    _get_metadata: Callable[[str], dict[str, Any] | None]
    _owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]]
    _on_delta: Callable[[str, str, int], None]
    _on_remove: Callable[[str, str], None]
    _on_select: Callable[[str, dict[str, Any], Any], None]
    _on_hover: Callable[[str, dict[str, Any]], None] | None
    _active: bool
    _mana_cost: str
    _card_color: tuple[int, int, int]
    _mana_cost_bitmap: wx.Bitmap | None
    _template_bitmap: wx.Bitmap | None
    _card_bitmap: wx.Bitmap | None
    _image_available: bool
    _image_attempted: bool
    _image_generation: int
    _image_name_candidates: list[str]

    def _resolve_card_color(self, meta: dict[str, Any]) -> tuple[int, int, int]: ...
    def _build_image_name_candidates(
        self, card: dict[str, Any], meta: dict[str, Any]
    ) -> list[str]: ...
    def _wrap_text(self, dc: wx.DC, text: str, max_width: int) -> list[str]: ...
