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
from dataclasses import dataclass
from datetime import datetime, timezone

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017
from pathlib import Path, PureWindowsPath
from typing import Any

import requests
from loguru import logger

from utils.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_stream,
    locked_path,
)
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
SCRYFALL_CARD_ID_URL = "https://api.scryfall.com/cards/{card_id}"
SCRYFALL_CARD_SET_URL = "https://api.scryfall.com/cards/{set_code}/{collector_number}"
MAX_WORKERS = 10  # Concurrent download threads
CHUNK_SIZE = 8192  # Download chunk size
REQUEST_TIMEOUT = 30  # Seconds


@dataclass(frozen=True)
class CardImageRequest:
    """Represents a single card image download request."""

    card_name: str
    uuid: str | None
    set_code: str | None
    collector_number: str | None
    size: str = "normal"

    def queue_key(self) -> tuple[str, str, str, str]:
        """Return a stable key for deduping requests."""
        if self.uuid:
            return ("uuid", self.uuid.lower(), self.size, "")
        set_code = (self.set_code or "").lower()
        collector = (self.collector_number or "").lower()
        return ("set", set_code, collector, self.size)

    def can_fetch(self) -> bool:
        """Return True when there is enough data to fetch from Scryfall."""
        if self.uuid:
            return True
        return bool(self.set_code and self.collector_number)


