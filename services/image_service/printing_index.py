"""Printing index loading and state management."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.card_images import (
    BULK_DATA_CACHE,
    PRINTING_INDEX_CACHE,
    PRINTING_INDEX_VERSION,
    load_printing_index_payload,
)
from utils.card_images_workers import build_printing_index_worker

if TYPE_CHECKING:
    from services.image_service.protocol import ImageServiceProto

    _Base = ImageServiceProto
else:
    _Base = object


class PrintingIndexMixin(_Base):
    """Load and track the printing index in the background."""

    def load_printing_index_async(
        self,
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> bool:
        if self.printing_index_loading and not force:
            logger.debug("Printing index already loading")
            return False

        if self.bulk_data_by_name and not force:
            logger.debug("Printing index already loaded")
            return False

        self.printing_index_loading = True

        existing = None if force else load_printing_index_payload()
        bulk_mtime = BULK_DATA_CACHE.stat().st_mtime if BULK_DATA_CACHE.exists() else None
        if existing and (bulk_mtime is None or existing.get("bulk_mtime", 0) >= bulk_mtime):
            data = existing.get("data", {})
            stats = {
                "unique_names": existing.get("unique_names", len(data)),
                "total_printings": existing.get(
                    "total_printings", sum(len(v) for v in data.values())
                ),
            }
            on_success(data, stats)
            return True

        if self._printings_handle and self._printings_handle.process.is_alive():
            logger.debug("Printing index process already running")
            return False

        def _on_success(result: dict[str, Any]) -> None:
            payload = load_printing_index_payload()
            if not payload:
                on_error("Printings index cache missing after build.")
                return
            data = payload.get("data", {})
            stats = {
                "unique_names": payload.get("unique_names", len(data)),
                "total_printings": payload.get(
                    "total_printings", sum(len(v) for v in data.values())
                ),
            }
            on_success(data, stats)

        def _on_error(msg: str) -> None:
            on_error(msg)

        try:
            self._printings_handle = self._process_worker.run_async(
                target=build_printing_index_worker,
                args=(),
                kwargs={
                    "bulk_data_path": str(BULK_DATA_CACHE),
                    "printings_path": str(PRINTING_INDEX_CACHE),
                    "printings_version": PRINTING_INDEX_VERSION,
                },
                on_success=_on_success,
                on_error=_on_error,
                call_after=self._call_after,
            )
        except Exception as exc:
            logger.exception("Failed to start printings index process")
            on_error(str(exc))
            self.printing_index_loading = False
            return False

        return True

    def set_bulk_data(self, bulk_data: dict[str, list[dict[str, Any]]]) -> None:
        self.bulk_data_by_name = bulk_data

    def clear_printing_index_loading(self) -> None:
        self.printing_index_loading = False

    def get_bulk_data(self) -> dict[str, list[dict[str, Any]]] | None:
        return self.bulk_data_by_name

    def is_loading(self) -> bool:
        return self.printing_index_loading
