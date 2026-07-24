"""Predictive batch prefetch of card images (issue #951).

UI surfaces submit the cards a user is *likely* to look at next — the loaded
deck's zones, the top visible decks of the research tab, the visible window of
the card search — and a single background worker feeds them through the shared
:class:`~services.image_service.download_queue.CardImageDownloadQueue` in
bounded batches, so images are already on disk by the time the user hovers.

Submissions coalesce per ``source``: a scroll storm on the search list ends up
as one batch (the latest window), never a backlog. Batches are capped at
:data:`IMAGE_PREFETCH_BATCH_LIMIT` requests so a huge search result can never
commit the app to downloading thousands of images.

The on-hover single-image behavior is unchanged — hover requests keep going
through :meth:`ImageService.queue_card_image_download` with ``prioritize=True``
and therefore always jump ahead of prefetch traffic in the queue.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from loguru import logger

from services.image_service.schemas import CardImageRequest
from utils.constants.timing import (
    IMAGE_PREFETCH_BATCH_LIMIT,
    IMAGE_PREFETCH_IDLE_WAIT_SECONDS,
    IMAGE_PREFETCH_START_DELAY_SECONDS,
    IMAGE_PREFETCH_STOP_TIMEOUT_SECONDS,
)

# A provider is called on the worker thread and returns the card names to
# prefetch. Lazy providers let a surface defer expensive work (e.g. fetching a
# research deck's text) off the UI thread until the batch is actually run.
NamesProvider = Callable[[], Iterable[str]]


class ImagePrefetcher:
    """Coalescing background feeder for the card-image download queue."""

    def __init__(
        self,
        enqueue: Callable[[CardImageRequest], bool],
        *,
        batch_limit: int = IMAGE_PREFETCH_BATCH_LIMIT,
        size: str = "normal",
        start_delay: float = IMAGE_PREFETCH_START_DELAY_SECONDS,
    ) -> None:
        self._enqueue = enqueue
        self._batch_limit = batch_limit
        self._size = size
        self._start_delay = start_delay
        # Latest pending provider per source; newer submissions replace older
        # ones so only the most recent prediction for each surface runs.
        self._pending: dict[str, NamesProvider] = {}
        # Names already fed to the queue this session. The queue dedupes
        # pending/in-flight requests itself, but each enqueue of an
        # already-cached name costs a SQLite lookup — this keeps repeated
        # submissions of the same window (scrolling back and forth) free.
        self._submitted: set[str] = set()
        self._stop_event = threading.Event()
        self._condition = threading.Condition()
        self._thread = threading.Thread(
            target=self._run,
            name="card-image-prefetcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = IMAGE_PREFETCH_STOP_TIMEOUT_SECONDS) -> None:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=timeout)

    def prefetch(self, source: str, names: Iterable[str]) -> None:
        """Prefetch ``names`` (deduped, capped) on behalf of ``source``."""
        snapshot = list(names)
        self.prefetch_lazy(source, lambda: snapshot)

    def prefetch_lazy(self, source: str, provider: NamesProvider) -> None:
        """Like :meth:`prefetch`, but ``provider`` runs on the worker thread.

        Use when producing the names is itself expensive (network, disk) and
        must not run on the caller's thread.
        """
        if self._stop_event.is_set():
            return
        with self._condition:
            self._pending[source] = provider
            self._condition.notify()

    # ------------------------------------------------------------------ worker
    def _run(self) -> None:
        # Idle before the first batch so prefetch downloads never compete with
        # the app's initial loads or first paint (same pattern as CacheWarmer).
        # Submissions arriving during the delay are held in _pending and run
        # once it elapses; a stop request interrupts the wait immediately.
        if self._stop_event.wait(self._start_delay):
            return
        while not self._stop_event.is_set():
            with self._condition:
                while not self._pending and not self._stop_event.is_set():
                    self._condition.wait(timeout=IMAGE_PREFETCH_IDLE_WAIT_SECONDS)
                if self._stop_event.is_set():
                    return
                source, provider = self._pending.popitem()
            self._run_batch(source, provider)

    def _run_batch(self, source: str, provider: NamesProvider) -> None:
        try:
            names = provider()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Image prefetch provider for {source} failed: {exc}")
            return
        batch: list[str] = []
        seen: set[str] = set()
        for name in names:
            cleaned = (name or "").strip()
            key = cleaned.lower()
            if not cleaned or key in seen or key in self._submitted:
                continue
            seen.add(key)
            batch.append(cleaned)
            if len(batch) >= self._batch_limit:
                break
        if not batch:
            return
        enqueued = 0
        for name in batch:
            if self._stop_event.is_set():
                return
            self._submitted.add(name.lower())
            try:
                if self._enqueue(
                    CardImageRequest(
                        card_name=name,
                        uuid=None,
                        set_code=None,
                        collector_number=None,
                        size=self._size,
                    )
                ):
                    enqueued += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"Image prefetch enqueue for {name} failed: {exc}")
        if enqueued:
            logger.debug(
                f"Image prefetch [{source}]: queued {enqueued}/{len(batch)} candidate cards"
            )


__all__ = ["ImagePrefetcher"]