class CardImageCache:
    """Manages local card image cache with SQLite database."""

    def __init__(self, cache_dir: Path = IMAGE_CACHE_DIR, db_path: Path = IMAGE_DB_PATH):
        self.cache_dir = Path(cache_dir)
        self.db_path = Path(db_path)
        self._ensure_directories()
        self.cache_dir = self.cache_dir.resolve()
        self.db_path = self.db_path.resolve()
        self._path_roots = self._build_path_roots()
        self._init_database()

    def _ensure_directories(self) -> None:
        """Create cache directories if they don't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for size in IMAGE_SIZES.values():
            (self.cache_dir / size).mkdir(exist_ok=True)

    def _build_path_roots(self) -> list[Path]:
        """Precompute base directories used to resolve relative cache entries."""
        roots: list[Path] = []
        candidates = [
            Path.cwd(),
            self.cache_dir,
            self.cache_dir.parent,
        ]
        # Include grandparent (project root) if available
        try:
            candidates.append(self.cache_dir.parents[1])
        except IndexError:
            pass
        seen = set()
        for entry in candidates:
            resolved = entry.resolve()
            if resolved not in seen:
                seen.add(resolved)
                roots.append(resolved)
        return roots

    def _init_database(self) -> None:
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            self._create_schema(conn)
            self._ensure_face_index_support(conn)
            conn.commit()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Create base tables if they do not exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS card_images (
                uuid TEXT NOT NULL,
                face_index INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                set_code TEXT,
                collector_number TEXT,
                image_size TEXT NOT NULL,
                file_path TEXT NOT NULL,
                downloaded_at TEXT NOT NULL,
                scryfall_uri TEXT,
                artist TEXT,
                PRIMARY KEY (uuid, face_index, image_size)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_card_name ON card_images(name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_set_code ON card_images(set_code)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bulk_data_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                downloaded_at TEXT NOT NULL,
                total_cards INTEGER NOT NULL,
                bulk_data_uri TEXT NOT NULL
            )
        """)

    def _ensure_face_index_support(self, conn: sqlite3.Connection) -> None:
        """Ensure the card_images table can store multiple faces per UUID."""
        info = conn.execute("PRAGMA table_info(card_images)").fetchall()
        has_face_index = any(column[1] == "face_index" for column in info)
        if has_face_index:
            return

        logger.info("Migrating card_images table to support multi-face entries")
        conn.execute("ALTER TABLE card_images RENAME TO card_images_old")
        self._create_schema(conn)
        conn.execute("""
            INSERT INTO card_images (
                uuid,
                face_index,
                name,
                set_code,
                collector_number,
                image_size,
                file_path,
                downloaded_at,
                scryfall_uri,
                artist
            )
            SELECT
                uuid,
                0,
                name,
                set_code,
                collector_number,
                image_size,
                file_path,
                downloaded_at,
                scryfall_uri,
                artist
            FROM card_images_old
        """)
        conn.execute("DROP TABLE card_images_old")

    def _resolve_path(self, stored_path: str) -> Path:
        """Convert stored path strings into usable filesystem Paths.

        Handles Windows-style separators and WSL drive prefixes when running on POSIX.
        """
        raw = stored_path.strip()
        path = Path(raw)
        resolved = self._normalize_path(path)
        if resolved.exists():
            return resolved

        # Normalize backslashes to forward slashes (works on all OSes)
        if "\\" in raw:
            normalized = raw.replace("\\", "/")
            path = Path(normalized)
            normalized_resolved = self._normalize_path(path)
            if normalized_resolved.exists():
                return normalized_resolved

            # Interpret as Windows path and convert to current platform
            try:
                win_path = Path(PureWindowsPath(raw))
                if win_path.exists():
                    return win_path
            except Exception as exc:
                logger.debug("Failed to normalize Windows path '%s': %s", raw, exc)

            # Translate Windows drive letters for WSL paths (e.g., C:\ -> /mnt/c/)
            if os.name != "nt" and len(raw) >= 3 and raw[1] == ":" and raw[2] in ("\\", "/"):
                drive = raw[0].lower()
                remainder = raw[3:].replace("\\", "/")
                wsl_path = Path("/mnt") / drive / remainder
                if wsl_path.exists():
                    return wsl_path

        return resolved

    def _normalize_path(self, path: Path) -> Path:
        """Resolve absolute paths or attempt to rebuild relatives under known roots."""
        try:
            if path.is_absolute():
                return path
        except OSError:
            pass

        rel = self._resolve_relative_path(path)
        if rel is not None:
            return rel

        return path

    def _resolve_relative_path(self, relative: Path) -> Path | None:
        """Attempt to resolve a relative cache entry against known roots."""
        for root in self._path_roots:
            candidate = (root / relative).resolve()
            if candidate.exists():
                return candidate
        return None

    def get_image_path(self, card_name: str, size: str = "normal") -> Path | None:
        """Get cached image path for a card name.

        Args:
            card_name: Card name (case-insensitive)
            size: Image size (small, normal, large, png)

        Returns:
            Path to cached image file, or None if not cached
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) = LOWER(?) AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (card_name, size),
            )
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path

            alias_path = self._lookup_double_faced_alias(conn, card_name, size)
            if alias_path:
                return alias_path
        return None

    def _lookup_double_faced_alias(
        self, conn: sqlite3.Connection, card_name: str, size: str
    ) -> Path | None:
        """Attempt to resolve legacy front/back alias lookups."""
        alias = (card_name or "").strip()
        if not alias or "//" in alias:
            return None

        alias_lower = alias.lower()
        patterns = (
            f"{alias_lower} // %",
            f"% // {alias_lower}",
        )

        for pattern in patterns:
            cursor = conn.execute(
                """
                SELECT file_path
                FROM card_images
                WHERE LOWER(name) LIKE ? AND image_size = ?
                ORDER BY face_index
                LIMIT 1
                """,
                (pattern, size),
            )
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path
        return None

    def get_image_by_uuid(
        self, uuid: str, size: str = "normal", face_index: int | None = 0
    ) -> Path | None:
        """Get cached image path by Scryfall UUID."""
        query = "SELECT file_path FROM card_images WHERE uuid = ? AND image_size = ? ORDER BY face_index"
        params: tuple[object, ...]
        if face_index is None:
            params = (uuid, size)
        else:
            query = "SELECT file_path FROM card_images WHERE uuid = ? AND face_index = ? AND image_size = ?"
            params = (uuid, face_index, size)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if row:
                path = self._resolve_path(row[0])
                if path.exists():
                    return path
        return None

    def get_image_paths_by_uuid(self, uuid: str, size: str = "normal") -> list[Path]:
        """Return all cached face images for a UUID, ordered by face index."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT face_index, file_path
                FROM card_images
                WHERE uuid = ? AND image_size = ? AND face_index >= 0
                ORDER BY face_index
                """,
                (uuid, size),
            ).fetchall()
        paths: list[Path] = []
        for _, file_path in rows:
            path = self._resolve_path(file_path)
            if path.exists():
                paths.append(path)
        return paths

    def add_image(
        self,
        uuid: str,
        name: str,
        set_code: str,
        collector_number: str,
        image_size: str,
        file_path: Path,
        scryfall_uri: str = None,
        artist: str = None,
        face_index: int = 0,
    ) -> None:
        """Add image record to database."""
        file_path_str = str(Path(file_path).resolve())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO card_images
                (uuid, face_index, name, set_code, collector_number, image_size, file_path,
                 downloaded_at, scryfall_uri, artist)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    uuid,
                    face_index,
                    name,
                    set_code,
                    collector_number,
                    image_size,
                    file_path_str,
                    datetime.now(UTC).isoformat(),
                    scryfall_uri,
                    artist,
                ),
            )
            conn.commit()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(DISTINCT uuid) FROM card_images").fetchone()[0]
            by_size = {}
            for size in IMAGE_SIZES.values():
                count = conn.execute(
                    "SELECT COUNT(*) FROM card_images WHERE image_size = ?", (size,)
                ).fetchone()[0]
                by_size[size] = count

            bulk_meta = conn.execute(
                "SELECT downloaded_at, total_cards FROM bulk_data_meta WHERE id = 1"
            ).fetchone()

        return {
            "unique_cards": total,
            "by_size": by_size,
            "bulk_data_date": bulk_meta[0] if bulk_meta else None,
            "bulk_total_cards": bulk_meta[1] if bulk_meta else None,
        }

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

    def fetch_card_by_id(self, card_id: str) -> dict[str, Any]:
        """Fetch card data from Scryfall by UUID."""
        url = SCRYFALL_CARD_ID_URL.format(card_id=card_id)
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def fetch_card_by_set(
        self, set_code: str, collector_number: str
    ) -> dict[str, Any]:
        """Fetch card data from Scryfall by set code and collector number."""
        url = SCRYFALL_CARD_SET_URL.format(
            set_code=set_code.lower(), collector_number=collector_number
        )
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def download_card_image_by_id(self, card_id: str, size: str = "normal") -> tuple[bool, str]:
        """Fetch card data by UUID and download its image(s)."""
        card = self.fetch_card_by_id(card_id)
        return self._download_single_image(card, size)

    def download_card_image_by_set(
        self, set_code: str, collector_number: str, size: str = "normal"
    ) -> tuple[bool, str]:
        """Fetch card data by set/collector number and download its image(s)."""
        card = self.fetch_card_by_set(set_code, collector_number)
        return self._download_single_image(card, size)

    def _get_cached_bulk_data_record(self) -> tuple[str | None, str | None]:
        """Return the saved bulk data metadata (updated_at, download URI)."""
        with sqlite3.connect(self.cache.db_path) as conn:
            row = conn.execute(
                "SELECT downloaded_at, bulk_data_uri FROM bulk_data_meta WHERE id = 1"
            ).fetchone()
        if row:
            return row[0], row[1]
        return None, None

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

            atomic_write_stream(BULK_DATA_CACHE, resp.iter_content(chunk_size=CHUNK_SIZE))

            # Update database metadata (defer card count to avoid parsing 500MB file)
            with sqlite3.connect(self.cache.db_path) as conn:
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
            with locked_path(BULK_DATA_CACHE):
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
        with locked_path(PRINTING_INDEX_CACHE):
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
    with locked_path(BULK_DATA_CACHE):
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
        atomic_write_json(PRINTING_INDEX_CACHE, payload, separators=(",", ":"))
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
    "CardImageRequest",
    "BulkImageDownloader",
    "PRINTING_INDEX_CACHE",
    "get_cache",
    "get_card_image",
    "download_bulk_images",
    "get_cache_stats",
    "ensure_printing_index_cache",
]
