"""
Collection Service - Business logic for collection/inventory management.

This module contains all the business logic for managing card collections:
- Loading collection data
- Checking card ownership
- Calculating missing cards
- Collection statistics
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from repositories.card_repository import CardRepository, get_card_repository
from services.collection_bridge_refresh import refresh_from_bridge_async as refresh_from_bridge
from services.collection_cache import find_latest_cached_file, get_file_age_hours
from services.collection_deck_analysis import (
    analyze_deck_ownership as analyze_deck_ownership_helper,
)
from services.collection_deck_analysis import (
    get_missing_cards_list as get_missing_cards_list_helper,
)
from services.collection_exporter import export_collection_to_file
from services.collection_ownership import format_owned_status
from services.collection_parsing import build_inventory
from services.collection_stats import get_collection_statistics as get_collection_statistics_helper
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
        self.card_repo = card_repository or get_card_repository()
        self._collection: dict[str, int] = {}
        self._collection_path: Path | None = None
        self._collection_loaded = False

    # ============= Collection Loading =============

    def load_collection(self, filepath: Path | None = None, force: bool = False) -> bool:
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
            self._collection = build_inventory(cards, normalize_names=False)

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
        if not self.get_inventory():
            return ("Owned —", (185, 191, 202))  # Subdued text color
        have = self.get_owned_count(name)
        return format_owned_status(have, required)

    def find_latest_cached_file(
        self, directory: Path, pattern: str = "collection_full_trade_*.json"
    ) -> Path | None:
        return find_latest_cached_file(directory, pattern)

    def load_from_cached_file(
        self, directory: Path, pattern: str = "collection_full_trade_*.json"
    ) -> dict[str, Any]:
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
        return export_collection_to_file(cards, directory, filename_prefix)

    # ============= Async Collection Refresh =============

    def refresh_from_bridge_async(
        self,
        directory: Path,
        force: bool = False,
        on_success: Callable[[Path, list], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        cache_max_age_seconds: int = COLLECTION_CACHE_MAX_AGE_SECONDS,
    ) -> bool:
        # Runs in a background thread; reports results via on_success/on_error callbacks.
        # Returns False without fetching if a recent cached file exists (unless force=True).
        return refresh_from_bridge(
            directory=directory,
            force=force,
            on_success=on_success,
            on_error=on_error,
            cache_max_age_seconds=cache_max_age_seconds,
            load_from_cached_file=self.load_from_cached_file,
            export_to_file=self.export_to_file,
            find_latest_cached_file=self.find_latest_cached_file,
        )

    def is_loaded(self) -> bool:
        return self._collection_loaded

    def get_collection_size(self) -> int:
        return len(self._collection)

    def get_total_cards(self) -> int:
        return sum(self._collection.values())

    # ============= Ownership Checking =============

    def owns_card(self, card_name: str, required_count: int = 1) -> bool:
        owned = self.get_owned_count(card_name)
        return owned >= required_count

    def get_owned_count(self, card_name: str) -> int:
        if card_name in self._collection:
            return self._collection[card_name]
        return self._collection.get(card_name.lower(), 0)

    def get_ownership_status(
        self, card_name: str, required: int
    ) -> tuple[str, tuple[int, int, int]]:
        owned = self.get_owned_count(card_name)
        return format_owned_status(owned, required)

    # ============= Deck Analysis =============

    def analyze_deck_ownership(self, deck_text: str) -> dict[str, Any]:
        return analyze_deck_ownership_helper(deck_text, self.get_owned_count)

    def get_missing_cards_list(self, deck_text: str) -> list[tuple[str, int]]:
        return get_missing_cards_list_helper(deck_text, self.get_owned_count)

    # ============= Collection Statistics =============

    def get_collection_statistics(self) -> dict[str, Any]:
        return get_collection_statistics_helper(
            inventory=self._collection,
            card_repo=self.card_repo,
            is_loaded=self._collection_loaded,
        )

    # ============= State Access Methods =============

    def get_inventory(self) -> dict[str, int]:
        return self._collection

    def set_inventory(self, inventory: dict[str, int]) -> None:
        self._collection = inventory
        self._collection_loaded = True

    def clear_inventory(self) -> None:
        self._collection = {}
        self._collection_path = None
        self._collection_loaded = False

    def get_collection_path(self) -> Path | None:
        return self._collection_path

    def set_collection_path(self, path: Path | None) -> None:
        self._collection_path = path


# Global instance for backward compatibility
_default_service = None


def get_collection_service() -> CollectionService:
    global _default_service
    if _default_service is None:
        _default_service = CollectionService()
    return _default_service


def reset_collection_service() -> None:
    """Reset the global collection service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "CollectionService",
    "CollectionStatus",
    "get_collection_service",
    "reset_collection_service",
]
