"""Per-deck notes / outboard / sideboard-guide JSON stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import GUIDE_STORE, NOTES_STORE, OUTBOARD_STORE


class MetadataStoreMixin:
    """Load/save per-deck notes, outboard cards, and sideboard guides."""

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
