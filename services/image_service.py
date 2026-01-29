"""
Image Service - Business logic for card image and bulk data management.

This module handles:
- Bulk data freshness checking
- Bulk metadata downloading
- Printing index loading
- Image cache management
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from loguru import logger

from utils.card_images import (
    BULK_DATA_CACHE,
    PRINTING_INDEX_CACHE,
    PRINTING_INDEX_VERSION,
    BulkImageDownloader,
    CardImageRequest,
    get_cache,
    load_printing_index_payload,
)
from utils.card_images_workers import (
    build_printing_index_worker,
    download_bulk_metadata_worker,
)
from utils.process_worker import ProcessHandle, ProcessWorker


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

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the background worker."""
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=timeout)
        self._executor.shutdown(wait=True, cancel_futures=True)

    def set_selected_request(self, request: CardImageRequest | None) -> None:
        """Update the current selection for priority handling."""
        with self._condition:
            self._selected_request = request
            self._ensure_selected_priority_locked()

    def enqueue(self, request: CardImageRequest, *, prioritize: bool = False) -> bool:
        """Add a card image to the download queue."""
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
                    self._condition.wait(timeout=0.5)
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
        max_retries = 5
        backoff_seconds = 0.5
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
                if elapsed > 1.5 and not self._is_cached(request):
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


