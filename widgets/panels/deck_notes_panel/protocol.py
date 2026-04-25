"""Shared ``self`` contract that the :class:`DeckNotesPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import wx

if TYPE_CHECKING:
    from repositories.deck_repository import DeckRepository
    from services.store_service import StoreService
    from widgets.panels.deck_notes_panel.frame import _NoteCardWidget


class DeckNotesPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckNotesPanel``."""

    deck_repo: DeckRepository
    store_service: StoreService
    notes_store: dict[str, Any]
    notes_store_path: Path
    on_status_update: Callable[[str], None]
    _locale: str | None
    _cards: list[dict[str, str]]
    _card_widgets: list[_NoteCardWidget]
    scroll_win: wx.ScrolledWindow
    cards_sizer: wx.BoxSizer
    empty_state_panel: wx.Panel

    def _t(self, key: str, **kwargs: object) -> str: ...
    def get_notes(self) -> list[dict[str, str]]: ...
