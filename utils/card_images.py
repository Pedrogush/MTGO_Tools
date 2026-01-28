"""High-throughput card image downloader and cache manager.

This module provides functionality to:
1. Download Scryfall bulk data to get all card metadata
2. Fetch card images from Scryfall CDN (no rate limits on image CDN)
3. Maintain a local SQLite database of cached images
4. Support concurrent downloads for high throughput

Architecture:
- Uses Scryfall bulk data JSON for card metadata
- Downloads images from cards.scryfall.io CDN (no rate limits)
- Stores images locally with UUID-based filenames
- SQLite database tracks downloaded images and metadata
- Supports multiple image sizes (small, normal, large, png)
"""

from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017
from pathlib import Path, PureWindowsPath
from typing import Any

import requests
from loguru import logger

from utils.card_image_path_resolver import CardImagePathResolver
from utils.card_image_store import CardImageStore
from utils.constants import BULK_DATA_CACHE_FRESHNESS_SECONDS, CACHE_DIR

# Image cache configuration
IMAGE_CACHE_DIR = CACHE_DIR / "card_images"
IMAGE_DB_PATH = IMAGE_CACHE_DIR / "images.db"
BULK_DATA_CACHE = IMAGE_CACHE_DIR / "bulk_data.json"
PRINTING_INDEX_VERSION = 2
PRINTING_INDEX_CACHE = IMAGE_CACHE_DIR / f"printings_v{PRINTING_INDEX_VERSION}.json"

# Image size options (in order of preference for storage)
IMAGE_SIZES = {
    "small": "small",  # 146x204 - thumbnails
    "normal": "normal",  # 488x680 - default
    "large": "large",  # 672x936 - high quality
    "png": "png",  # 745x1040 - highest quality, transparent
}

# Download configuration
BULK_DATA_URL = "https://api.scryfall.com/bulk-data/default-cards"
MAX_WORKERS = 10  # Concurrent download threads
CHUNK_SIZE = 8192  # Download chunk size
REQUEST_TIMEOUT = 30  # Seconds


