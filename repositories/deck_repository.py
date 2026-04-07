"""Compatibility facade for deck persistence stores and workspace state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymongo

from repositories.deck_db_store import DeckDbStore
from repositories.deck_file_store import DeckFileStore
from repositories.deck_side_data_store import DeckSideDataStore
from repositories.deck_workspace_state import DeckWorkspaceState


class DeckRepository:
    """Facade preserving the historical deck repository API.

    Persistence is handled by focused stores, while transient UI/workspace state
    lives in DeckWorkspaceState.
    """

    def __init__(
        self,
        mongo_client: pymongo.MongoClient | None = None,
        *,
        db_store: DeckDbStore | None = None,
        file_store: DeckFileStore | None = None,
        side_data_store: DeckSideDataStore | None = None,
        workspace_state: DeckWorkspaceState | None = None,
    ) -> None:
        self.db_store = db_store or DeckDbStore(mongo_client)
        self.file_store = file_store or DeckFileStore()
        self.side_data_store = side_data_store or DeckSideDataStore()
        self.workspace_state = workspace_state or DeckWorkspaceState()

    # ============= Database Operations =============

    def save_to_db(
        self,
        deck_name: str,
        deck_content: str,
        format_type: str | None = None,
        archetype: str | None = None,
        player: str | None = None,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
    ):
        return self.db_store.save_to_db(
            deck_name=deck_name,
            deck_content=deck_content,
            format_type=format_type,
            archetype=archetype,
            player=player,
            source=source,
            metadata=metadata,
        )

    def get_decks(
        self,
        format_type: str | None = None,
        archetype: str | None = None,
        sort_by: str = "date_saved",
    ) -> list[dict[str, Any]]:
        return self.db_store.get_decks(
            format_type=format_type,
            archetype=archetype,
            sort_by=sort_by,
        )

    def load_from_db(self, deck_id):
        return self.db_store.load_from_db(deck_id)

    def delete_from_db(self, deck_id) -> bool:
        return self.db_store.delete_from_db(deck_id)

    def update_in_db(
        self,
        deck_id,
        deck_content: str | None = None,
        deck_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        return self.db_store.update_in_db(
            deck_id,
            deck_content=deck_content,
            deck_name=deck_name,
            metadata=metadata,
        )

    # ============= File System Operations =============

    def read_current_deck_file(self) -> str:
        return self.file_store.read_current_deck_file()

    def save_deck_to_file(
        self, deck_name: str, deck_content: str, directory: Path | None = None
    ) -> Path:
        return self.file_store.save_deck_to_file(deck_name, deck_content, directory)

    def list_deck_files(self, directory: Path | None = None) -> list[Path]:
        return self.file_store.list_deck_files(directory)

    # ============= Deck Metadata/Notes Storage =============

    def load_notes(self, deck_key: str) -> str:
        return self.side_data_store.load_notes(deck_key)

    def save_notes(self, deck_key: str, notes: str) -> None:
        self.side_data_store.save_notes(deck_key, notes)

    def load_outboard(self, deck_key: str) -> list[dict[str, Any]]:
        return self.side_data_store.load_outboard(deck_key)

    def save_outboard(self, deck_key: str, outboard: list[dict[str, Any]]) -> None:
        self.side_data_store.save_outboard(deck_key, outboard)

    def load_sideboard_guide(self, deck_key: str) -> list[dict[str, Any]]:
        return self.side_data_store.load_sideboard_guide(deck_key)

    def save_sideboard_guide(self, deck_key: str, guide: list[dict[str, Any]]) -> None:
        self.side_data_store.save_sideboard_guide(deck_key, guide)

    # ============= Workspace State =============

    def get_decks_list(self) -> list[dict[str, Any]]:
        return self.workspace_state.get_decks_list()

    def set_decks_list(self, decks: list[dict[str, Any]]) -> None:
        self.workspace_state.set_decks_list(decks)

    def clear_decks_list(self) -> None:
        self.workspace_state.clear_decks_list()

    def get_current_deck(self) -> dict[str, Any] | None:
        return self.workspace_state.get_current_deck()

    def get_current_deck_key(self) -> str:
        return self.workspace_state.get_current_deck_key()

    def get_current_decklist_hash(self) -> str:
        return self.workspace_state.get_current_decklist_hash()

    def set_current_deck(self, deck: dict[str, Any] | None) -> None:
        self.workspace_state.set_current_deck(deck)

    def get_current_deck_text(self) -> str:
        return self.workspace_state.get_current_deck_text()

    def set_current_deck_text(self, deck_text: str) -> None:
        self.workspace_state.set_current_deck_text(deck_text)

    def get_deck_buffer(self) -> dict[str, float]:
        return self.workspace_state.get_deck_buffer()

    def set_deck_buffer(self, buffer: dict[str, float]) -> None:
        self.workspace_state.set_deck_buffer(buffer)

    def get_decks_added_count(self) -> int:
        return self.workspace_state.get_decks_added_count()

    def set_decks_added_count(self, count: int) -> None:
        self.workspace_state.set_decks_added_count(count)

    def reset_averaging_state(self) -> None:
        self.workspace_state.reset_averaging_state()


# Global instance for backward compatibility
_default_repository = None


def get_deck_repository() -> DeckRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = DeckRepository()
    return _default_repository


def reset_deck_repository() -> None:
    """Reset the global deck repository (use in tests for isolation)."""
    global _default_repository
    _default_repository = None
