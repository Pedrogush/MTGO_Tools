"""State accessors and pure-data helpers for the radar widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.radar_service import CardFrequency, RadarData
from utils.i18n import translate

if TYPE_CHECKING:
    pass


class RadarPanelPropertiesMixin:
    """Translation and pure-data helpers for :class:`RadarPanel`.

    Kept as a mixin (no ``__init__``) so :class:`RadarPanel` remains the
    single source of truth for instance-state initialization.
    """

    _locale: str | None

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _format_distribution_tooltip(self, card: CardFrequency, total_decks: int) -> str:
        if total_decks <= 0:
            return ""

        lines = [f"{total_decks} decks analyzed"]
        for copies, deck_count in card.copy_distribution.items():
            copy_label = "copy" if copies == 1 else "copies"
            lines.append(f"{deck_count} decks use {copies} {copy_label}")

        return "\n".join(lines)


class RadarFramePropertiesMixin:
    """Translation helper and state accessors for :class:`RadarFrame`."""

    _locale: str | None
    current_radar: RadarData | None

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def get_current_radar(self) -> RadarData | None:
        return self.current_radar
