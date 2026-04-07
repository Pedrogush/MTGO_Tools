"""Background orchestration for MTGO decklist refreshes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from utils.constants import (
    MTGO_BACKGROUND_FETCH_DAYS,
    MTGO_BACKGROUND_FETCH_DELAY_SECONDS,
    MTGO_BACKGROUND_FETCH_SLEEP_STEP_SECONDS,
    MTGO_BACKGROUND_FETCH_SLEEP_STEPS,
    MTGO_BACKGROUND_FORMATS,
    MTGO_DECKLISTS_ENABLED,
)

if TYPE_CHECKING:
    from utils.background_worker import BackgroundWorker


class MtgoBackgroundHelpers:
    def __init__(self, *, worker: BackgroundWorker) -> None:
        self._worker = worker

    def start_background_fetch(self) -> None:
        from services.mtgo_background_service import fetch_mtgo_data_background

        if not MTGO_DECKLISTS_ENABLED:
            logger.info("MTGO decklists disabled; background fetch not started.")
            return

        def mtgo_fetch_task():
            formats = MTGO_BACKGROUND_FORMATS

            while not self._worker.is_stopped():
                for mtg_format in formats:
                    if self._worker.is_stopped():
                        break
                    try:
                        logger.info(f"Starting MTGO background fetch for {mtg_format}...")
                        stats = fetch_mtgo_data_background(
                            days=MTGO_BACKGROUND_FETCH_DAYS,
                            mtg_format=mtg_format,
                            delay=MTGO_BACKGROUND_FETCH_DELAY_SECONDS,
                        )
                        logger.info(
                            f"MTGO fetch complete for {mtg_format}: "
                            f"{stats['total_decks_cached']} decks cached from "
                            f"{stats['events_processed']}/{stats['events_found']} events"
                        )
                    except Exception as exc:
                        logger.error(
                            f"MTGO background fetch failed for {mtg_format}: {exc}",
                            exc_info=True,
                        )

                if self._worker.is_stopped():
                    break

                logger.info(
                    "MTGO background fetch cycle complete. Waiting 1 hour before next cycle..."
                )
                for _ in range(MTGO_BACKGROUND_FETCH_SLEEP_STEPS):
                    if self._worker.is_stopped():
                        break
                    time.sleep(MTGO_BACKGROUND_FETCH_SLEEP_STEP_SECONDS)

        self._worker.submit(mtgo_fetch_task)
