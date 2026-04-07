"""
Deck Repository - Centralized data access layer for deck operations.

This module handles all deck-related data persistence including:
- Database operations (MongoDB)
- File system operations
- Cache management
- Deck file format conversion
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pymongo
from loguru import logger

from utils.atomic_io import atomic_write_json, atomic_write_text, locked_path
from utils.constants import (
    CACHE_DIR,
    CURR_DECK_FILE,
    DECKS_DIR,
)
from utils.deck import sanitize_filename

# Legacy file paths for migration
LEGACY_CURR_DECK_CACHE = Path("cache") / "curr_deck.txt"
LEGACY_CURR_DECK_ROOT = Path("curr_deck.txt")
NOTES_STORE = CACHE_DIR / "deck_notes.json"
OUTBOARD_STORE = CACHE_DIR / "deck_outboard.json"
GUIDE_STORE = CACHE_DIR / "deck_sbguides.json"


class DeckRepository:
    """Repository for deck data access operations and deck state management."""

    def __init__(self, mongo_client: pymongo.MongoClient | None = None):
        self._client = mongo_client
        self._db = None

        # State management for UI layer
        self._decks: list[dict[str, Any]] = []
        self._current_deck: dict[str, Any] | None = None
        self._current_deck_text: str = ""
        self._deck_buffer: dict[str, float] = {}
        self._decks_added: int = 0

    def _get_db(self):
        if self._db is None:
            if self._client is None:
                self._client = pymongo.MongoClient("mongodb://localhost:27017/")
            self._db = self._client.get_database("lm_scraper")
        return self._db

    # ============= Database Operations =============

    def save_to_db(
        self,
        deck_name: str,
        deck_content: str,
        format_type: str | None = None,
        archetype: str | None = None,
        player: str | None = None,
        source: str = "manual",
        metadata: dict | None = None,
    ):
        db = self._get_db()

        deck_doc = {
            "name": deck_name,
            "content": deck_content,
            "format": format_type,
            "archetype": archetype,
            "player": player,
            "source": source,
            "date_saved": datetime.now(),
            "metadata": metadata or {},
        }

        result = db.decks.insert_one(deck_doc)
        logger.info(f"Saved deck '{deck_name}' to database with ID: {result.inserted_id}")
        return result.inserted_id

    def get_decks(
        self,
        format_type: str | None = None,
        archetype: str | None = None,
        sort_by: str = "date_saved",
    ) -> list[dict]:
        db = self._get_db()

        query = {}
        if format_type:
            query["format"] = format_type
        if archetype:
            query["archetype"] = archetype

        decks = list(db.decks.find(query).sort(sort_by, pymongo.DESCENDING))
        logger.debug(f"Retrieved {len(decks)} decks from database")
        return decks

    def load_from_db(self, deck_id):
        db = self._get_db()

        if isinstance(deck_id, str):
            from bson import ObjectId

            deck_id = ObjectId(deck_id)

        deck = db.decks.find_one({"_id": deck_id})
        if deck:
            logger.debug(f"Loaded deck: {deck['name']}")
        else:
            logger.warning(f"Deck with ID {deck_id} not found")

        return deck

    def delete_from_db(self, deck_id) -> bool:
        db = self._get_db()

        if isinstance(deck_id, str):
            from bson import ObjectId

            deck_id = ObjectId(deck_id)

        result = db.decks.delete_one({"_id": deck_id})

        if result.deleted_count > 0:
            logger.info(f"Deleted deck with ID: {deck_id}")
            return True
        else:
            logger.warning(f"Deck with ID {deck_id} not found for deletion")
            return False

    def update_in_db(
        self,
        deck_id,
        deck_content: str | None = None,
        deck_name: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        db = self._get_db()

        if isinstance(deck_id, str):
            from bson import ObjectId

            deck_id = ObjectId(deck_id)

        update_fields = {"date_modified": datetime.now()}

        if deck_content is not None:
            update_fields["content"] = deck_content
        if deck_name is not None:
            update_fields["name"] = deck_name
        if metadata is not None:
            # Merge metadata
            existing_deck = db.decks.find_one({"_id": deck_id})
            if existing_deck:
                merged_metadata = existing_deck.get("metadata", {})
                merged_metadata.update(metadata)
                update_fields["metadata"] = merged_metadata

        result = db.decks.update_one({"_id": deck_id}, {"$set": update_fields})

        if result.modified_count > 0:
            logger.info(f"Updated deck with ID: {deck_id}")
            return True
        else:
            logger.warning(f"Deck with ID {deck_id} not found or no changes made")
            return False

    # ============= File System Operations =============

    def read_current_deck_file(self) -> str:
        candidates = [CURR_DECK_FILE, LEGACY_CURR_DECK_CACHE, LEGACY_CURR_DECK_ROOT]
        for candidate in candidates:
            if candidate.exists():
                with locked_path(candidate):
                    with candidate.open("r", encoding="utf-8") as fh:
                        contents = fh.read()
                # Migrate from legacy locations
                if candidate != CURR_DECK_FILE:
                    try:
                        atomic_write_text(CURR_DECK_FILE, contents)
                        try:
                            candidate.unlink()
                        except OSError:
                            logger.debug(f"Unable to remove legacy deck file {candidate}")
                    except OSError as exc:
                        logger.debug(f"Failed to migrate curr_deck.txt from {candidate}: {exc}")
                return contents
        raise FileNotFoundError("Current deck file not found")

    def save_deck_to_file(
        self, deck_name: str, deck_content: str, directory: Path | None = None
    ) -> Path:
        if directory is None:
            directory = DECKS_DIR

        directory.mkdir(parents=True, exist_ok=True)

        # Sanitize filename with fallback for empty/whitespace names
        safe_name = sanitize_filename(deck_name, fallback="saved_deck")
        file_path = directory / f"{safe_name}.txt"

        # Handle duplicate names
        counter = 1
        while file_path.exists():
            file_path = directory / f"{safe_name}_{counter}.txt"
            counter += 1

        atomic_write_text(file_path, deck_content)

        logger.info(f"Saved deck to file: {file_path}")
        return file_path

    def list_deck_files(self, directory: Path | None = None) -> list[Path]:
        if directory is None:
            directory = DECKS_DIR

        if not directory.exists():
            return []

        return sorted(directory.glob("*.txt"))

    # ============= Deck Metadata/Notes Storage =============

    def load_notes(self, deck_key: str) -> str:
        data = self._load_json_store(NOTES_STORE)
        return data.get(deck_key, "")

    def save_notes(self, deck_key: str, notes: str) -> None:
        data = self._load_json_store(NOTES_STORE)
        data[deck_key] = notes
        self._save_json_store(NOTES_STORE, data)

    def load_outboard(self, deck_key: str) -> list[dict[str, Any]]:
        data = self._load_json_store(OUTBOARD_STORE)
        return data.get(deck_key, [])

    def save_outboard(self, deck_key: str, outboard: list[dict[str, Any]]) -> None:
        data = self._load_json_store(OUTBOARD_STORE)
        data[deck_key] = outboard
        self._save_json_store(OUTBOARD_STORE, data)

    def load_sideboard_guide(self, deck_key: str) -> list[dict[str, Any]]:
        data = self._load_json_store(GUIDE_STORE)
        return data.get(deck_key, [])

    def save_sideboard_guide(self, deck_key: str, guide: list[dict[str, Any]]) -> None:
        data = self._load_json_store(GUIDE_STORE)
        data[deck_key] = guide
        self._save_json_store(GUIDE_STORE, data)

    # ============= State Management (for UI layer) =============

    def get_decks_list(self) -> list[dict[str, Any]]:
        return self._decks

    def set_decks_list(self, decks: list[dict[str, Any]]) -> None:
        self._decks = decks

    def clear_decks_list(self) -> None:
        self._decks = []

    def get_current_deck(self) -> dict[str, Any] | None:
        return self._current_deck

    def get_current_deck_key(self) -> str:
        current_deck = self.get_current_deck()
        if current_deck:
            return current_deck.get("href") or current_deck.get("name", "manual").lower()
        return "manual"

    def get_current_decklist_hash(self) -> str:
        # Each unique 75-card configuration gets its own guide; the same exact
        # deck loaded multiple times retains its guide.
        import hashlib

        deck_text = self.get_current_deck_text()
        if not deck_text:
            return "empty"

        lines = [line.strip() for line in deck_text.strip().split("\n") if line.strip()]
        lines.sort()
        normalized_text = "\n".join(lines)

        hash_obj = hashlib.sha256(normalized_text.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def set_current_deck(self, deck: dict[str, Any] | None) -> None:
        self._current_deck = deck

    def get_current_deck_text(self) -> str:
        return self._current_deck_text

    def set_current_deck_text(self, deck_text: str) -> None:
        self._current_deck_text = deck_text

    def get_deck_buffer(self) -> dict[str, float]:
        return self._deck_buffer

    def set_deck_buffer(self, buffer: dict[str, float]) -> None:
        self._deck_buffer = buffer

    def get_decks_added_count(self) -> int:
        return self._decks_added

    def set_decks_added_count(self, count: int) -> None:
        self._decks_added = count

    def reset_averaging_state(self) -> None:
        self._deck_buffer = {}
        self._decks_added = 0

    def build_daily_average_deck(
        self,
        decks: list[dict[str, Any]],
        download_func,
        read_func,
        add_to_buffer_func,
        progress_callback=None,
    ) -> dict[str, float]:
        buffer: dict[str, float] = {}
        total = len(decks)
        for index, deck in enumerate(decks, start=1):
            download_func(deck["number"])
            deck_content = read_func()
            buffer = add_to_buffer_func(buffer, deck_content)
            if progress_callback:
                progress_callback(index, total)
        return buffer

    # ============= Private Helper Methods =============

    def _load_json_store(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with locked_path(path):
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load {path}: {exc}")
            return {}

    def _save_json_store(self, path: Path, data: dict[str, Any]) -> None:
        try:
            atomic_write_json(path, data, indent=2)
        except OSError as exc:
            logger.error(f"Failed to save {path}: {exc}")


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
