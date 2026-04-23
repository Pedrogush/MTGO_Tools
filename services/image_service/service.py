"""ImageService composed from responsibility-specific mixins."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from services.image_service.bulk_data import BulkDataMixin
from services.image_service.cache import ImageCacheMixin
from services.image_service.download_queue import CardImageDownloadQueue
from services.image_service.metadata import PrintingsFetchMixin
from services.image_service.printing_index import PrintingIndexMixin
from utils.card_images import BulkImageDownloader, CardImageRequest, get_cache
from utils.process_worker import ProcessHandle, ProcessWorker


class ImageService(
    BulkDataMixin,
    PrintingIndexMixin,
    PrintingsFetchMixin,
    ImageCacheMixin,
):
    """Service for managing card image bulk data and printing indices."""

    def __init__(self):
        self.image_cache = get_cache()
        self.image_downloader: BulkImageDownloader | None = None
        self.bulk_data_by_name: dict[str, list[dict[str, Any]]] | None = None
        self.printing_index_loading: bool = False
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
        self._download_queue.stop()
        if self._bulk_download_handle:
            self._process_worker.terminate(self._bulk_download_handle)
            self._bulk_download_handle = None
        if self._printings_handle:
            self._process_worker.terminate(self._printings_handle)
            self._printings_handle = None
        self._process_worker.terminate_all()
