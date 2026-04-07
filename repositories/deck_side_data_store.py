"""JSON side-data persistence for deck notes, outboards, and sideboard guides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import GUIDE_STORE, NOTES_STORE, OUTBOARD_STORE


class DeckSideDataStore:
    """Store for deck side-data keyed by deck identity."""

    def __init__(
        self,
        *,
        notes_store: Path = NOTES_STORE,
        outboard_store: Path = OUTBOARD_STORE,
        guide_store: Path = GUIDE_STORE,
    ) -> None:
        self.notes_store = notes_store
        self.outboard_store = outboard_store
        self.guide_store = guide_store

    def load_notes(self, deck_key: str) -> str:
        data = self._load_json_store(self.notes_store)
        return data.get(deck_key, "")

    def save_notes(self, deck_key: str, notes: str) -> None:
        data = self._load_json_store(self.notes_store)
        data[deck_key] = notes
        self._save_json_store(self.notes_store, data)

    def load_outboard(self, deck_key: str) -> list[dict[str, Any]]:
        data = self._load_json_store(self.outboard_store)
        return data.get(deck_key, [])

    def save_outboard(self, deck_key: str, outboard: list[dict[str, Any]]) -> None:
        data = self._load_json_store(self.outboard_store)
        data[deck_key] = outboard
        self._save_json_store(self.outboard_store, data)

    def load_sideboard_guide(self, deck_key: str) -> list[dict[str, Any]]:
        data = self._load_json_store(self.guide_store)
        return data.get(deck_key, [])

    def save_sideboard_guide(self, deck_key: str, guide: list[dict[str, Any]]) -> None:
        data = self._load_json_store(self.guide_store)
        data[deck_key] = guide
        self._save_json_store(self.guide_store, data)

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
