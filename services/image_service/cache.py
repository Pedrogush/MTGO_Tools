"""Image cache interactions: download queueing and UI callbacks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.image_service.priorities import PRIORITY_BACKGROUND
from services.image_service.schemas import CardImageRequest

if TYPE_CHECKING:
    from services.image_service.protocol import ImageServiceProto

    _Base = ImageServiceProto
else:
    _Base = object


class ImageCacheMixin(_Base):
    """Download-queue orchestration and UI callback plumbing."""

    def set_image_download_callback(
        self, callback: Callable[[CardImageRequest], None] | None
    ) -> None:
        self._on_image_downloaded = callback

    def set_image_download_failed_callback(
        self, callback: Callable[[CardImageRequest, str], None] | None
    ) -> None:
        self._on_image_download_failed = callback

    def set_printings_loaded_callback(
        self, callback: Callable[[str, list[dict[str, Any]]], None] | None
    ) -> None:
        self._on_printings_loaded = callback

    def queue_card_image_download(
        self,
        request: CardImageRequest,
        *,
        prioritize: bool,
        priority: int = PRIORITY_BACKGROUND,
    ) -> bool:
        enqueued = self._download_queue.enqueue(request, prioritize=prioritize, priority=priority)
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
        self._download_queue.set_selected_request(request)

    def prefetch_card_images(
        self,
        source: str,
        names: Iterable[str],
        *,
        priority: int = PRIORITY_BACKGROUND,
        on_batch: Callable[[str, list[str], list[str]], None] | None = None,
    ) -> None:
        """Batch-prefetch images for the cards a user is likely to view next.

        Coalesces per ``source`` and runs off the UI thread; see
        :class:`~services.image_service.prefetcher.ImagePrefetcher`.
        """
        self._prefetcher.prefetch(source, names, priority=priority, on_batch=on_batch)

    def prefetch_card_images_lazy(
        self,
        source: str,
        provider: Callable[[], Iterable[str]],
        *,
        priority: int = PRIORITY_BACKGROUND,
    ) -> None:
        """Batch-prefetch with ``provider`` evaluated on the prefetch thread."""
        self._prefetcher.prefetch_lazy(source, provider, priority=priority)

    def _handle_image_downloaded(self, request: CardImageRequest) -> None:
        if not self._on_image_downloaded:
            return
        self._call_after(self._on_image_downloaded, request)

    def _handle_image_download_failed(self, request: CardImageRequest, message: str) -> None:
        if not self._on_image_download_failed:
            return
        self._call_after(self._on_image_download_failed, request, message)

    @staticmethod
    def _call_after(callback: Callable[..., Any], *args: Any) -> None:
        try:
            import wx

            wx.CallAfter(callback, *args)
        except ImportError:
            callback(*args)
