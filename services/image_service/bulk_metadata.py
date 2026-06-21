"""Bulk-metadata lifecycle for :class:`BulkImageDownloader`.

Talks to the Scryfall bulk-data metadata endpoint, the ``bulk_data_meta`` SQLite
row, and the on-disk bulk file: freshness checks plus the streamed atomic
download.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.image_service.schemas import BULK_DATA_URL, UTC
from utils.atomic_io import atomic_write_stream
from utils.constants import (
    BULK_DATA_CACHE_FRESHNESS_SECONDS,
    BYTES_PER_MB,
    SCRYFALL_BULK_STREAM_TIMEOUT_SECONDS,
    SCRYFALL_DOWNLOAD_CHUNK_SIZE,
    SCRYFALL_REQUEST_TIMEOUT_SECONDS,
    SQLITE_CONNECTION_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from services.image_service.downloader_protocol import BulkImageDownloaderProto

    _Base = BulkImageDownloaderProto
else:
    _Base = object


class BulkMetadataMixin(_Base):
    """Bulk-data metadata fetch, freshness check, and streamed download."""

    def _fetch_bulk_metadata(self) -> dict[str, Any]:
        logger.info("Fetching bulk data metadata from Scryfall...")
        resp = self.session.get(BULK_DATA_URL, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()

    def _get_cached_bulk_data_record(self) -> tuple[str | None, str | None]:
        with sqlite3.connect(self.cache.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS) as conn:
            row = conn.execute(
                "SELECT downloaded_at, bulk_data_uri FROM bulk_data_meta WHERE id = 1"
            ).fetchone()
        if row:
            return row[0], row[1]
        return None, None

    def is_bulk_data_outdated(
        self, max_staleness_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any]]:
        # Lazy import so monkeypatches of ``BULK_DATA_CACHE`` on the schemas
        # module are honoured by tests.
        from services.image_service import schemas as _schemas

        metadata = self._fetch_bulk_metadata()
        download_uri = metadata.get("download_uri")
        updated_at = metadata.get("updated_at")

        if not _schemas.BULK_DATA_CACHE.exists():
            return True, metadata

        cached_updated, cached_uri = self._get_cached_bulk_data_record()
        if updated_at and download_uri and cached_updated and cached_uri:
            if updated_at == cached_updated and download_uri == cached_uri:
                return False, metadata
            return True, metadata

        # Fallback to age-based check when the vendor metadata lacks timestamps/URIs
        threshold = max_staleness_seconds or BULK_DATA_CACHE_FRESHNESS_SECONDS
        try:
            age_seconds = datetime.now().timestamp() - _schemas.BULK_DATA_CACHE.stat().st_mtime
            if age_seconds < threshold:
                return False, metadata
        except OSError:
            pass

        return True, metadata

    def download_bulk_metadata(self, force: bool = False) -> tuple[bool, str]:
        from services.image_service import schemas as _schemas

        try:
            metadata = self._fetch_bulk_metadata()
        except Exception as exc:
            logger.exception("Failed to fetch bulk data metadata")
            return False, f"Error: {exc}"

        download_uri = metadata.get("download_uri")
        if not download_uri:
            return False, "No download URI in bulk data response"

        remote_updated_at = metadata.get("updated_at")
        cached_updated, cached_uri = self._get_cached_bulk_data_record()
        cache_matches = (
            not force
            and _schemas.BULK_DATA_CACHE.exists()
            and remote_updated_at
            and cached_updated == remote_updated_at
            and cached_uri == download_uri
        )
        if cache_matches:
            logger.info("Using cached bulk data (vendor metadata is current)")
            return True, "Using cached bulk data"

        try:
            logger.info(f"Downloading bulk data from {download_uri}")
            logger.info(f"Size: {metadata.get('size', 0) / BYTES_PER_MB:.1f} MB")

            # Download with progress
            resp = self.session.get(
                download_uri, stream=True, timeout=SCRYFALL_BULK_STREAM_TIMEOUT_SECONDS
            )
            resp.raise_for_status()

            atomic_write_stream(
                _schemas.BULK_DATA_CACHE,
                resp.iter_content(chunk_size=SCRYFALL_DOWNLOAD_CHUNK_SIZE),
            )

            # Update database metadata (defer card count to avoid parsing 500MB file)
            with sqlite3.connect(
                self.cache.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS
            ) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bulk_data_meta (id, downloaded_at, total_cards, bulk_data_uri)
                    VALUES (1, ?, ?, ?)
                """,
                    (
                        remote_updated_at or datetime.now(UTC).isoformat(),
                        0,
                        download_uri,
                    ),
                )
                conn.commit()

            logger.info("Bulk data downloaded successfully")
            return True, "Bulk data downloaded"

        except Exception as exc:
            logger.exception("Failed to download bulk data")
            return False, f"Error: {exc}"
