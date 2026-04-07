"""
Card Repository - Data access layer for card information.

This module handles all card-related data access including:
- Card metadata lookup
- Card image fetching
- Bulk data management
- Printing information
"""

from pathlib import Path
from typing import Any

import msgspec
import msgspec.json
from loguru import logger

from utils.card_data import CardDataManager

# ---------------------------------------------------------------------------
# msgspec schema for collection files
# ---------------------------------------------------------------------------


class _CollectionEntry(msgspec.Struct, gc=False):
    # Only the three fields we actually need; all other keys in the JSON object
    # are silently ignored by msgspec.
    name: str
    quantity: float  # Accept int or float; we coerce to int after decoding.
    id: Any = None  # Optional UUID / numeric card ID


_collection_any_decoder: msgspec.json.Decoder[Any] = msgspec.json.Decoder(Any)


class CardRepository:
    """Repository for card data access operations and card data state management."""

    def __init__(self, card_data_manager: CardDataManager | None = None):
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
        try:
            card_info = self.card_data_manager.get_card(card_name)
            return card_info
        except RuntimeError as exc:
            # Card data not loaded yet
            logger.debug(f"Card data not loaded: {exc}")
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
        try:
            results = self.card_data_manager.search_cards(
                query=query or "", color_identity=colors, type_filter=types
            )
            return results
        except RuntimeError as exc:
            logger.warning(f"Card data not loaded: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Failed to search cards: {exc}")
            return []

    def is_card_data_loaded(self) -> bool:
        return self._card_data_manager is not None and self._card_data_manager.is_loaded

    # ============= Collection/Inventory Operations =============

    def load_collection_from_file(self, filepath: Path) -> list[dict[str, Any]]:
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
            raw_data = filepath.read_bytes()
        except FileNotFoundError:
            logger.info(f"Collection file {filepath} does not exist")
            return []
        except OSError as exc:
            logger.error(f"Unable to read collection file {filepath}: {exc}")
            return []

        # Decode the outer wrapper (may be a list or a dict with a nested list)
        # using the untyped Any decoder so the existing _extract_cards logic works.
        try:
            payload = _collection_any_decoder.decode(raw_data)
        except msgspec.DecodeError as exc:
            logger.error(f"Invalid JSON in collection file {filepath}: {exc}")
            return []

        raw_entries = _extract_cards(payload)
        if not raw_entries:
            logger.warning(f"No card entries found in collection file {filepath}")
            return []

        parsed_cards: list[dict[str, Any]] = []
        for entry in raw_entries:
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
        from utils.constants import CACHE_DIR

        return CACHE_DIR / "collection.json"

    # ============= Card Data State Management (for UI layer) =============

    def is_card_data_loading(self) -> bool:
        return self._card_data_loading

    def set_card_data_loading(self, loading: bool) -> None:
        self._card_data_loading = loading

    def is_card_data_ready(self) -> bool:
        return self._card_data_ready

    def set_card_data_ready(self, ready: bool) -> None:
        self._card_data_ready = ready

    def get_card_manager(self) -> CardDataManager | None:
        return self._card_data_manager

    def set_card_manager(self, manager: CardDataManager | None) -> None:
        self._card_data_manager = manager
        if manager is not None:
            self._card_data_ready = True

    def ensure_card_data_loaded(self, force: bool = False) -> CardDataManager:
        if not force and self._card_data_manager is not None and self._card_data_manager.is_loaded:
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
    """Reset the global card repository (use in tests for isolation)."""
    global _default_repository
    _default_repository = None
