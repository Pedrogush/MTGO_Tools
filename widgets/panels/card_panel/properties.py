"""Pure helpers (no ``self`` UI mutation) for :class:`CardPanel`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from widgets.panels.card_panel.protocol import CardPanelProto

    _Base = CardPanelProto
else:
    _Base = object


def _find_card_frequency(cards: list[Any], card_name: str) -> Any | None:
    name_lower = card_name.lower()
    for entry in cards:
        if str(getattr(entry, "card_name", "")).lower() == name_lower:
            return entry
    return None


class CardPanelPropertiesMixin(_Base):
    """Pure helpers used by :class:`CardPanel`. No state mutation."""

    def _format_number(self, value: float | int | None) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            if value.is_integer():
                return f"{int(value):,}"
            return f"{value:,.2f}"
        return f"{int(value):,}"

    def _format_average(self, value: float | None) -> str:
        if value is None:
            return "—"
        return f"{float(value):,.2f}"

    def _archetype_name(self) -> str | None:
        if not self._current_archetype:
            return None
        name = self._current_archetype.get("name")
        return str(name) if name else None

    def _lookup_main_freq(self, card_name: str) -> Any | None:
        if not self._current_radar:
            return None
        return _find_card_frequency(self._current_radar.mainboard_cards, card_name)

    def _lookup_side_freq(self, card_name: str) -> Any | None:
        if not self._current_radar:
            return None
        return _find_card_frequency(self._current_radar.sideboard_cards, card_name)
