"""DeckRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repositories.deck_repository.database import DatabaseMixin
from repositories.deck_repository.filesystem import FilesystemMixin
from repositories.deck_repository.metadata_store import MetadataStoreMixin
from repositories.deck_repository.ui_state import UIStateMixin


class DeckRepository(
    DatabaseMixin,
    FilesystemMixin,
    MetadataStoreMixin,
    UIStateMixin,
):
    """Repository for deck data access operations and deck state management."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path

        self._decks: list[dict[str, Any]] = []
        self._current_deck: dict[str, Any] | None = None
        self._current_deck_text: str = ""
        self._deck_buffer: dict[str, float] = {}
        self._decks_added: int = 0
