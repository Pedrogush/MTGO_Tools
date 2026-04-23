"""DeckRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from typing import Any

import pymongo

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

    def __init__(self, mongo_client: pymongo.MongoClient | None = None):
        self._client = mongo_client
        self._db = None

        self._decks: list[dict[str, Any]] = []
        self._current_deck: dict[str, Any] | None = None
        self._current_deck_text: str = ""
        self._deck_buffer: dict[str, float] = {}
        self._decks_added: int = 0
