"""Facade module for the card image cache subsystem.

Public surface:
- ``CardImageCache`` -- thin orchestrator that coordinates path resolution
  and SQLite persistence.
- ``BulkImageDownloader`` -- high-throughput Scryfall image downloader.
- ``ensure_printing_index_cache`` -- build/load the compact printings index.
- Singleton helpers: ``get_cache``, ``get_card_image``, ``get_cache_stats``.

Implementation details live in the sibling modules:
- ``card_image_path_resolver`` -- Windows/WSL path normalisation.
- ``card_image_store`` -- SQLite schema, migrations, and queries.
- ``card_image_downloader`` -- HTTP download orchestration.
- ``card_printing_index`` -- printings index builder.

All module-level constants defined here (``IMAGE_CACHE_DIR``,
``BULK_DATA_CACHE``, ``PRINTING_INDEX_CACHE``, etc.) remain in this file so
that tests which monkeypatch them continue to work without changes.
"""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Any

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017

from utils.card_image_path_resolver import CardImagePathResolver
from utils.card_image_store import CardImageStore
from utils.constants import CACHE_DIR

# ---------------------------------------------------------------------------
# Path constants (stay here so monkeypatching in tests keeps working)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# CardImageCache -- thin orchestrator
# ---------------------------------------------------------------------------


class CardImageCache:
    """Orchestrates path resolution and SQLite persistence for card images.

    Delegates storage to ``CardImageStore`` and path translation to
    ``CardImagePathResolver``.  Consumers interact exclusively through
    this class's public methods.
    """

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


# ---------------------------------------------------------------------------
# Re-exports from dedicated modules (backward compatibility)
# ---------------------------------------------------------------------------

# BulkImageDownloader -- download orchestration
from utils.card_image_downloader import BulkImageDownloader  # noqa: E402, F401

# Printing index -- face alias collection and index cache builder
from utils.card_printing_index import collect_face_aliases as _collect_face_aliases  # noqa: E402, F401
from utils.card_printing_index import ensure_printing_index_cache  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Module-level singleton and convenience helpers
# ---------------------------------------------------------------------------

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
    "IMAGE_CACHE_DIR",
    "IMAGE_DB_PATH",
    "BULK_DATA_CACHE",
    "PRINTING_INDEX_CACHE",
    "IMAGE_SIZES",
    "get_cache",
    "get_card_image",
    "download_bulk_images",
    "get_cache_stats",
    "ensure_printing_index_cache",
]
