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
        """
        Initialize the deck repository.

        Args:
            mongo_client: MongoDB client instance. If None, creates a default client.
        """
        self._client = mongo_client
        self._db = None

        # State management for UI layer
        self._decks: list[dict[str, Any]] = []
        self._current_deck: dict[str, Any] | None = None
        self._current_deck_text: str = ""
        self._deck_buffer: dict[str, float] = {}
        self._decks_added: int = 0

    def _get_db(self):
        """Get or create database connection."""
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
        """
        Save a deck to the database.

        Args:
            deck_name: Name of the deck
            deck_content: Full deck list as text
            format_type: MTG format (Modern, Standard, etc.)
            archetype: Deck archetype name
            player: Player name if from tournament
            source: Source of deck ("mtggoldfish", "manual", "averaged", etc.)
            metadata: Additional metadata dict

        Returns:
            ObjectId of the saved deck
        """
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
        """
        Retrieve saved decks from database.

        Args:
            format_type: Filter by format (optional)
            archetype: Filter by archetype (optional)
            sort_by: Field to sort by (default: "date_saved")

        Returns:
            List of deck documents
        """
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
        """
        Load a specific deck by ID.

        Args:
            deck_id: MongoDB ObjectId or string ID

        Returns:
            Deck document or None if not found
        """
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
        """
        Delete a saved deck from database.

        Args:
            deck_id: MongoDB ObjectId or string ID

        Returns:
            True if deleted, False if not found
        """
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
        """
        Update an existing deck in the database.

        Args:
            deck_id: MongoDB ObjectId or string ID
            deck_content: New deck content (optional)
            deck_name: New deck name (optional)
            metadata: Metadata to merge with existing (optional)

        Returns:
            True if updated, False if not found
        """
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
        """
        Read the current deck file, handling legacy locations.

        Returns:
            Deck content as string

        Raises:
            FileNotFoundError: If no deck file found
        """
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
        """
        Save a deck to a file.

        Args:
            deck_name: Name for the deck file
            deck_content: Deck list content
            directory: Target directory (defaults to DECKS_DIR)

        Returns:
            Path to the saved file
        """
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
        """
        List all deck files in a directory.

        Args:
            directory: Directory to search (defaults to DECKS_DIR)

        Returns:
            List of deck file paths
        """
        if directory is None:
            directory = DECKS_DIR

        if not directory.exists():
            return []

        return sorted(directory.glob("*.txt"))

    # ============= Deck Metadata/Notes Storage =============

    def load_notes(self, deck_key: str) -> str:
        """
        Load notes for a specific deck.

        Args:
            deck_key: Unique identifier for the deck

        Returns:
            Notes content or empty string
        """
        data = self._load_json_store(NOTES_STORE)
        return data.get(deck_key, "")

    def save_notes(self, deck_key: str, notes: str) -> None:
        """
        Save notes for a specific deck.

        Args:
            deck_key: Unique identifier for the deck
            notes: Notes content to save
        """
        data = self._load_json_store(NOTES_STORE)
        data[deck_key] = notes
        self._save_json_store(NOTES_STORE, data)

    def load_outboard(self, deck_key: str) -> list[dict[str, Any]]:
        """
        Load outboard cards for a specific deck.

        Args:
            deck_key: Unique identifier for the deck

        Returns:
            List of outboard card dictionaries
        """
        data = self._load_json_store(OUTBOARD_STORE)
        return data.get(deck_key, [])

    def save_outboard(self, deck_key: str, outboard: list[dict[str, Any]]) -> None:
        """
        Save outboard cards for a specific deck.

        Args:
            deck_key: Unique identifier for the deck
            outboard: List of outboard card dictionaries
        """
        data = self._load_json_store(OUTBOARD_STORE)
        data[deck_key] = outboard
        self._save_json_store(OUTBOARD_STORE, data)

    def load_sideboard_guide(self, deck_key: str) -> list[dict[str, Any]]:
        """
        Load sideboard guide for a specific deck.

        Args:
            deck_key: Unique identifier for the deck

        Returns:
            List of sideboard guide entries
        """
        data = self._load_json_store(GUIDE_STORE)
        return data.get(deck_key, [])

    def save_sideboard_guide(self, deck_key: str, guide: list[dict[str, Any]]) -> None:
        """
        Save sideboard guide for a specific deck.

        Args:
            deck_key: Unique identifier for the deck
            guide: List of sideboard guide entries
        """
        data = self._load_json_store(GUIDE_STORE)
        data[deck_key] = guide
        self._save_json_store(GUIDE_STORE, data)

    # ============= State Management (for UI layer) =============

    def get_decks_list(self) -> list[dict[str, Any]]:
        """Get the list of currently loaded decks."""
        return self._decks

    def set_decks_list(self, decks: list[dict[str, Any]]) -> None:
        """Set the list of currently loaded decks."""
        self._decks = decks

    def clear_decks_list(self) -> None:
        """Clear the list of currently loaded decks."""
        self._decks = []

    def get_current_deck(self) -> dict[str, Any] | None:
        """Get the currently selected deck."""
        return self._current_deck

    def get_current_deck_key(self) -> str:
        """Return a stable key for the current deck for store lookups."""
        current_deck = self.get_current_deck()
        if current_deck:
            return current_deck.get("href") or current_deck.get("name", "manual").lower()
        return "manual"

    def get_current_decklist_hash(self) -> str:
        """
        Return a hash of the current decklist (75 cards) for sideboard guide storage.

        This ensures each unique 75-card configuration gets its own guide,
        while the same exact deck loaded multiple times retains its guide.

        Returns:
            Hash string based on sorted mainboard + sideboard card names and quantities
        """
        import hashlib

        deck_text = self.get_current_deck_text()
        if not deck_text:
            return "empty"

        # Create a stable hash from the deck text (sorted to ensure consistency)
        # Normalize the text by sorting lines and removing whitespace variations
        lines = [line.strip() for line in deck_text.strip().split("\n") if line.strip()]
        lines.sort()
        normalized_text = "\n".join(lines)

        # Generate SHA256 hash and take first 16 characters for readability
        hash_obj = hashlib.sha256(normalized_text.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def set_current_deck(self, deck: dict[str, Any] | None) -> None:
        """Set the currently selected deck."""
        self._current_deck = deck

    def get_current_deck_text(self) -> str:
        """Get the text representation of the current deck."""
        return self._current_deck_text

    def set_current_deck_text(self, deck_text: str) -> None:
        """Set the text representation of the current deck."""
        self._current_deck_text = deck_text

    def get_deck_buffer(self) -> dict[str, float]:
        """Get the deck averaging buffer."""
        return self._deck_buffer

    def set_deck_buffer(self, buffer: dict[str, float]) -> None:
        """Set the deck averaging buffer."""
        self._deck_buffer = buffer

    def get_decks_added_count(self) -> int:
        """Get the count of decks added to buffer."""
        return self._decks_added

    def set_decks_added_count(self, count: int) -> None:
        """Set the count of decks added to buffer."""
        self._decks_added = count

    def reset_averaging_state(self) -> None:
        """Reset the deck averaging state."""
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
        """
        Build daily average deck by downloading and averaging multiple decks.

        Args:
            decks: List of deck metadata dictionaries with 'number' field
            download_func: Function to download a deck (takes deck number)
            read_func: Function to read downloaded deck content
            add_to_buffer_func: Function to add deck to averaging buffer
            progress_callback: Optional callback invoked with (index, total)

        Returns:
            Buffer dictionary with averaged card counts
        """
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
        """Load JSON data from a file store."""
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
        """Save JSON data to a file store."""
        try:
            atomic_write_json(path, data, indent=2)
        except OSError as exc:
            logger.error(f"Failed to save {path}: {exc}")


# Global instance for backward compatibility
_default_repository = None


def get_deck_repository() -> DeckRepository:
    """Get the default deck repository instance."""
    global _default_repository
    if _default_repository is None:
        _default_repository = DeckRepository()
    return _default_repository


def reset_deck_repository() -> None:
    """
    Reset the global deck repository instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_repository
    _default_repository = None
