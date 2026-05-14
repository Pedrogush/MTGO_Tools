"""Scryfall request loop and bulk fetch.

Contains:
- :class:`BulkImageDownloader` — fetches metadata and individual card images
- Top-level helpers used by scripts and widgets: :func:`get_cache`,
  :func:`get_card_image`, :func:`download_bulk_images`, :func:`get_cache_stats`.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from services.image_service.disk_cache import CardImageCache
from services.image_service.schemas import (
    BULK_DATA_URL,
    SCRYFALL_CARD_NAMED_URL,
    SCRYFALL_CARD_SEARCH_URL,
    UTC,
)
from utils.atomic_io import (
    atomic_write_bytes,
    atomic_write_stream,
    locked_path,
)
from utils.constants import (
    BULK_DATA_CACHE_FRESHNESS_SECONDS,
    BYTES_PER_MB,
    SCRYFALL_BULK_STREAM_TIMEOUT_SECONDS,
    SCRYFALL_DOWNLOAD_CHUNK_SIZE,
    SCRYFALL_DOWNLOAD_PROGRESS_INTERVAL,
    SCRYFALL_MAX_DOWNLOAD_WORKERS,
    SCRYFALL_REQUEST_TIMEOUT_SECONDS,
    SQLITE_CONNECTION_TIMEOUT_SECONDS,
)


class BulkImageDownloader:
    """High-throughput bulk image downloader using Scryfall data."""

    def __init__(self, cache: CardImageCache, max_workers: int = SCRYFALL_MAX_DOWNLOAD_WORKERS):
        self.cache = cache
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MTGOMetagameCrawler/1.0"})

    def _fetch_bulk_metadata(self) -> dict[str, Any]:
        logger.info("Fetching bulk data metadata from Scryfall...")
        resp = self.session.get(BULK_DATA_URL, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()

    def fetch_card_by_name(self, name: str, set_code: str | None = None) -> dict[str, Any]:
        params = {"exact": name}
        if set_code:
            params["set"] = set_code.lower()
        resp = self.session.get(
            SCRYFALL_CARD_NAMED_URL, params=params, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_printings_by_name(self, name: str) -> list[dict[str, Any]]:
        params = {"q": f'!"{name}"', "unique": "prints", "order": "released"}
        results: list[dict[str, Any]] = []
        url: str | None = SCRYFALL_CARD_SEARCH_URL
        while url:
            resp = self.session.get(url, params=params, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            payload = resp.json()
            results.extend(payload.get("data", []))
            url = payload.get("next_page")
            params = None
        return results

    def download_card_image_by_name(
        self, name: str, size: str = "normal", set_code: str | None = None
    ) -> tuple[bool, str]:
        card = self.fetch_card_by_name(name, set_code=set_code)
        return self._download_single_image(card, size)

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
            age_seconds = (
                datetime.now().timestamp() - _schemas.BULK_DATA_CACHE.stat().st_mtime
            )
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

    def _download_single_image(
        self, card: dict[str, Any], size: str = "normal"
    ) -> tuple[bool, str]:
        uuid = card.get("id")
        name = card.get("name", "Unknown")

        if not uuid:
            return False, f"No UUID for {name}"

        card_faces = card.get("card_faces") or []
        if card_faces:
            return self._download_multi_face_card(card, card_faces, size)

        success, message, _ = self._download_face_asset(
            uuid=uuid,
            face_index=0,
            name=name,
            image_uris=card.get("image_uris") or {},
            size=size,
            card=card,
        )
        return success, message

    def _download_multi_face_card(
        self, card: dict[str, Any], faces: list[dict[str, Any]], size: str
    ) -> tuple[bool, str]:
        uuid = card.get("id")
        if not uuid:
            return False, "Missing UUID for multi-face card"

        # Single-image layouts (split, flip, adventure, prepare) carry one
        # physical image at the top level; per-face image_uris are empty.
        # Two-image layouts (transform, modal_dfc, reversible_card) put the
        # image_uris on each face. Dispatch by presence rather than by layout
        # name so future Scryfall layouts with the same shape work without code
        # changes.
        if not any((face.get("image_uris") or {}) for face in faces):
            return self._download_single_image_multi_face(card, size)

        downloaded = 0
        front_path: Path | None = None
        for idx, face in enumerate(faces):
            face_name = face.get("name") or card.get("name", "Unknown")
            image_uris = face.get("image_uris") or {}
            success, _, file_path = self._download_face_asset(
                uuid=uuid,
                face_index=idx,
                name=face_name,
                image_uris=image_uris,
                size=size,
                card=card,
            )
            if success:
                downloaded += 1
                if idx == 0:
                    front_path = file_path

        # Store combined display name pointing to the front face
        combined_name = card.get("name")
        if combined_name and front_path:
            self.cache.add_image(
                uuid=uuid,
                name=combined_name,
                set_code=card.get("set", ""),
                collector_number=card.get("collector_number", ""),
                image_size=size,
                file_path=front_path,
                scryfall_uri=card.get("scryfall_uri"),
                artist=card.get("artist"),
                face_index=-1,
            )

        if downloaded == 0:
            return False, f"No downloadable faces for {card.get('name', 'Unknown')}"
        return True, f"Downloaded {downloaded} faces for {card.get('name', 'Unknown')}"

    def _download_single_image_multi_face(
        self, card: dict[str, Any], size: str
    ) -> tuple[bool, str]:
        uuid = card.get("id") or ""
        combined_name = card.get("name", "Unknown")
        image_uris = card.get("image_uris") or {}

        success, message, _ = self._download_face_asset(
            uuid=uuid,
            face_index=0,
            name=combined_name,
            image_uris=image_uris,
            size=size,
            card=card,
        )
        return success, message

    def _download_face_asset(
        self,
        uuid: str,
        face_index: int,
        name: str,
        image_uris: dict[str, Any],
        size: str,
        card: dict[str, Any],
    ) -> tuple[bool, str, Path | None]:
        if self.cache.is_cached(uuid, size, face_index=face_index):
            path = self.cache.get_image_by_uuid(uuid, size, face_index=face_index)
            return True, f"Already cached: {name}", path

        image_url = image_uris.get(size) or image_uris.get("normal")
        if not image_url:
            return False, f"No {size} image for {name}", None

        try:
            resp = self.session.get(image_url, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug(f"Failed to download {name}: {exc}")
            return False, f"Error: {name} - {exc}", None

        ext = "png" if size == "png" else "jpg"
        filename = self._build_face_filename(uuid, face_index, ext)
        file_path = self.cache.cache_dir / size / filename

        try:
            atomic_write_bytes(file_path, resp.content)
        except Exception as exc:
            logger.debug(f"Failed to write image {name}: {exc}")
            return False, f"Error saving image for {name}: {exc}", None

        self.cache.add_image(
            uuid=uuid,
            name=name,
            set_code=card.get("set", ""),
            collector_number=card.get("collector_number", ""),
            image_size=size,
            file_path=file_path,
            scryfall_uri=card.get("scryfall_uri"),
            artist=card.get("artist"),
            face_index=face_index,
        )
        return True, f"Downloaded: {name}", file_path

    @staticmethod
    def _build_face_filename(uuid: str, face_index: int, ext: str) -> str:
        if face_index <= 0:
            return f"{uuid}.{ext}"
        return f"{uuid}-f{face_index}.{ext}"

    def download_all_images(
        self,
        size: str = "normal",
        max_cards: int | None = None,
        progress_callback: callable | None = None,
    ) -> dict[str, Any]:
        from services.image_service import schemas as _schemas

        if not _schemas.BULK_DATA_CACHE.exists():
            return {
                "success": False,
                "error": "Bulk data not downloaded. Call download_bulk_metadata() first.",
            }

        try:
            from utils.json_io import fast_load

            with locked_path(_schemas.BULK_DATA_CACHE):
                cards_data = fast_load(_schemas.BULK_DATA_CACHE)
            if max_cards:
                cards_data = cards_data[:max_cards]

            total = len(cards_data)
            completed = 0
            successful = 0
            failed = 0
            skipped = 0

            logger.info(f"Starting bulk download of {total} cards ({size} size)")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._download_single_image, card, size): card
                    for card in cards_data
                }

                for future in as_completed(futures):
                    completed += 1
                    try:
                        success, message = future.result()
                        if success:
                            if "Already cached" in message:
                                skipped += 1
                            else:
                                successful += 1
                        else:
                            failed += 1
                            logger.debug(message)
                    except Exception as exc:
                        failed += 1
                        logger.debug(f"Exception in download: {exc}")

                    # Progress callback
                    if progress_callback and completed % SCRYFALL_DOWNLOAD_PROGRESS_INTERVAL == 0:
                        progress_callback(
                            completed,
                            total,
                            f"{successful} downloaded, {skipped} cached, {failed} failed",
                        )

            logger.info(
                f"Bulk download complete: {successful} downloaded, {skipped} cached, {failed} failed"
            )

            return {
                "success": True,
                "total": total,
                "downloaded": successful,
                "skipped": skipped,
                "failed": failed,
            }

        except Exception as exc:
            logger.exception("Bulk download failed")
            return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Singleton + high-level convenience helpers
# ---------------------------------------------------------------------------

# Singleton instance
_cache_instance: CardImageCache | None = None


def get_cache() -> CardImageCache:
    """Get singleton CardImageCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CardImageCache()
    return _cache_instance


def get_card_image(card_name: str, size: str = "normal") -> Path | None:
    """Get card image from cache."""
    cache = get_cache()
    return cache.get_image_path(card_name, size)


def download_bulk_images(
    size: str = "normal", max_cards: int | None = None, progress_callback: callable | None = None
) -> dict[str, Any]:
    """High-level function to download all card images."""
    cache = get_cache()
    downloader = BulkImageDownloader(cache)

    # Download metadata first
    success, msg = downloader.download_bulk_metadata()
    if not success:
        return {"success": False, "error": msg}

    # Download images
    return downloader.download_all_images(size, max_cards, progress_callback)


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    cache = get_cache()
    return cache.get_cache_stats()


__all__ = [
    "BulkImageDownloader",
    "download_bulk_images",
    "get_cache",
    "get_cache_stats",
    "get_card_image",
]
