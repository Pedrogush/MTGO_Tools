"""Async refresh of the collection snapshot from the MTGO bridge."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from loguru import logger

from utils.constants import (
    COLLECTION_BRIDGE_TIMEOUT_SECONDS,
    COLLECTION_CACHE_MAX_AGE_SECONDS,
)


class BridgeRefreshMixin:
    """Fetch collection data from the MTGO bridge and write a cache file."""

    def refresh_from_bridge_async(
        self,
        directory: Path,
        force: bool = False,
        on_success: Callable[[Path, list], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        cache_max_age_seconds: int = COLLECTION_CACHE_MAX_AGE_SECONDS,
        fetch_collection: Callable[..., dict] | None = None,
    ) -> bool:
        # Runs in a background thread; reports results via on_success/on_error callbacks.
        # Returns False without fetching if a recent cached file exists (unless force=True).
        if fetch_collection is None:
            from utils import mtgo_bridge

            fetch_collection = mtgo_bridge.get_collection_snapshot

        if not force:
            latest = self.find_latest_cached_file(directory)
            if latest:
                try:
                    file_age_seconds = datetime.now().timestamp() - latest.stat().st_mtime
                    if file_age_seconds < cache_max_age_seconds:
                        logger.info(
                            "Using cached collection "
                            f"({file_age_seconds:.0f}s old, max {cache_max_age_seconds}s)"
                        )
                        info = self.load_from_cached_file(directory)
                        if on_success:
                            on_success(info["filepath"], [])
                        return False
                except Exception as exc:
                    logger.warning(f"Failed to check collection file age: {exc}")

        export_to_file = self.export_to_file

        def worker() -> None:
            try:
                collection_data = fetch_collection(timeout=COLLECTION_BRIDGE_TIMEOUT_SECONDS)

                if not collection_data:
                    if on_error:
                        on_error("Bridge returned empty collection")
                    return

                cards = collection_data.get("cards", [])
                if not cards:
                    if on_error:
                        on_error("No cards in collection data")
                    return

                filepath = export_to_file(cards, directory)

                if on_success:
                    on_success(filepath, cards)

            except FileNotFoundError as exc:
                logger.error(f"Bridge not found: {exc}")
                if on_error:
                    on_error("MTGO Bridge not found. Build the bridge executable.")

            except Exception as exc:
                logger.exception("Failed to fetch collection from bridge")
                if on_error:
                    on_error(str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return True
