"""Accessors and i18n helpers for the sideboard card selector panel."""

from __future__ import annotations

from typing import Any

from utils.i18n import translate


class SideboardCardSelectorPropertiesMixin:
    """Getters and translation helper for :class:`SideboardCardSelector`.

    Kept as a mixin (no ``__init__``) so :class:`SideboardCardSelector` remains
    the single source of truth for instance-state initialization.
    """

    _locale: str | None
    selected_cards: dict[str, int]

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def get_selected_cards(self) -> dict[str, int]:
        return self.selected_cards.copy()

    def get_selected_cards_list(self) -> list[dict[str, Any]]:
        return [{"name": name, "qty": qty} for name, qty in sorted(self.selected_cards.items())]