class CardImageCache:
    """Manages local card image cache with SQLite database."""

    def __init__(self, cache_dir: Path = IMAGE_CACHE_DIR, db_path: Path = IMAGE_DB_PATH):
        self.cache_dir = Path(cache_dir)
        self.db_path = Path(db_path)
        self._ensure_directories()
        self.cache_dir = self.cache_dir.resolve()
        self.db_path = self.db_path.resolve()
        self._path_resolver = CardImagePathResolver(self.cache_dir)
        self._store = CardImageStore(self.db_path)

    def _ensure_directories(self) -> None:
        """Create cache directories if they don't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for size in IMAGE_SIZES.values():
            (self.cache_dir / size).mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Path resolution helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, stored_path: str) -> Path:
        """Convert a stored path string into a usable filesystem Path."""
        return self._path_resolver.resolve_path(stored_path)

    def _first_existing_path(self, rows: list[tuple[str, ...]]) -> Path | None:
        """Return the first resolved path that exists on disk, or None."""
        for (file_path_str,) in rows:
            path = self._resolve_path(file_path_str)
            if path.exists():
                return path
        return None

    # ------------------------------------------------------------------
    # Public read interface
    # ------------------------------------------------------------------

    def get_image_path(self, card_name: str, size: str = "normal") -> Path | None:
        """Get cached image path for a card name.

        Args:
            card_name: Card name (case-insensitive)
            size: Image size (small, normal, large, png)

        Returns:
            Path to cached image file, or None if not cached
        """
        rows = self._store.get_rows_by_name(card_name, size)
        if rows:
            found = self._first_existing_path(rows[:1])
            if found:
                return found

        # Fall back to double-faced alias lookup
        return self._lookup_double_faced_alias(card_name, size)

    def _lookup_double_faced_alias(self, card_name: str, size: str) -> Path | None:
        """Attempt to resolve legacy front/back alias lookups."""
        alias = (card_name or "").strip()
        if not alias or "//" in alias:
            return None

        alias_lower = alias.lower()
        for pattern in (f"{alias_lower} // %", f"% // {alias_lower}"):
            rows = self._store.get_rows_by_name_pattern(pattern, size)
            if rows:
                found = self._first_existing_path(rows[:1])
                if found:
                    return found
        return None

    def get_image_by_uuid(
        self, uuid: str, size: str = "normal", face_index: int | None = 0
    ) -> Path | None:
        """Get cached image path by Scryfall UUID."""
        rows = self._store.get_rows_by_uuid(uuid, size, face_index=face_index)
        if rows:
            return self._first_existing_path(rows[:1])
        return None

    def get_image_paths_by_uuid(self, uuid: str, size: str = "normal") -> list[Path]:
        """Return all cached face images for a UUID, ordered by face index."""
        rows = self._store.get_all_face_rows(uuid, size)
        paths: list[Path] = []
        for _, file_path in rows:
            path = self._resolve_path(file_path)
            if path.exists():
                paths.append(path)
        return paths

    # ------------------------------------------------------------------
    # Public write interface (delegates to store)
    # ------------------------------------------------------------------

    def add_image(
        self,
        uuid: str,
        name: str,
        set_code: str,
        collector_number: str,
        image_size: str,
        file_path: Path,
        scryfall_uri: str | None = None,
        artist: str | None = None,
        face_index: int = 0,
    ) -> None:
        """Add image record to database."""
        self._store.add_image(
            uuid=uuid,
            name=name,
            set_code=set_code,
            collector_number=collector_number,
            image_size=image_size,
            file_path=file_path,
            scryfall_uri=scryfall_uri,
            artist=artist,
            face_index=face_index,
        )

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self._store.get_cache_stats()

    def get_bulk_data_record(self) -> tuple[str | None, str | None]:
        """Return (downloaded_at, bulk_data_uri) for the cached bulk-data snapshot."""
        return self._store.get_bulk_data_record()

    def upsert_bulk_data_meta(
        self, downloaded_at: str, total_cards: int, bulk_data_uri: str
    ) -> None:
        """Persist updated bulk-data metadata."""
        self._store.upsert_bulk_data_meta(downloaded_at, total_cards, bulk_data_uri)

    def is_cached(self, uuid: str, size: str = "normal", face_index: int | None = 0) -> bool:
        """Check if image is already cached."""
        return self.get_image_by_uuid(uuid, size, face_index=face_index) is not None


class BulkImageDownloader:
    """High-throughput bulk image downloader using Scryfall data."""

    def __init__(self, cache: CardImageCache, max_workers: int = MAX_WORKERS):
        self.cache = cache
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MTGOMetagameCrawler/1.0"})

    def _fetch_bulk_metadata(self) -> dict[str, Any]:
        """Fetch the bulk data metadata from Scryfall."""
        logger.info("Fetching bulk data metadata from Scryfall...")
        resp = self.session.get(BULK_DATA_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _get_cached_bulk_data_record(self) -> tuple[str | None, str | None]:
        """Return the saved bulk data metadata (updated_at, download URI)."""
        return self.cache.get_bulk_data_record()

    def is_bulk_data_outdated(
        self, max_staleness_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any]]:
        """Determine whether the cached bulk data is outdated compared to the vendor."""
        metadata = self._fetch_bulk_metadata()
        download_uri = metadata.get("download_uri")
        updated_at = metadata.get("updated_at")

        if not BULK_DATA_CACHE.exists():
            return True, metadata

        cached_updated, cached_uri = self._get_cached_bulk_data_record()
        if updated_at and download_uri and cached_updated and cached_uri:
            if updated_at == cached_updated and download_uri == cached_uri:
                return False, metadata
            return True, metadata

        # Fallback to age-based check when the vendor metadata lacks timestamps/URIs
        threshold = max_staleness_seconds or BULK_DATA_CACHE_FRESHNESS_SECONDS
        try:
            age_seconds = datetime.now().timestamp() - BULK_DATA_CACHE.stat().st_mtime
            if age_seconds < threshold:
                return False, metadata
        except OSError:
            pass

        return True, metadata

    def download_bulk_metadata(self, force: bool = False) -> tuple[bool, str]:
        """Download Scryfall bulk data JSON.

        Args:
            force: Force re-download even if cached

        Returns:
            (success, message)
        """
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
            and BULK_DATA_CACHE.exists()
            and remote_updated_at
            and cached_updated == remote_updated_at
            and cached_uri == download_uri
        )
        if cache_matches:
            logger.info("Using cached bulk data (vendor metadata is current)")
            return True, "Using cached bulk data"

        try:
            logger.info(f"Downloading bulk data from {download_uri}")
            logger.info(f"Size: {metadata.get('size', 0) / (1024 * 1024):.1f} MB")

            # Download with progress
            resp = self.session.get(download_uri, stream=True, timeout=120)
            resp.raise_for_status()

            with BULK_DATA_CACHE.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    f.write(chunk)

            # Update database metadata (defer card count to avoid parsing 500MB file)
            self.cache.upsert_bulk_data_meta(
                downloaded_at=remote_updated_at or datetime.now(UTC).isoformat(),
                total_cards=0,
                bulk_data_uri=download_uri,
            )

            logger.info("Bulk data downloaded successfully")
            return True, "Bulk data downloaded"

        except Exception as exc:
            logger.exception("Failed to download bulk data")
            return False, f"Error: {exc}"

    def _download_single_image(
        self, card: dict[str, Any], size: str = "normal"
    ) -> tuple[bool, str]:
        """Download a single card image.

        Args:
            card: Card object from bulk data
            size: Image size to download

        Returns:
            (success, message)
        """
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
        """Download images for each face of a double-faced card."""
        uuid = card.get("id")
        if not uuid:
            return False, "Missing UUID for multi-face card"

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

    def _download_face_asset(
        self,
        uuid: str,
        face_index: int,
        name: str,
        image_uris: dict[str, Any],
        size: str,
        card: dict[str, Any],
    ) -> tuple[bool, str, Path | None]:
        """Download a specific face image."""
        if self.cache.is_cached(uuid, size, face_index=face_index):
            path = self.cache.get_image_by_uuid(uuid, size, face_index=face_index)
            return True, f"Already cached: {name}", path

        image_url = image_uris.get(size) or image_uris.get("normal")
        if not image_url:
            return False, f"No {size} image for {name}", None

        try:
            resp = self.session.get(image_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug(f"Failed to download {name}: {exc}")
            return False, f"Error: {name} - {exc}", None

        ext = "png" if size == "png" else "jpg"
        filename = self._build_face_filename(uuid, face_index, ext)
        file_path = self.cache.cache_dir / size / filename

        try:
            with file_path.open("wb") as fh:
                fh.write(resp.content)
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
        """Return deterministic filename for a face image."""
        if face_index <= 0:
            return f"{uuid}.{ext}"
        return f"{uuid}-f{face_index}.{ext}"

    def download_all_images(
        self,
        size: str = "normal",
        max_cards: int | None = None,
        progress_callback: callable | None = None,
    ) -> dict[str, Any]:
        """Download all card images from bulk data.

        Args:
            size: Image size to download (small, normal, large, png)
            max_cards: Limit number of cards (for testing)
            progress_callback: Callback function(completed, total, message)

        Returns:
            Statistics dict
        """
        if not BULK_DATA_CACHE.exists():
            return {
                "success": False,
                "error": "Bulk data not downloaded. Call download_bulk_metadata() first.",
            }

        try:
            cards_data = json.loads(BULK_DATA_CACHE.read_text(encoding="utf-8"))
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
                    if progress_callback and completed % 100 == 0:
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


def _collect_face_aliases(card: dict[str, Any], display_name: str) -> set[str]:
    """Return alternate face names for MDFCs, split, and adventure cards."""
    aliases: set[str] = set()
    for raw_face in card.get("card_faces") or []:
        face_name = (raw_face.get("name") or "").strip()
        if face_name:
            aliases.add(face_name)

    if "//" in display_name:
        for piece in display_name.split("//"):
            face_name = piece.strip()
            if face_name:
                aliases.add(face_name)

    display_key = display_name.strip().lower()
    return {alias for alias in aliases if alias.lower() != display_key}


def _load_printing_index_payload() -> dict[str, Any] | None:
    """Load the cached card printings index if available."""
    if not PRINTING_INDEX_CACHE.exists():
        return None
    try:
        with PRINTING_INDEX_CACHE.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        logger.warning(f"Failed to read printings index cache: {exc}")
        return None
    if payload.get("version") != PRINTING_INDEX_VERSION:
        logger.info("Discarding printings index cache due to version mismatch")
        return None
    return payload


def ensure_printing_index_cache(force: bool = False) -> dict[str, Any]:
    """Ensure a compact card printings index exists for fast wx lookups."""
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    existing = None if force else _load_printing_index_payload()
    bulk_mtime = BULK_DATA_CACHE.stat().st_mtime if BULK_DATA_CACHE.exists() else None

    if existing and (bulk_mtime is None or existing.get("bulk_mtime", 0) >= bulk_mtime):
        return existing

    if bulk_mtime is None:
        raise FileNotFoundError("Bulk data cache not found; cannot build printings index")

    logger.info("Building card printings index from bulk data…")
    with BULK_DATA_CACHE.open("r", encoding="utf-8") as fh:
        cards = json.load(fh)

    by_name: dict[str, list[dict[str, Any]]] = {}
    total_printings = 0
    for card in cards:
        name = (card.get("name") or "").strip()
        uuid = card.get("id")
        if not name or not uuid:
            continue
        key = name.lower()
        entry = {
            "id": uuid,
            "set": (card.get("set") or "").upper(),
            "set_name": card.get("set_name") or "",
            "collector_number": card.get("collector_number") or "",
            "released_at": card.get("released_at") or "",
        }
        by_name.setdefault(key, []).append(entry)
        for alias in _collect_face_aliases(card, name):
            alias_key = alias.lower()
            if alias_key == key:
                continue
            by_name.setdefault(alias_key, []).append(entry)
        total_printings += 1

    for entries in by_name.values():
        entries.sort(key=lambda c: c.get("released_at") or "", reverse=True)

    payload = {
        "version": PRINTING_INDEX_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "bulk_mtime": bulk_mtime,
        "unique_names": len(by_name),
        "total_printings": total_printings,
        "data": by_name,
    }

    try:
        with PRINTING_INDEX_CACHE.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        logger.info(
            "Cached card printings index ({unique_names} names, {total_printings} printings)",
            unique_names=payload["unique_names"],
            total_printings=payload["total_printings"],
        )
    except Exception as exc:
        logger.warning(f"Failed to write printings index cache: {exc}")

    return payload


# Singleton instance
_cache_instance: CardImageCache | None = None


def get_cache() -> CardImageCache:
    """Get singleton CardImageCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CardImageCache()
    return _cache_instance


def get_card_image(card_name: str, size: str = "normal") -> Path | None:
    """Get card image from cache.

    Args:
        card_name: Card name (case-insensitive)
        size: Image size (small, normal, large, png)

    Returns:
        Path to image file, or None if not cached
    """
    cache = get_cache()
    return cache.get_image_path(card_name, size)


def download_bulk_images(
    size: str = "normal", max_cards: int | None = None, progress_callback: callable | None = None
) -> dict[str, Any]:
    """High-level function to download all card images.

    Args:
        size: Image size (small, normal, large, png)
        max_cards: Limit download (for testing)
        progress_callback: Progress callback(completed, total, message)

    Returns:
        Statistics dict
    """
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
    "CardImageCache",
    "BulkImageDownloader",
    "PRINTING_INDEX_CACHE",
    "get_cache",
    "get_card_image",
    "download_bulk_images",
    "get_cache_stats",
    "ensure_printing_index_cache",
]
