"""Deck download, text building, saving, and daily-average computation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto

    _Base = AppControllerProto
else:
    _Base = object


class DeckManagementMixin(_Base):
    """Per-deck download/save/build plus daily-average orchestration."""

    def download_deck_text(
        self,
        deck_number: str,
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[..., None],
    ) -> None:
        if not deck_number:
            on_error(ValueError("Deck identifier missing"))
            return

        on_status("app.status.downloading_deck")

        source_filter = self.get_deck_data_source()

        def worker(number: str):
            return self.workflow_service.download_deck_text(number, source_filter=source_filter)

        self._worker.submit(worker, deck_number, on_success=on_success, on_error=on_error)

    def build_deck_text(self, zone_cards: dict[str, list[dict[str, Any]]] | None = None) -> str:
        zones = zone_cards if zone_cards is not None else self.zone_cards
        return self.workflow_service.build_deck_text(zones)

    def save_deck(
        self,
        deck_name: str,
        deck_content: str,
        format_name: str,
        deck: dict[str, Any] | None = None,
    ) -> tuple[Path, int | None]:
        return self.workflow_service.save_deck(
            deck_name=deck_name,
            deck_content=deck_content,
            format_name=format_name,
            deck=deck,
            deck_save_dir=self.deck_save_dir,
        )

    def build_daily_average_deck(
        self,
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, str]:
        cutoff_date = (datetime.now() - timedelta(hours=self._average_hours)).strftime("%Y-%m-%d")
        todays_decks = [
            deck for deck in self.deck_repo.get_decks_list() if deck.get("date", "") >= cutoff_date
        ]

        if not todays_decks:
            return False, "No decks from the selected time window found for this archetype."

        with self._loading_lock:
            self.loading_daily_average = True

        on_status("app.status.building_daily_average")

        source_filter = self.get_deck_data_source()
        method = self._average_method
        deck_count = len(todays_decks)

        def worker(rows: list[dict[str, Any]]):
            return self.workflow_service.build_daily_average_buffer(
                rows,
                source_filter=source_filter,
                method=method,
                on_progress=on_progress,
            )

        def success_handler(buffer):
            with self._loading_lock:
                self.loading_daily_average = False
            if method == "karsten":
                deck_text = self.deck_service.render_karsten_deck(buffer)
            else:
                deck_text = self.deck_service.render_average_deck(buffer, deck_count)
            on_success(deck_text)

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_daily_average = False
            logger.error(f"Daily average error: {error}")
            on_error(error)

        self._worker.submit(
            worker,
            todays_decks,
            on_success=success_handler,
            on_error=error_handler,
        )

        return True, f"Processing {deck_count} decks"

    def get_zone_cards(self) -> dict[str, list[dict[str, Any]]]:
        return self.zone_cards
