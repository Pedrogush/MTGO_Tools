"""Accessors and i18n helpers for the sideboard guide panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.i18n import translate

if TYPE_CHECKING:
    from widgets.panels.sideboard_guide_panel.protocol import SideboardGuidePanelProto

    _Base = SideboardGuidePanelProto
else:
    _Base = object


class SideboardGuidePanelPropertiesMixin(_Base):
    """Getters, translation helper, and pure-data formatters for :class:`SideboardGuidePanel`.

    Kept as a mixin (no ``__init__``) so :class:`SideboardGuidePanel` remains
    the single source of truth for instance-state initialization.
    """

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def get_entries(self) -> list[dict[str, str]]:
        return self.entries

    def get_exclusions(self) -> list[str]:
        return self.exclusions

    def get_selected_index(self) -> int | None:
        item = self.guide_view.GetSelection()
        if not item.IsOk():
            return None
        return self.guide_view.ItemToRow(item)

    def _format_card_list(self, cards: dict[str, int] | str) -> str:
        # Accepts either a dict (new format) or a plain string (old format).
        if isinstance(cards, str):
            # Old format - just return the string
            return cards

        if not cards:
            return ""

        # New format - dict of card name to quantity
        formatted = []
        for name, qty in sorted(cards.items()):
            formatted.append(f"{qty}x {name}")
        return ", ".join(formatted)
