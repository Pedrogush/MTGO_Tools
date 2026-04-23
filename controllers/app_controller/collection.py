"""Collection cache loading and MTGO bridge refresh orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from utils.constants import COLLECTION_CACHE_MAX_AGE_SECONDS


class CollectionMixin:
    """Load the cached collection file and trigger bridge refreshes."""

    def load_collection_from_cache(self, directory: Path) -> tuple[bool, dict[str, Any] | None]:
        try:
            info = self.collection_service.load_from_cached_file(directory)
            return True, info
        except (FileNotFoundError, ValueError) as exc:
            logger.debug(f"Could not load collection from cache: {exc}")
            return False, None

    def refresh_collection_from_bridge(
        self, directory: Path | None = None, force: bool = False
    ) -> None:
        callbacks = self._ui_callbacks
        on_status = callbacks.on_status if callbacks else lambda msg: None
        on_success = callbacks.on_collection_refresh_success if callbacks else None
        on_error = callbacks.on_collection_failed if callbacks else None
        directory = directory or self.deck_save_dir

        on_status("app.status.fetching_collection")
        logger.info("Fetching collection from MTGO Bridge")

        self.collection_service.refresh_from_bridge_async(
            directory=directory,
            force=force,
            on_success=on_success,
            on_error=on_error,
            cache_max_age_seconds=COLLECTION_CACHE_MAX_AGE_SECONDS,
        )
