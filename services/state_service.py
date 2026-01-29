from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from utils import constants
from utils.atomic_io import atomic_write_json, locked_path
from utils.deck import sanitize_zone_cards


class StateService:
    """Load and persist application window state/settings."""

    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = settings_path or constants.DECK_SELECTOR_SETTINGS_FILE

    def load(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return {}
        try:
            with locked_path(self.settings_path):
                with self.settings_path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive logging
            logger.warning(f"Failed to load deck selector settings: {exc}")
            return {}

    def save(self, data: dict[str, Any]) -> None:
        try:
            atomic_write_json(self.settings_path, data, indent=2)
        except OSError as exc:  # pragma: no cover - defensive logging
            logger.warning(f"Unable to persist deck selector settings: {exc}")

    @staticmethod
    def coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def clamp_bulk_cache_age(
        value: Any,
        *,
        default_days: int,
        min_days: int,
        max_days: int,
    ) -> int:
        try:
            days = int(float(value))
        except (TypeError, ValueError):
            days = default_days
        return max(min_days, min(days, max_days))

    @staticmethod
    def serialize_zone_cards(
        zone_cards: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        return {zone: sanitize_zone_cards(cards) for zone, cards in zone_cards.items()}

    @staticmethod
    def deserialize_zone_cards(value: Any) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(value, dict):
            return {}
        restored: dict[str, list[dict[str, Any]]] = {}
        for zone, entries in value.items():
            if not isinstance(entries, list):
                continue
            sanitized = sanitize_zone_cards(entries)
            if sanitized:
                restored[zone] = sanitized
        return restored


__all__ = ["StateService"]