class ImageService:
    """Service for managing card image bulk data and printing indices."""

    def __init__(self):
        """Initialize the image service."""
        self.image_cache = get_cache()
        self.image_downloader: BulkImageDownloader | None = None
        self.bulk_data_by_name: dict[str, list[dict[str, Any]]] | None = None
        self.printing_index_loading: bool = False
        self._bulk_check_worker_active: bool = False
        self._on_image_downloaded: Callable[[CardImageRequest], None] | None = None
        self._on_image_download_failed: Callable[[CardImageRequest, str], None] | None = None
        self._download_queue = CardImageDownloadQueue(
            self.image_cache,
            on_downloaded=self._handle_image_downloaded,
            on_failed=self._handle_image_download_failed,
        )
        self._printings_lock = threading.Lock()
        self._printings_inflight: set[str] = set()
        self._on_printings_loaded: Callable[[str, list[dict[str, Any]]], None] | None = None
        self._process_worker = ProcessWorker()
        self._bulk_download_handle: ProcessHandle | None = None
        self._printings_handle: ProcessHandle | None = None

    def shutdown(self) -> None:
        """Stop background services owned by the image service."""
        self._download_queue.stop()
        if self._bulk_download_handle:
            self._process_worker.terminate(self._bulk_download_handle)
            self._bulk_download_handle = None
        if self._printings_handle:
            self._process_worker.terminate(self._printings_handle)
            self._printings_handle = None
        self._process_worker.terminate_all()

    def set_image_download_callback(
        self, callback: Callable[[CardImageRequest], None] | None
    ) -> None:
        """Register a callback for completed card image downloads."""
        self._on_image_downloaded = callback

    def set_image_download_failed_callback(
        self, callback: Callable[[CardImageRequest, str], None] | None
    ) -> None:
        """Register a callback for failed card image downloads."""
        self._on_image_download_failed = callback

    def set_printings_loaded_callback(
        self, callback: Callable[[str, list[dict[str, Any]]], None] | None
    ) -> None:
        """Register a callback for completed printings fetches."""
        self._on_printings_loaded = callback

    def queue_card_image_download(self, request: CardImageRequest, *, prioritize: bool) -> bool:
        """Queue a card image download request."""
        enqueued = self._download_queue.enqueue(request, prioritize=prioritize)
        logger.debug(
            "Queue image request for %s (set=%s, size=%s, collector=%s) -> %s",
            request.card_name,
            request.set_code,
            request.size,
            request.collector_number,
            "enqueued" if enqueued else "skipped",
        )
        return enqueued

    def set_selected_card_request(self, request: CardImageRequest | None) -> None:
        """Update the currently selected card for queue prioritization."""
        self._download_queue.set_selected_request(request)

    def _handle_image_downloaded(self, request: CardImageRequest) -> None:
        if not self._on_image_downloaded:
            return
        self._call_after(self._on_image_downloaded, request)

    def _handle_image_download_failed(self, request: CardImageRequest, message: str) -> None:
        if not self._on_image_download_failed:
            return
        self._call_after(self._on_image_download_failed, request, message)

    def fetch_printings_by_name_async(self, card_name: str) -> None:
        """Fetch all printings for a card name in the background."""
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

    @staticmethod
    def _call_after(callback: Callable[..., Any], *args: Any) -> None:
        """Marshal callback to UI thread if wx is available."""
        try:
            import wx

            wx.CallAfter(callback, *args)
        except ImportError:
            callback(*args)

    # ============= Bulk Data Management =============

    def check_bulk_data_exists(self) -> tuple[bool, str]:
        """
        Check if bulk data exists.

        Returns:
            Tuple of (exists: bool, reason: str)
        """
        if not BULK_DATA_CACHE.exists():
            return False, "Bulk data cache not found"

        return True, "Bulk data cache exists"

    def download_bulk_metadata_async(
        self,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
        force: bool = False,
    ) -> None:
        """
        Download bulk metadata in a background thread.

        Args:
            on_success: Callback for successful download (receives success message)
            on_error: Callback for failed download (receives error message)
            force: Force download even if vendor metadata matches cache
        """
        if self._bulk_download_handle and self._bulk_download_handle.process.is_alive():
            logger.debug("Bulk data download already running")
            return

        def _on_success(result: dict[str, Any]) -> None:
            msg = result.get("message", "Bulk data downloaded")
            on_success(msg)

        def _on_error(msg: str) -> None:
            on_error(msg)

        try:
            self._bulk_download_handle = self._process_worker.run_async(
                target=download_bulk_metadata_worker,
                args=(),
                kwargs={
                    "cache_dir": str(self.image_cache.cache_dir),
                    "db_path": str(self.image_cache.db_path),
                    "force": force,
                },
                on_success=_on_success,
                on_error=_on_error,
                call_after=self._call_after,
            )
        except Exception as exc:
            logger.exception("Failed to start bulk metadata process")
            on_error(str(exc))

    def ensure_data_ready(
        self,
        *,
        force_cached: bool,
        max_age_days: int,
        worker_factory: Callable[..., Any],
        set_status: Callable[[str], None],
        on_load_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_load_error: Callable[[str], None],
        on_download_success: Callable[[str], None],
        on_download_error: Callable[[str], None],
        on_check_failed: Callable[[Exception], None],
    ) -> None:
        """
        Coordinate card image bulk data lifecycle.

        Checks freshness, loads cached data, or initiates download as needed.

        Args:
            force_cached: If True, skip freshness check and use cached data only
            max_age_days: Maximum age of bulk data before triggering download
            worker_factory: Factory function to create background workers
            set_status: Callback to update status text
            on_load_success: Callback for successful bulk data load
            on_load_error: Callback for failed bulk data load
            on_download_success: Callback for successful download
            on_download_error: Callback for failed download
            on_check_failed: Callback for freshness check failure
        """
        if self._bulk_check_worker_active:
            logger.debug("Bulk data check already running")
            return

        status_msg = (
            "Loading cached card image database…"
            if force_cached
            else "Checking card image database…"
        )
        set_status(status_msg)
        self._bulk_check_worker_active = True

        def worker():
            if force_cached:
                return False, "Cached-only mode enabled"
            return self.check_bulk_data_freshness(max_age_days=max_age_days)

        def on_success(result: tuple[bool, str]) -> None:
            self._bulk_check_worker_active = False
            needs_download, reason = result
            self._handle_check_result(
                needs_download=needs_download,
                reason=reason,
                force_cached=force_cached,
                set_status=set_status,
                on_load_success=on_load_success,
                on_load_error=on_load_error,
                on_download_success=on_download_success,
                on_download_error=on_download_error,
            )

        def on_error(exc: Exception) -> None:
            self._bulk_check_worker_active = False
            on_check_failed(exc)

        worker_factory(worker, on_success=on_success, on_error=on_error).start()

    def _handle_check_result(
        self,
        *,
        needs_download: bool,
        reason: str,
        force_cached: bool,
        set_status: Callable[[str], None],
        on_load_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_load_error: Callable[[str], None],
        on_download_success: Callable[[str], None],
        on_download_error: Callable[[str], None],
    ) -> None:
        """Handle the result of bulk data freshness check."""
        if force_cached or not needs_download:
            self._load_bulk_data(
                set_status=set_status,
                force=force_cached,
                on_success=on_load_success,
                on_error=on_load_error,
            )
            if force_cached:
                set_status("Using cached card image database")
            else:
                set_status("Card image database ready")
            return

        if not self.bulk_data_by_name:
            self._load_bulk_data(
                set_status=set_status,
                force=False,
                on_success=on_load_success,
                on_error=on_load_error,
            )

        logger.info(f"Bulk data needs update: {reason}")
        set_status("Downloading card image database...")
        self.download_bulk_metadata_async(
            on_success=on_download_success,
            on_error=on_download_error,
        )

    def _load_bulk_data(
        self,
        *,
        set_status: Callable[[str], None],
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Load bulk data from cache."""
        set_status("Preparing card printings cache…")
        started = self.load_printing_index_async(
            force=force,
            on_success=on_success,
            on_error=on_error,
        )
        if not started:
            set_status("Ready")

    def load_bulk_data_direct(
        self,
        *,
        force: bool,
        set_status: Callable[[str], None],
        on_load_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_load_error: Callable[[str], None],
    ) -> None:
        """Expose bulk data loading for fallback flows."""
        self._load_bulk_data(
            set_status=set_status,
            force=force,
            on_success=on_load_success,
            on_error=on_load_error,
        )

    # ============= Printing Index Management =============

    def load_printing_index_async(
        self,
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> bool:
        """
        Load printing index in a background thread.

        Args:
            force: Force reload even if already loading/loaded
            on_success: Callback for successful load (receives bulk_data_by_name, stats)
            on_error: Callback for failed load (receives error message)

        Returns:
            True if load was started, False if skipped
        """
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
        """Set the bulk data reference."""
        self.bulk_data_by_name = bulk_data

    def clear_printing_index_loading(self) -> None:
        """Clear the printing index loading flag."""
        self.printing_index_loading = False

    def get_bulk_data(self) -> dict[str, list[dict[str, Any]]] | None:
        """Get the current bulk data."""
        return self.bulk_data_by_name

    def is_loading(self) -> bool:
        """Check if printing index is currently loading."""
        return self.printing_index_loading


# Global instance for backward compatibility
_default_service = None


def get_image_service() -> ImageService:
    """Get the default image service instance."""
    global _default_service
    if _default_service is None:
        _default_service = ImageService()
    return _default_service


def reset_image_service() -> None:
    """
    Reset the global image service instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_service
    _default_service = None
