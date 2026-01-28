"""
Card Repository - Data access layer for card information.

This module handles all card-related data access including:
- Card metadata lookup
- Card image fetching
- Bulk data management
- Printing information
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from utils.card_data import CardDataManager
from utils.card_images import (
    BULK_DATA_CACHE,
    BulkImageDownloader,
    ensure_printing_index_cache,
    get_card_image,
)


class CardRepository:
    """Repository for card data access operations and card data state management."""

    def __init__(self, card_data_manager: CardDataManager | None = None):
        """
        Initialize the card repository.

        Args:
            card_data_manager: CardDataManager instance. If None, creates a new one.
        """
        self._card_data_manager = card_data_manager

        # State management for UI layer
        self._card_data_loading: bool = False
        self._card_data_ready: bool = False

    @property
    def card_data_manager(self) -> CardDataManager:
        """Get or create the CardDataManager instance."""
        if self._card_data_manager is None:
            self._card_data_manager = CardDataManager()
        return self._card_data_manager

    # ============= Card Metadata Operations =============

    def get_card_metadata(self, card_name: str) -> dict[str, Any] | None:
        """
        Get metadata for a specific card.

        Args:
            card_name: Name of the card

        Returns:
            Dictionary with card metadata or None if not found
        """
        try:
            # Get card info from the manager
            card_info = self.card_data_manager.get_card(card_name)
            return card_info
        except RuntimeError as exc:
            # Card data not loaded yet
            logger.warning(f"Card data not loaded: {exc}")
            return None
        except Exception as exc:
            logger.warning(f"Failed to get metadata for {card_name}: {exc}")
            return None

    def search_cards(
        self,
        query: str | None = None,
        colors: list[str] | None = None,
        types: list[str] | None = None,
        mana_value: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for cards matching criteria.

        Args:
            query: Text search query
            colors: List of color codes (e.g., ['W', 'U'])
            types: List of card types to filter by
            mana_value: Specific mana value to match

        Returns:
            List of matching card dictionaries
        """
        try:
            # Use the card data manager's search functionality
            results = self.card_data_manager.search_cards(
                query=query or "", color_identity=colors, type_filter=types
            )
            return results
        except RuntimeError as exc:
            # Card data not loaded yet
            logger.warning(f"Card data not loaded: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Failed to search cards: {exc}")
            return []

    def is_card_data_loaded(self) -> bool:
        """Check if card data has been loaded."""
        return self.card_data_manager._cards is not None

    def load_card_data(self, force: bool = False) -> bool:
        """
        Load card data into memory.

        Args:
            force: If True, reload even if already loaded

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not force and self.card_data_manager._cards is not None:
                return True

            self.card_data_manager.ensure_latest(force=force)
            return True
        except Exception as exc:
            logger.error(f"Failed to load card data: {exc}")
            return False

    # ============= Card Image Operations =============

    def get_card_image_path(self, card_name: str, set_code: str | None = None) -> Path | None:
        """
        Get the file path for a card image.

        Args:
            card_name: Name of the card
            set_code: Specific set code (unused -- image lookup is name-based)

        Returns:
            Path to the image file or None if not found
        """
        try:
            image_path = get_card_image(card_name)
            return image_path
        except Exception as exc:
            logger.warning(f"Failed to get image for {card_name}: {exc}")
            return None

    def get_card_printings(self, card_name: str) -> list[dict[str, Any]]:
        """
        Get all printings for a specific card.

        Args:
            card_name: Name of the card

        Returns:
            List of printing dictionaries with set info
        """
        try:
            # Use the card data manager to get printings
            printings = self.card_data_manager.get_printings(card_name)
            return printings or []
        except Exception as exc:
            logger.warning(f"Failed to get printings for {card_name}: {exc}")
            return []

    def ensure_printing_cache(self) -> bool:
        """
        Ensure the printing index cache is available.

        Returns:
            True if cache is ready, False otherwise
        """
        try:
            ensure_printing_index_cache()
            return True
        except Exception as exc:
            logger.error(f"Failed to ensure printing cache: {exc}")
            return False

    # ============= Bulk Data Operations =============

    def is_bulk_data_cached(self) -> bool:
        """
        Check if bulk card data is cached locally.

        Returns:
            True if bulk data cache exists
        """
        return BULK_DATA_CACHE.exists()

    def download_bulk_data(self, callback: Callable | None = None) -> bool:
        """
        Download bulk card data.

        Args:
            callback: Optional callback function for progress updates

        Returns:
            True if successful, False otherwise
        """
        try:
            downloader = BulkImageDownloader()
            # This would need to be adapted based on actual BulkImageDownloader API
            # For now, just attempt the download
            success = downloader.download_bulk_data(callback=callback)
            return success
        except Exception as exc:
            logger.error(f"Failed to download bulk data: {exc}")
            return False

    def get_bulk_cache_info(self) -> dict[str, Any]:
        """
        Get information about the bulk data cache.

        Returns:
            Dictionary with cache information (size, last_modified, etc.)
        """
        if not BULK_DATA_CACHE.exists():
            return {"exists": False}

        try:
            stat = BULK_DATA_CACHE.stat()
            return {
                "exists": True,
                "size_bytes": stat.st_size,
                "size_mb": stat.st_size / (1024 * 1024),
                "last_modified": stat.st_mtime,
            }
        except OSError as exc:
            logger.warning(f"Failed to get cache info: {exc}")
            return {"exists": True, "error": str(exc)}

    # ============= Collection/Inventory Operations =============

    def load_collection_from_file(self, filepath: Path) -> list[dict[str, Any]]:
        """
        Load a collection from a file.

        Args:
            filepath: Path to the collection file

        Returns:
            List of card dictionaries with quantities
        """

        def _extract_cards(payload: Any) -> list[Any]:
            """Return the most likely card list from the payload."""
            if isinstance(payload, list):
                return payload

            if isinstance(payload, dict):
                for key in ("cards", "items"):
                    candidate = payload.get(key)
                    if isinstance(candidate, list):
                        return candidate

                collection = payload.get("collection")
                if collection is not None:
                    return _extract_cards(collection)

            return []

        try:
            raw_data = filepath.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.info(f"Collection file {filepath} does not exist")
            return []
        except OSError as exc:
            logger.error(f"Unable to read collection file {filepath}: {exc}")
            return []

        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            logger.error(f"Invalid JSON in collection file {filepath}: {exc}")
            return []

        card_entries = _extract_cards(payload)
        if not card_entries:
            logger.warning(f"No card entries found in collection file {filepath}")
            return []

        parsed_cards: list[dict[str, Any]] = []
        for entry in card_entries:
            if not isinstance(entry, dict):
                continue

            name = str(entry.get("name", "")).strip()
            if not name:
                continue

            quantity_raw = entry.get("quantity", 0)
            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                try:
                    quantity = int(float(quantity_raw))
                except (TypeError, ValueError):
                    logger.debug(f"Skipping {name}: invalid quantity {quantity_raw!r}")
                    continue

            if quantity < 0:
                logger.debug(f"Skipping {name}: negative quantity {quantity}")
                continue

            normalized: dict[str, Any] = {"name": name, "quantity": quantity}
            if "id" in entry:
                normalized["id"] = entry.get("id")

            parsed_cards.append(normalized)

        logger.info(f"Loaded {len(parsed_cards)} cards from {filepath}")
        return parsed_cards

    def get_collection_cache_path(self) -> Path:
        """
        Get the path to the collection cache file.

        Returns:
            Path to collection cache
        """
        from utils.constants import CACHE_DIR

        return CACHE_DIR / "collection.json"

    # ============= Card Data State Management (for UI layer) =============

    def is_card_data_loading(self) -> bool:
        """Check if card data is currently loading."""
        return self._card_data_loading

    def set_card_data_loading(self, loading: bool) -> None:
        """Set the card data loading state."""
        self._card_data_loading = loading

    def is_card_data_ready(self) -> bool:
        """Check if card data is ready for use."""
        return self._card_data_ready

    def set_card_data_ready(self, ready: bool) -> None:
        """Set the card data ready state."""
        self._card_data_ready = ready

    def get_card_manager(self) -> CardDataManager | None:
        """Get the CardDataManager instance."""
        return self._card_data_manager

    def set_card_manager(self, manager: CardDataManager | None) -> None:
        """Set the CardDataManager instance."""
        self._card_data_manager = manager
        if manager is not None:
            self._card_data_ready = True

    def ensure_card_data_loaded(self, force: bool = False) -> CardDataManager:
        """
        Ensure that card data is available, loading it if necessary.

        Args:
            force: If True, force reload even if already loaded

        Returns:
            Initialized CardDataManager
        """
        if not force and self._card_data_manager is not None:
            return self._card_data_manager

        from utils.card_data import load_card_manager

        manager = load_card_manager()
        self.set_card_manager(manager)
        return manager


# Global instance for backward compatibility
_default_repository = None


def get_card_repository() -> CardRepository:
    """Get the default card repository instance."""
    global _default_repository
    if _default_repository is None:
        _default_repository = CardRepository()
    return _default_repository


def reset_card_repository() -> None:
    """
    Reset the global card repository instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_repository
    _default_repository = None
