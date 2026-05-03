"""Pure helpers (no ``self`` UI mutation) for :class:`CardPanel`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from widgets.panels.card_panel.protocol import CardPanelProto

    _Base = CardPanelProto
else:
    _Base = object


def _stats_lookup_names(card_name: str) -> list[str]:
    """Lookup-name candidates ordered by likelihood of matching stored data.

    Decklist sources (Goldfish, MTGO) typically key DFC/MDFC cards by their
    front-face name only, while ``card_name`` here may be the canonical
    ``"Front // Back"`` form. Try the front face first, then the full name.
    """
    candidates: list[str] = []
    name = card_name.strip()
    if "//" in name:
        front = name.split("//", 1)[0].strip()
        if front:
            candidates.append(front)
    if name and name not in candidates:
        candidates.append(name)
    return candidates


def _find_card_frequency(cards: list[Any], card_name: str) -> Any | None:
    candidates = {n.lower() for n in _stats_lookup_names(card_name)}
    for entry in cards:
        if str(getattr(entry, "card_name", "")).lower() in candidates:
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
