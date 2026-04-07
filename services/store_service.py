"""Utility service for simple JSON-backed key/value stores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.json_io import fast_load


class StoreService:
    """Service that reads and writes lightweight JSON stores."""

    def load_store(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with locked_path(path):
                return fast_load(path)
        except Exception as exc:
            if isinstance(exc, OSError):
                logger.warning(f"Failed to read {path}: {exc}")
            else:
                logger.warning(f"Invalid JSON at {path}; ignoring store")
            return {}

    def save_store(self, path: Path, data: dict[str, Any]) -> None:
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
