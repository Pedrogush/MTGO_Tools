"""Shared ``self`` contract that the :class:`ImageService` mixins assume."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

from services.image_service.download_queue import CardImageDownloadQueue
from utils.card_images import BulkImageDownloader, CardImageCache, CardImageRequest
from utils.process_worker import ProcessHandle, ProcessWorker


class ImageServiceProto(Protocol):
    """Cross-mixin ``self`` surface for ``ImageService``."""

    image_cache: CardImageCache
    image_downloader: BulkImageDownloader | None
    bulk_data_by_name: dict[str, list[dict[str, Any]]] | None
    printing_index_loading: bool

    _on_image_downloaded: Callable[[CardImageRequest], None] | None
    _on_image_download_failed: Callable[[CardImageRequest, str], None] | None
    _on_printings_loaded: Callable[[str, list[dict[str, Any]]], None] | None

    _download_queue: CardImageDownloadQueue
    _printings_lock: threading.Lock
    _printings_inflight: set[str]

    _process_worker: ProcessWorker
    _bulk_download_handle: ProcessHandle | None
    _printings_handle: ProcessHandle | None

    def _call_after(self, callback: Callable[..., Any], *args: Any) -> None: ...
    def _run_printings_task(
        self,
        worker: Callable[[], tuple[str, list[dict[str, Any]]]],
        on_success: Callable[[tuple[str, list[dict[str, Any]]]], None],
        on_error: Callable[[Exception], None],
    ) -> None: ...
