"""Shared ``self`` contract that the :class:`SideboardGuidePanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import wx
import wx.dataview as dv


class SideboardGuidePanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``SideboardGuidePanel``."""

    _locale: str | None
    entries: list[dict[str, str]]
    exclusions: list[str]
    guide_view: dv.DataViewListCtrl
    empty_state_panel: wx.Panel
    button_row: wx.Panel
    exclusions_label: wx.StaticText
    warning_label: wx.StaticText
    pin_btn: wx.Button
    on_add_entry: Callable[[], None]
    on_edit_entry: Callable[[], None]
    on_remove_entry: Callable[[], None]
    on_edit_exclusions: Callable[[], None]
    on_export_csv: Callable[[], None]
    on_import_csv: Callable[[], None]
    on_pin_guide: Callable[[], None] | None
    on_edit_flex_slots: Callable[[], None] | None

    def _t(self, key: str, **kwargs: object) -> str: ...
    def _format_card_list(self, cards: dict[str, int] | str) -> str: ...
