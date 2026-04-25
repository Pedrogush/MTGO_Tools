"""Read-only accessors and pure-data helpers for the deck builder panel."""

from __future__ import annotations

from typing import Any

import wx

from services.radar_service import RadarData
from utils.i18n import translate


class DeckBuilderPanelPropertiesMixin:
    """Filter getters and i18n helpers for :class:`DeckBuilderPanel`.

    Kept as a mixin (no ``__init__``) so :class:`DeckBuilderPanel` remains the
    single source of truth for instance-state initialization.
    """

    _locale: str | None
    inputs: dict[str, wx.TextCtrl]
    mana_exact_cb: wx.CheckBox | None
    mv_comparator: wx.Choice | None
    mv_value: wx.TextCtrl | None
    format_choice: wx.Choice | None
    color_checks: dict[str, wx.ToggleButton]
    color_mode_choice: wx.Choice | None
    text_mode_choice: wx.Choice | None
    results_ctrl: Any
    results_cache: list[dict[str, Any]]
    format_pool_cb: wx.CheckBox | None
    active_radar: RadarData | None
    radar_enabled: bool
    radar_zone: str

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def get_filters(self) -> dict[str, Any]:
        filters = {key: ctrl.GetValue().strip() for key, ctrl in self.inputs.items()}
        filters["mana_exact"] = self.mana_exact_cb.IsChecked() if self.mana_exact_cb else False
        filters["text_mode"] = (
            "any" if self.text_mode_choice and self.text_mode_choice.GetSelection() == 1 else "all"
        )
        filters["mv_comparator"] = (
            self.mv_comparator.GetStringSelection() if self.mv_comparator else "Any"
        )
        mv_value_text = self.mv_value.GetValue().strip() if self.mv_value else ""
        filters["mv_value"] = mv_value_text
        filters["formats"] = (
            [self.format_choice.GetStringSelection().lower()]
            if self.format_choice and self.format_choice.GetSelection() > 0
            else []
        )
        filters["format_pool_enabled"] = bool(
            self.format_pool_cb
            and self.format_pool_cb.IsChecked()
            and self.format_choice
            and self.format_choice.GetSelection() > 0
        )
        filters["color_mode"] = (
            self.color_mode_choice.GetStringSelection() if self.color_mode_choice else "Any"
        )
        filters["selected_colors"] = [
            code for code, btn in self.color_checks.items() if btn.GetValue()
        ]

        # Add radar filter if enabled
        filters["radar_enabled"] = self.radar_enabled
        if self.radar_enabled and self.active_radar:
            from services.radar_service import get_radar_service

            radar_service = get_radar_service()
            filters["radar_cards"] = radar_service.get_radar_card_names(
                self.active_radar, self.radar_zone
            )
        else:
            filters["radar_cards"] = set()

        return filters

    def get_result_at_index(self, idx: int) -> dict[str, Any] | None:
        if idx < 0 or idx >= len(self.results_cache):
            return None
        return self.results_cache[idx]

    def get_selected_result(self) -> dict[str, Any] | None:
        if not self.results_ctrl:
            return None
        selected = self.results_ctrl.GetFirstSelected()
        return self.get_result_at_index(selected) if selected != wx.NOT_FOUND else None
