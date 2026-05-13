"""Subprocess worker entrypoints for card image bulk operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from datetime import UTC, datetime
except ImportError:  # Python 3.10
    from datetime import datetime, timezone

    UTC = timezone.utc  # noqa: F811,UP017

from services.image_service.disk_cache import CardImageCache
from services.image_service.downloader import BulkImageDownloader
from services.image_service.printing_index import build_printing_index
from services.image_service.schemas import _bulk_cards_decoder
from utils.atomic_io import atomic_write_json, locked_path

__all__ = ["build_printing_index_worker", "download_bulk_metadata_worker"]


def download_bulk_metadata_worker(*, cache_dir: str, db_path: str, force: bool) -> dict[str, Any]:
    cache = CardImageCache(cache_dir=Path(cache_dir), db_path=Path(db_path))
    downloader = BulkImageDownloader(cache)
    success, msg = downloader.download_bulk_metadata(force=force)
    if not success:
        raise RuntimeError(msg)
    return {"message": msg}


def build_printing_index_worker(
    *,
    bulk_data_path: str,
    printings_path: str,
    printings_version: int,
) -> dict[str, Any]:
    bulk_path = Path(bulk_data_path)
    printings_cache = Path(printings_path)
    bulk_mtime = bulk_path.stat().st_mtime if bulk_path.exists() else None
    if bulk_mtime is None:
        raise FileNotFoundError("Bulk data cache not found; cannot build printings index")

    with locked_path(bulk_path):
        raw = bulk_path.read_bytes()
    cards = _bulk_cards_decoder.decode(raw)

    by_name, stats = build_printing_index(cards)
    payload = {
        "version": printings_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "bulk_mtime": bulk_mtime,
        "unique_names": stats["unique_names"],
        "total_printings": stats["total_printings"],
        "data": by_name,
    }
    atomic_write_json(printings_cache, payload, separators=(",", ":"))
    return {
        "unique_names": payload["unique_names"],
        "total_printings": payload["total_printings"],
        "bulk_mtime": bulk_mtime,
    }
