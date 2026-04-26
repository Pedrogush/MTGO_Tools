"""On-demand printings metadata lookups."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.card_images import BulkImageDownloader

if TYPE_CHECKING:
    from services.image_service.protocol import ImageServiceProto

    _Base = ImageServiceProto
else:
    _Base = object


class PrintingsFetchMixin(_Base):
    """Fetch printings metadata for individual cards on demand."""

    def fetch_printings_by_name_async(self, card_name: str) -> None:
        key = card_name.lower().strip()
        if not key:
            return
        with self._printings_lock:
            if key in self._printings_inflight:
                return
            self._printings_inflight.add(key)

        def worker() -> tuple[str, list[dict[str, Any]]]:
            downloader = self.image_downloader or BulkImageDownloader(self.image_cache)
            printings = downloader.fetch_printings_by_name(card_name)
            mapped = [
                {
                    "id": printing.get("id"),
                    "set": (printing.get("set") or "").upper(),
                    "set_name": printing.get("set_name") or "",
                    "collector_number": printing.get("collector_number") or "",
                    "released_at": printing.get("released_at") or "",
                }
                for printing in printings
                if printing.get("id")
            ]
            return card_name, mapped

        def success_handler(result: tuple[str, list[dict[str, Any]]]) -> None:
            name, mapped = result
            with self._printings_lock:
                self._printings_inflight.discard(key)
            if self._on_printings_loaded:
                self._call_after(self._on_printings_loaded, name, mapped)

        def error_handler(exc: Exception) -> None:
            with self._printings_lock:
                self._printings_inflight.discard(key)
            logger.error(f"Failed to fetch printings for {card_name}: {exc}")

        def run_task() -> None:
            self._run_printings_task(worker, success_handler, error_handler)

        threading.Thread(target=run_task, daemon=True).start()

    @staticmethod
    def _run_printings_task(
        worker: Callable[[], tuple[str, list[dict[str, Any]]]],
        on_success: Callable[[tuple[str, list[dict[str, Any]]]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        try:
            result = worker()
        except Exception as exc:
            on_error(exc)
            return
        on_success(result)
