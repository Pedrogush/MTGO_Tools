"""
Collection Service - Business logic for collection/inventory management.

This module contains all the business logic for managing card collections:
- Loading collection data
- Checking card ownership
- Calculating missing cards
- Collection statistics
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from repositories.card_repository import CardRepository, get_card_repository
from services.collection_cache import find_latest_cached_file, get_file_age_hours
from services.collection_parsing import build_inventory
from utils.constants import (
    COLLECTION_CACHE_MAX_AGE_SECONDS,
)


@dataclass(frozen=True)
class CollectionStatus:
    """Display-friendly collection metadata."""

    label: str
    filepath: Path
    card_count: int
    age_hours: int


class CollectionService:
    """Service for collection/inventory management logic."""

    def __init__(self, card_repository: CardRepository | None = None):
        """
        Initialize the collection service.

        Args:
            card_repository: CardRepository instance
        """
        self.card_repo = card_repository or get_card_repository()
        self._collection: dict[str, int] = {}
        self._collection_path: Path | None = None
        self._collection_loaded = False

    # ============= Collection Loading =============

    def load_collection(self, filepath: Path | None = None, force: bool = False) -> bool:
        """
        Load collection from file or cache.

        Args:
            filepath: Path to collection file (optional)
            force: If True, reload even if already loaded

        Returns:
            True if loaded successfully, False otherwise
        """
        if self._collection_loaded and not force:
            return True

        try:
            if filepath is None:
                filepath = self.card_repo.get_collection_cache_path()

            if not filepath.exists():
                logger.info("No collection file found")
                self._collection = {}
                self._collection_path = None
                self._collection_loaded = True
                return True

            # Load collection data
            cards = self.card_repo.load_collection_from_file(filepath)

            # Convert to dictionary for quick lookup
            self._collection = build_inventory(cards)

            self._collection_path = filepath
            self._collection_loaded = True
            logger.info(
                f"Loaded collection from {filepath} with {len(self._collection)} unique cards"
            )
            return True

        except Exception as exc:
            logger.error(f"Failed to load collection: {exc}")
            return False

    def get_owned_status(self, name: str, required: int) -> tuple[str, tuple[int, int, int]]:
        """
        Return ownership status text and color for a given card requirement.

        Args:
            name: Card name
            required: Quantity needed

        Returns:
            Tuple containing the status label and RGB color tuple (R, G, B)
        """
        collection_inventory = self.get_inventory()
        if not collection_inventory:
            return ("Owned —", (185, 191, 202))  # Subdued text color
        have = collection_inventory.get(name.lower(), 0)
        if have >= required:
            return (f"Owned {have}/{required}", (120, 200, 120))  # Green
        if have > 0:
            return (f"Owned {have}/{required}", (230, 200, 90))  # Yellow/Orange
        return ("Owned 0", (230, 120, 120))  # Red

    def find_latest_cached_file(
        self, directory: Path, pattern: str = "collection_full_trade_*.json"
    ) -> Path | None:
        """
        Find the most recent cached collection file.

        Args:
            directory: Directory to search for collection files
            pattern: Glob pattern for collection files

        Returns:
            Path to latest file, or None if none found
        """
        return find_latest_cached_file(directory, pattern)

    def load_from_cached_file(
        self, directory: Path, pattern: str = "collection_full_trade_*.json"
    ) -> dict[str, Any]:
        """
        Load collection from the most recent cached file.

        Args:
            directory: Directory to search for collection files
            pattern: Glob pattern for collection files

        Returns:
            Dictionary containing: filepath, mapping, age_hours, card_count

        Raises:
            FileNotFoundError: If no cached collection files found
            ValueError: If file cannot be parsed or is invalid
        """
        latest = self.find_latest_cached_file(directory, pattern)

        if not latest:
            self.clear_inventory()
            raise FileNotFoundError("No cached collection files found")

        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            mapping = build_inventory(data)

            self.set_inventory(mapping)
            self.set_collection_path(latest)

            # Calculate file age
            age_hours = get_file_age_hours(latest)

            logger.info(
                f"Loaded collection from cache: {len(mapping)} unique cards from {latest.name}"
            )

            return {
                "filepath": latest,
                "mapping": mapping,
                "age_hours": age_hours,
                "card_count": len(mapping),
            }
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(f"Failed to load cached collection {latest}: {exc}")
            self.clear_inventory()
            raise ValueError(f"Failed to parse collection file {latest.name}") from exc

    def load_cached_status(
        self, directory: Path, pattern: str = "collection_full_trade_*.json"
    ) -> CollectionStatus:
        """
        Load cached collection info and return display-friendly metadata.

        Args:
            directory: Directory to search for collection files
            pattern: Glob pattern for collection files

        Returns:
            CollectionStatus with formatted label and metadata

        Raises:
            FileNotFoundError: If no cached collection files found
            ValueError: If file cannot be parsed or is invalid
        """
        info = self.load_from_cached_file(directory, pattern)
        age_hours = info["age_hours"]
        age_str = f"{age_hours}h ago" if age_hours > 0 else "recent"
        label = f"Collection: {info['filepath'].name} ({info['card_count']} entries, {age_str})"
        return CollectionStatus(
            label=label,
            filepath=info["filepath"],
            card_count=info["card_count"],
            age_hours=age_hours,
        )

    def load_from_card_list(
        self, cards: list[dict[str, Any]], filepath: Path | None = None
    ) -> dict[str, Any]:
        """
        Load collection from a list of card dictionaries.

        Args:
            cards: List of card dicts with 'name' and 'quantity' keys
            filepath: Optional path to associate with this collection

        Returns:
            Dictionary containing: mapping, card_count

        Raises:
            ValueError: If card list is invalid or cannot be parsed
        """
        try:
            mapping = build_inventory(cards)

            self.set_inventory(mapping)
            if filepath:
                self.set_collection_path(filepath)

            logger.info(f"Loaded collection from card list: {len(mapping)} unique cards")

            return {
                "mapping": mapping,
                "card_count": len(mapping),
            }
        except (KeyError, TypeError, ValueError) as exc:
            logger.error(f"Failed to load collection from card list: {exc}")
            raise ValueError("Failed to parse card list") from exc

    def export_to_file(
        self,
        cards: list[dict[str, Any]],
        directory: Path,
        filename_prefix: str = "collection_full_trade",
    ) -> Path:
        """
        Export collection cards to a JSON file.

        Args:
            cards: List of card dicts to export
            directory: Directory to write file to
            filename_prefix: Prefix for the filename (timestamp will be added)

        Returns:
            Path to the exported file

        Raises:
            OSError: If file cannot be written
            ValueError: If cards list is invalid
        """
        try:
            directory.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.json"
            filepath = directory / filename

            with filepath.open("w", encoding="utf-8") as f:
                json.dump(cards, f, indent=2)

            logger.info(f"Exported collection to {filepath} ({len(cards)} cards)")
            return filepath
        except OSError as exc:
            logger.error(f"Failed to export collection: {exc}")
            raise
        except (TypeError, ValueError) as exc:
            logger.error(f"Invalid card data for export: {exc}")
            raise ValueError("Invalid card data for export") from exc

    # ============= Async Collection Refresh =============

    def refresh_from_bridge_async(
        self,
        directory: Path,
        force: bool = False,
        on_success: Callable[[Path, list], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        cache_max_age_seconds: int = COLLECTION_CACHE_MAX_AGE_SECONDS,
    ) -> bool:
        """
        Fetch collection from MTGO Bridge and export to file (async).

        This method runs in a background thread and uses callbacks to report results.
        It will check for a recent cached collection first (unless forced).

        Args:
            directory: Directory to save collection file to
            force: If True, always fetch from bridge (skip cache check)
            on_success: Callback for successful fetch (receives filepath, cards)
            on_error: Callback for failed fetch (receives error message)
            cache_max_age_seconds: Max age of cached file before fetching new (default 1 hour)

        Returns:
            True if fetch was started, False if recent cache was used
        """
        from utils import mtgo_bridge

        # Check if we have a recent cached collection (unless forced)
        if not force:
            latest = self.find_latest_cached_file(directory)
            if latest:
                try:
                    file_age_seconds = datetime.now().timestamp() - latest.stat().st_mtime
                    if file_age_seconds < cache_max_age_seconds:
                        logger.info(
                            f"Using cached collection ({file_age_seconds:.0f}s old, max {cache_max_age_seconds}s)"
                        )
                        # Load from cache and call success callback
                        info = self.load_from_cached_file(directory)
                        if on_success:
                            on_success(info["filepath"], [])  # Empty cards list for cache hits
                        return False  # Didn't start new fetch
                except Exception as exc:
                    logger.warning(f"Failed to check collection file age: {exc}")

        # Fetch fresh collection from MTGO Bridge in background
        def worker():
            try:
                # Call the bridge to get collection
                collection_data = mtgo_bridge.get_collection_snapshot(timeout=60.0)

                if not collection_data:
                    if on_error:
                        on_error("Bridge returned empty collection")
                    return

                # Get cards from bridge response
                cards = collection_data.get("cards", [])
                if not cards:
                    if on_error:
                        on_error("No cards in collection data")
                    return

                # Export to file using service
                filepath = self.export_to_file(cards, directory)

                # Call success callback
                if on_success:
                    on_success(filepath, cards)

            except FileNotFoundError as exc:
                logger.error(f"Bridge not found: {exc}")
                if on_error:
                    on_error("MTGO Bridge not found. Build the bridge executable.")

            except Exception as exc:
                logger.exception("Failed to fetch collection from bridge")
                if on_error:
                    on_error(str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return True  # Started new fetch

    def is_loaded(self) -> bool:
        """Check if collection has been loaded."""
        return self._collection_loaded

    def get_collection_size(self) -> int:
        """Get the number of unique cards in collection."""
        return len(self._collection)

    def get_total_cards(self) -> int:
        """Get the total number of cards (including duplicates) in collection."""
        return sum(self._collection.values())

    # ============= Ownership Checking =============

    def owns_card(self, card_name: str, required_count: int = 1) -> bool:
        """
        Check if player owns enough copies of a card.

        Args:
            card_name: Name of the card
            required_count: Number of copies needed

        Returns:
            True if owns enough copies, False otherwise
        """
        owned = self.get_owned_count(card_name)
        return owned >= required_count

    def get_owned_count(self, card_name: str) -> int:
        """
        Get the number of copies owned of a card.

        Args:
            card_name: Name of the card

        Returns:
            Number of copies owned
        """
        if card_name in self._collection:
            return self._collection[card_name]
        return self._collection.get(card_name.lower(), 0)

    def get_ownership_status(
        self, card_name: str, required: int
    ) -> tuple[str, tuple[int, int, int]]:
        """
        Get ownership status for a card.

        Args:
            card_name: Name of the card
            required: Number required

        Returns:
            Tuple of (status_text, color_rgb)
            status_text: "X/Y" where X is owned and Y is required
            color_rgb: RGB tuple for display color
        """
        owned = self.get_owned_count(card_name)

        if owned >= required:
            # Green - fully owned
            return f"{owned}/{required}", (0, 180, 0)
        elif owned > 0:
            # Orange - partially owned
            return f"{owned}/{required}", (255, 140, 0)
        else:
            # Red - not owned
            return f"0/{required}", (200, 0, 0)

    # ============= Deck Analysis =============

    def analyze_deck_ownership(self, deck_text: str) -> dict[str, Any]:
        """
        Analyze what cards from a deck are owned.

        Args:
            deck_text: Deck list as text

        Returns:
            Dictionary with ownership analysis:
                - total_unique: int - total unique cards in deck
                - fully_owned: int - cards fully owned
                - partially_owned: int - cards partially owned
                - not_owned: int - cards not owned
                - missing_cards: list of (card_name, owned, needed) tuples
                - ownership_percentage: float - percentage fully owned
        """
        card_requirements: dict[str, int] = {}

        # Parse deck to get requirements
        for line in deck_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                parts = line.split(" ", 1)
                if len(parts) < 2:
                    continue

                count = int(float(parts[0]))
                card_name = parts[1].strip()

                # Remove "Sideboard " prefix if present
                if card_name.startswith("Sideboard "):
                    card_name = card_name[10:]

                card_requirements[card_name] = card_requirements.get(card_name, 0) + count

            except (ValueError, IndexError):
                continue

        # Analyze ownership
        fully_owned = 0
        partially_owned = 0
        not_owned = 0
        missing_cards = []

        for card_name, needed in card_requirements.items():
            owned = self.get_owned_count(card_name)

            if owned >= needed:
                fully_owned += 1
            elif owned > 0:
                partially_owned += 1
                missing_cards.append((card_name, owned, needed))
            else:
                not_owned += 1
                missing_cards.append((card_name, 0, needed))

        total_unique = len(card_requirements)
        ownership_percentage = (fully_owned / total_unique * 100) if total_unique > 0 else 0.0

        return {
            "total_unique": total_unique,
            "fully_owned": fully_owned,
            "partially_owned": partially_owned,
            "not_owned": not_owned,
            "missing_cards": missing_cards,
            "ownership_percentage": ownership_percentage,
        }

    def get_missing_cards_list(self, deck_text: str) -> list[tuple[str, int]]:
        """
        Get a list of missing cards for a deck.

        Args:
            deck_text: Deck list as text

        Returns:
            List of (card_name, missing_count) tuples
        """
        analysis = self.analyze_deck_ownership(deck_text)
        missing = []

        for card_name, owned, needed in analysis["missing_cards"]:
            missing_count = needed - owned
            if missing_count > 0:
                missing.append((card_name, missing_count))

        return missing

    # ============= Collection Statistics =============

    def get_collection_statistics(self) -> dict[str, Any]:
        """
        Get statistics about the collection.

        Returns:
            Dictionary with collection statistics
        """
        if not self._collection_loaded:
            return {
                "loaded": False,
                "message": "Collection not loaded",
            }

        total_cards = self.get_total_cards()
        unique_cards = self.get_collection_size()

        # Calculate rarity distribution if card data is available
        rarity_counts: dict[str, int] = {}

        for card_name, count in self._collection.items():
            # Try to get card metadata
            metadata = self.card_repo.get_card_metadata(card_name)
            if metadata:
                rarity = metadata.get("rarity", "unknown")
                rarity_counts[rarity] = rarity_counts.get(rarity, 0) + count

        return {
            "loaded": True,
            "unique_cards": unique_cards,
            "total_cards": total_cards,
            "average_copies": total_cards / unique_cards if unique_cards > 0 else 0,
            "rarity_distribution": rarity_counts,
        }

    # ============= Collection Updates =============

    def add_cards(self, card_name: str, count: int) -> None:
        """
        Add cards to the collection.

        Args:
            card_name: Name of the card
            count: Number to add
        """
        if count <= 0:
            return

        current = self._collection.get(card_name, 0)
        self._collection[card_name] = current + count
        logger.debug(f"Added {count}x {card_name} to collection (now {current + count})")

    def remove_cards(self, card_name: str, count: int) -> None:
        """
        Remove cards from the collection.

        Args:
            card_name: Name of the card
            count: Number to remove
        """
        if count <= 0:
            return

        current = self._collection.get(card_name, 0)
        new_count = max(0, current - count)

        if new_count == 0:
            self._collection.pop(card_name, None)
        else:
            self._collection[card_name] = new_count

        logger.debug(f"Removed {count}x {card_name} from collection (now {new_count})")

    def set_card_count(self, card_name: str, count: int) -> None:
        """
        Set the count for a specific card.

        Args:
            card_name: Name of the card
            count: New count
        """
        if count <= 0:
            self._collection.pop(card_name, None)
        else:
            self._collection[card_name] = count

        logger.debug(f"Set {card_name} count to {count}")

    # ============= State Access Methods =============

    def get_inventory(self) -> dict[str, int]:
        """
        Get the collection inventory dictionary.

        Returns:
            Dictionary mapping card names (lowercase) to quantities
        """
        return self._collection

    def set_inventory(self, inventory: dict[str, int]) -> None:
        """
        Set the collection inventory dictionary directly.

        Args:
            inventory: Dictionary mapping card names to quantities
        """
        self._collection = inventory
        self._collection_loaded = True

    def clear_inventory(self) -> None:
        """Clear the collection inventory."""
        self._collection = {}
        self._collection_path = None
        self._collection_loaded = False

    def get_collection_path(self) -> Path | None:
        """
        Get the path to the currently loaded collection file.

        Returns:
            Path to collection file, or None if not loaded from file
        """
        return self._collection_path

    def set_collection_path(self, path: Path | None) -> None:
        """
        Set the path to the collection file.

        Args:
            path: Path to collection file
        """
        self._collection_path = path


# Global instance for backward compatibility
_default_service = None


def get_collection_service() -> CollectionService:
    """Get the default collection service instance."""
    global _default_service
    if _default_service is None:
        _default_service = CollectionService()
    return _default_service


def reset_collection_service() -> None:
    """
    Reset the global collection service instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_service
    _default_service = None


__all__ = [
    "CollectionService",
    "CollectionStatus",
    "get_collection_service",
    "reset_collection_service",
]
