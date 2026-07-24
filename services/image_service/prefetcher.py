"""Predictive batch prefetch of card images (issue #951).

UI surfaces submit the cards a user is *likely* to look at next — the loaded
deck's zones, the top visible decks of the research tab, the visible window of
the card search — and a single background worker feeds them through the shared
:class:`~services.image_service.download_queue.CardImageDownloadQueue` in
bounded batches, so images are already on disk by the time the user hovers.

Every submission carries a priority tier (see
:mod:`services.image_service.priorities`) that travels with each request into
the download queue, so the selected deck's batch always drains ahead of
research/warm-up traffic. User-driven batches (``priority <=
PRIORITY_USER_DRIVEN_MAX``) run immediately; background ones idle through a
short startup grace delay so they never compete with the app's initial loads.

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
import time
from collections.abc import Callable, Iterable

from loguru import logger

from services.image_service.priorities import (
    PRIORITY_BACKGROUND,
    PRIORITY_USER_DRIVEN_MAX,
)
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

# Optional per-batch feedback: called on the worker thread after a batch runs
# with (source, enqueued_names, skipped_names). Skipped names were already
# cached, already queued, or previously submitted at an equal-or-better tier.
BatchCallback = Callable[[str, list[str], list[str]], None]


class ImagePrefetcher:
    """Coalescing background feeder for the card-image download queue."""

    def __init__(
        self,
        enqueue: Callable[[CardImageRequest, int], bool],
        *,
        batch_limit: int = IMAGE_PREFETCH_BATCH_LIMIT,
        size: str = "normal",
        start_delay: float = IMAGE_PREFETCH_START_DELAY_SECONDS,
    ) -> None:
        self._enqueue = enqueue
        self._batch_limit = batch_limit
        self._size = size
        # Background batches idle until this deadline so prefetch downloads
        # never compete with the app's initial loads or first paint;
        # user-driven batches (selected deck, visible research decks) ignore
        # it — those are the images the user is waiting on right now.
        self._background_deadline = time.monotonic() + start_delay
        # Latest pending (priority, provider, on_batch) per source; newer
        # submissions replace older ones so only the most recent prediction
        # for each surface runs.
        self._pending: dict[str, tuple[int, NamesProvider, BatchCallback | None]] = {}
        # Best (numerically lowest) priority each name has been fed to the
        # queue with this session. The queue dedupes pending/in-flight
        # requests itself, but each enqueue of an already-cached name costs a
        # SQLite lookup — this keeps repeated submissions of the same window
        # (scrolling back and forth) free, while still letting a name be
        # re-submitted at a *better* tier (the queue promotes it in place).
        self._submitted: dict[str, int] = {}
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

    def prefetch(
        self,
        source: str,
        names: Iterable[str],
        *,
        priority: int = PRIORITY_BACKGROUND,
        on_batch: BatchCallback | None = None,
    ) -> None:
        """Prefetch ``names`` (deduped, capped) on behalf of ``source``."""
        snapshot = list(names)
        self.prefetch_lazy(source, lambda: snapshot, priority=priority, on_batch=on_batch)

    def prefetch_lazy(
        self,
        source: str,
        provider: NamesProvider,
        *,
        priority: int = PRIORITY_BACKGROUND,
        on_batch: BatchCallback | None = None,
    ) -> None:
        """Like :meth:`prefetch`, but ``provider`` runs on the worker thread.

        Use when producing the names is itself expensive (network, disk) and
        must not run on the caller's thread.
        """
        if self._stop_event.is_set():
            return
        with self._condition:
            self._pending[source] = (priority, provider, on_batch)
            self._condition.notify()

    # ------------------------------------------------------------------ worker
    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._condition:
                batch = self._next_batch_locked()
                while batch is None and not self._stop_event.is_set():
                    self._condition.wait(timeout=self._wait_timeout_locked())
                    batch = self._next_batch_locked()
                if self._stop_event.is_set():
                    return
                source, (priority, provider, on_batch) = batch
            self._run_batch(source, provider, priority=priority, on_batch=on_batch)

    def _next_batch_locked(
        self,
    ) -> tuple[str, tuple[int, NamesProvider, BatchCallback | None]] | None:
        """Pop the most urgent runnable submission, or None to keep waiting.

        Background-tier submissions are held until the startup grace deadline;
        user-driven ones run immediately, even during the delay.
        """
        if not self._pending:
            return None
        source = min(self._pending, key=lambda s: self._pending[s][0])
        priority = self._pending[source][0]
        if priority > PRIORITY_USER_DRIVEN_MAX and time.monotonic() < self._background_deadline:
            return None
        return source, self._pending.pop(source)

    def _wait_timeout_locked(self) -> float:
        """Wait timeout: shortened while background work waits out the delay."""
        if not self._pending:
            return IMAGE_PREFETCH_IDLE_WAIT_SECONDS
        remaining = self._background_deadline - time.monotonic()
        return min(IMAGE_PREFETCH_IDLE_WAIT_SECONDS, max(remaining, 0.05))

    def _run_batch(
        self,
        source: str,
        provider: NamesProvider,
        *,
        priority: int = PRIORITY_BACKGROUND,
        on_batch: BatchCallback | None = None,
    ) -> None:
        try:
            names = provider()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Image prefetch provider for {source} failed: {exc}")
            return
        batch: list[str] = []
        skipped: list[str] = []
        seen: set[str] = set()
        for name in names:
            cleaned = (name or "").strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            # Skip names already fed to the queue at this tier or better; a
            # strictly better tier re-submits so the queue promotes them.
            if self._submitted.get(key, PRIORITY_BACKGROUND + 1) <= priority:
                skipped.append(cleaned)
                continue
            batch.append(cleaned)
            if len(batch) >= self._batch_limit:
                break
        if not batch:
            if on_batch:
                self._safe_on_batch(on_batch, source, [], skipped)
            return
        enqueued: list[str] = []
        for name in batch:
            if self._stop_event.is_set():
                return
            self._submitted[name.lower()] = priority
            try:
                if self._enqueue(
                    CardImageRequest(
                        card_name=name,
                        uuid=None,
                        set_code=None,
                        collector_number=None,
                        size=self._size,
                    ),
                    priority,
                ):
                    enqueued.append(name)
                else:
                    skipped.append(name)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"Image prefetch enqueue for {name} failed: {exc}")
                skipped.append(name)
        if enqueued:
            logger.debug(
                f"Image prefetch [{source}] (tier {priority}): queued "
                f"{len(enqueued)}/{len(batch)} candidate cards"
            )
        if on_batch:
            self._safe_on_batch(on_batch, source, enqueued, skipped)

    @staticmethod
    def _safe_on_batch(
        on_batch: BatchCallback, source: str, enqueued: list[str], skipped: list[str]
    ) -> None:
        try:
            on_batch(source, enqueued, skipped)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Image prefetch on_batch for {source} failed: {exc}")


__all__ = ["ImagePrefetcher"]
