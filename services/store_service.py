"""Utility service for simple JSON-backed key/value stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path


class StoreService:
    """Service that reads and writes lightweight JSON stores."""

    def load_store(self, path: Path) -> dict[str, Any]:
        """
        Load JSON data from the given path.

        Args:
            path: Path to the JSON store

        Returns:
            Dictionary payload (empty dict if unreadable)
        """
        if not path.exists():
            return {}
        try:
            with locked_path(path):
                return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON at {path}; ignoring store")
            return {}
        except OSError as exc:
            logger.warning(f"Failed to read {path}: {exc}")
            return {}

    def save_store(self, path: Path, data: dict[str, Any]) -> None:
        """
        Persist JSON data to the given path.

        Args:
            path: Path to write
            data: Dictionary payload
        """
        try:
            atomic_write_json(path, data, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.warning(f"Failed to write {path}: {exc}")


_default_store_service: StoreService | None = None


def get_store_service() -> StoreService:
    """Return a shared StoreService instance."""
    global _default_store_service
    if _default_store_service is None:
        _default_store_service = StoreService()
    return _default_store_service
