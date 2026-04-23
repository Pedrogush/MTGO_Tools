"""Background queue for downloading individual card images."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from utils.card_images import BulkImageDownloader, CardImageRequest
from utils.constants.timing import (
    IMAGE_DOWNLOAD_INITIAL_BACKOFF_SECONDS,
    IMAGE_DOWNLOAD_MAX_RETRIES,
    IMAGE_DOWNLOAD_QUEUE_IDLE_WAIT_SECONDS,
    IMAGE_DOWNLOAD_QUEUE_STOP_TIMEOUT_SECONDS,
    IMAGE_DOWNLOAD_SLOW_THRESHOLD_SECONDS,
)


class CardImageDownloadQueue:
    """Background queue for downloading individual card images."""

    _MAX_CONCURRENT_DOWNLOADS = 10
    _NOT_FOUND_LOCK = threading.Lock()
    _NOT_FOUND_KEYS: set[tuple[str, str]] = set()

    def __init__(
        self,
        cache,
        *,
        on_downloaded: Callable[[CardImageRequest], None] | None = None,
        on_failed: Callable[[CardImageRequest, str], None] | None = None,
    ) -> None:
        self._cache = cache
        self._downloader = BulkImageDownloader(cache)
        self._on_downloaded = on_downloaded
        self._on_failed = on_failed
        self._queue: deque[CardImageRequest] = deque()
        self._pending_keys: set[tuple[str, str, str, str]] = set()
        self._inflight_keys: set[tuple[str, str, str, str]] = set()
        self._inflight_count = 0
        self._selected_request: CardImageRequest | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._executor = ThreadPoolExecutor(max_workers=self._MAX_CONCURRENT_DOWNLOADS)
        self._thread = threading.Thread(
            target=self._run,
            name="card-image-download-queue",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = IMAGE_DOWNLOAD_QUEUE_STOP_TIMEOUT_SECONDS) -> None:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=timeout)
        self._executor.shutdown(wait=True, cancel_futures=True)

    def set_selected_request(self, request: CardImageRequest | None) -> None:
        with self._condition:
            self._selected_request = request
            self._ensure_selected_priority_locked()

    def enqueue(self, request: CardImageRequest, *, prioritize: bool = False) -> bool:
        if not request.can_fetch():
            return False
        if self._is_cached(request):
            return False
        not_found_key = self._not_found_key(request)
        key = request.queue_key()
        with self._condition:
            if self._is_not_found_key_blocked(not_found_key):
                logger.debug(
                    "Skipping image request for %s (set=%s, size=%s, collector=%s); "
                    "marked not found.",
                    request.card_name,
                    request.set_code,
                    request.size,
                    request.collector_number,
                )
                return False
            if key in self._inflight_keys:
                return False
            if key in self._pending_keys:
                if prioritize:
                    self._remove_request_by_key_locked(key)
                else:
                    return False
            if prioritize:
                self._queue.appendleft(request)
            else:
                self._queue.append(request)
            self._pending_keys.add(key)
            self._condition.notify()
        return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._condition:
                while (
                    not self._queue or self._inflight_count >= self._MAX_CONCURRENT_DOWNLOADS
                ) and not self._stop_event.is_set():
                    self._condition.wait(timeout=IMAGE_DOWNLOAD_QUEUE_IDLE_WAIT_SECONDS)
                if self._stop_event.is_set():
                    break
                request = self._queue.popleft()
                self._pending_keys.discard(request.queue_key())
                self._inflight_keys.add(request.queue_key())
                self._inflight_count += 1

            future = self._executor.submit(self._download_request, request)
            future.add_done_callback(
                lambda completed, req=request: self._handle_download_complete(req, completed)
            )

    def _notify_downloaded(self, request: CardImageRequest) -> None:
        if not self._on_downloaded:
            return
        if self._is_cached(request):
            self._on_downloaded(request)

    def _notify_failed(self, request: CardImageRequest, message: str) -> None:
        if not self._on_failed:
            return
        self._on_failed(request, message)

    def _download_request(self, request: CardImageRequest) -> bool:
        logger.debug(
            "Starting image download for %s (set=%s, size=%s, collector=%s).",
            request.card_name,
            request.set_code,
            request.size,
            request.collector_number,
        )
        if self._is_cached(request):
            return True
        max_retries = IMAGE_DOWNLOAD_MAX_RETRIES
        backoff_seconds = IMAGE_DOWNLOAD_INITIAL_BACKOFF_SECONDS
        attempt = 0
        while True:
            started_at = time.monotonic()
            try:
                success, msg = self._downloader.download_card_image_by_name(
                    request.card_name, request.size, set_code=request.set_code
                )
            except Exception as exc:
                success = False
                msg = str(exc)
            if not success and self._is_not_found_message(msg):
                logger.error(f"Card image download failed for {request.card_name}: {msg}")
                self._add_not_found_key(self._not_found_key(request))
                self._notify_failed(request, msg)
                return False
            elapsed = time.monotonic() - started_at
            if success:
                if elapsed > IMAGE_DOWNLOAD_SLOW_THRESHOLD_SECONDS and not self._is_cached(request):
                    logger.error(
                        f"Assuming card image download failed for {request.card_name} "
                        f"({elapsed:.2f}s elapsed)."
                    )
                    return False
                self._discard_not_found_key(self._not_found_key(request))
                return True

            if attempt >= max_retries:
                logger.error(f"Card image download failed for {request.card_name}: {msg}")
                return False

            attempt += 1
            logger.warning(
                f"Retrying card image download for {request.card_name} in "
                f"{backoff_seconds:.1f}s ({attempt}/{max_retries})."
            )
            time.sleep(backoff_seconds)
            backoff_seconds *= 2

    @staticmethod
    def _is_not_found_message(message: str) -> bool:
        if not message:
            return False
        lowered = message.lower()
        return "404" in lowered and "not found" in lowered

    @staticmethod
    def _not_found_key(request: CardImageRequest) -> tuple[str, str]:
        return (
            (request.card_name or "").lower(),
            (request.set_code or "").lower(),
        )

    @classmethod
    def _add_not_found_key(cls, key: tuple[str, str]) -> None:
        with cls._NOT_FOUND_LOCK:
            cls._NOT_FOUND_KEYS.add(key)

    @classmethod
    def _discard_not_found_key(cls, key: tuple[str, str]) -> None:
        with cls._NOT_FOUND_LOCK:
            cls._NOT_FOUND_KEYS.discard(key)

    @classmethod
    def _is_not_found_key_blocked(cls, key: tuple[str, str]) -> bool:
        with cls._NOT_FOUND_LOCK:
            return key in cls._NOT_FOUND_KEYS

    def _handle_download_complete(self, request: CardImageRequest, completed) -> None:
        success = False
        try:
            success = completed.result()
        except Exception:
            logger.exception(f"Card image download failed for {request.card_name}")
        if success:
            self._notify_downloaded(request)
        with self._condition:
            key = request.queue_key()
            self._inflight_keys.discard(key)
            self._inflight_count = max(0, self._inflight_count - 1)
            self._ensure_selected_priority_locked()
            self._condition.notify()

    def _ensure_selected_priority_locked(self) -> None:
        request = self._selected_request
        if not request or not request.can_fetch():
            return
        if self._is_cached(request):
            return
        not_found_key = self._not_found_key(request)
        if self._is_not_found_key_blocked(not_found_key):
            return
        key = request.queue_key()
        if key in self._inflight_keys:
            return
        if key in self._pending_keys:
            self._remove_request_by_key_locked(key)
        self._queue.appendleft(request)
        self._pending_keys.add(key)
        self._condition.notify()

    def _remove_request_by_key_locked(self, key: tuple[str, str, str, str]) -> None:
        for request in list(self._queue):
            if request.queue_key() == key:
                self._queue.remove(request)
                self._pending_keys.discard(key)
                return

    def _is_cached(self, request: CardImageRequest) -> bool:
        if not request.card_name:
            return False
        if request.set_code:
            return (
                self._cache.get_image_path_for_printing(
                    request.card_name, request.set_code, request.size
                )
                is not None
            )
        return self._cache.get_image_path(request.card_name, request.size) is not None
