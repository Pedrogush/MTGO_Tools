"""Shared ``self`` contract that the :class:`BulkImageDownloader` mixins assume.

The downloader is composed from three responsibility-specific mixins
(:class:`BulkMetadataMixin`, :class:`LocalResolverMixin`,
:class:`ImageWriterMixin`) plus the thin orchestration on
:class:`BulkImageDownloader` itself. They share only the ``session``/``cache``
handles and the lazily-built local image index; this Protocol documents that
surface so each mixin can reach it via ``self`` under the ``_Base = Proto``
idiom used elsewhere in the package.
"""

from __future__ import annotations

import threading
from typing import Protocol

import requests

from services.image_service.disk_cache import CardImageCache
from services.image_service.schemas import BulkCardImage


class BulkImageDownloaderProto(Protocol):
    """Cross-mixin ``self`` surface for ``BulkImageDownloader``."""

    cache: CardImageCache
    max_workers: int
    session: requests.Session

    _local_image_index: dict[str, list[BulkCardImage]] | None
    _local_image_index_mtime: float | None
    _local_image_index_lock: threading.Lock
