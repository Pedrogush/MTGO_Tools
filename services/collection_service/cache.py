"""Collection cache discovery and loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from services.collection_service.parsing import build_inventory
from utils.constants import ONE_HOUR_SECONDS


@dataclass(frozen=True)
class CollectionStatus:
    """Display-friendly collection metadata."""

    label: str
    filepath: Path
    card_count: int
    age_hours: int


class CollectionCacheMixin:
    """Discover, load and expose cached collection files."""

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

    def find_latest_cached_file(
        self, directory: Path, pattern: str = "collection_full_trade_*.json"
    ) -> Path | None:
        files = sorted(directory.glob(pattern))
        return files[-1] if files else None

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
            file_age_seconds = datetime.now().timestamp() - latest.stat().st_mtime
            age_hours = int(file_age_seconds / ONE_HOUR_SECONDS)

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

    # ============= State Access =============

    def is_loaded(self) -> bool:
        return self._collection_loaded

    def get_collection_size(self) -> int:
        return len(self._collection)

    def get_total_cards(self) -> int:
        return sum(self._collection.values())

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
