"""Accessors and i18n helpers for the deck notes panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.i18n import translate

if TYPE_CHECKING:
    from widgets.panels.deck_notes_panel.protocol import DeckNotesPanelProto

    _Base = DeckNotesPanelProto
else:
    _Base = object


class DeckNotesPanelPropertiesMixin(_Base):
    """Getters and translation helper for :class:`DeckNotesPanel`.

    Kept as a mixin (no ``__init__``) so :class:`DeckNotesPanel` remains the
    single source of truth for instance-state initialization.
    """

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def get_notes(self) -> list[dict[str, str]]:
        return [w.get_data() for w in self._card_widgets]
