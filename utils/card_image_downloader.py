"""High-throughput bulk image downloader for the card image cache.

Downloads Scryfall bulk-data JSON and individual card images using a
thread pool, delegating persistence to ``CardImageCache``.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from loguru import logger

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017

from utils.constants import BULK_DATA_CACHE_FRESHNESS_SECONDS

# ---------------------------------------------------------------------------
# Module-level configuration constants (kept here so card_images.py can
# re-export them without circular imports).
# ---------------------------------------------------------------------------
BULK_DATA_URL = "https://api.scryfall.com/bulk-data/default-cards"
MAX_WORKERS = 10  # Concurrent download threads
CHUNK_SIZE = 8192  # Download chunk size in bytes
REQUEST_TIMEOUT = 30  # Seconds per HTTP request


def _build_face_filename(uuid: str, face_index: int, ext: str) -> str:
    """Return a deterministic filename for a single face image."""
    if face_index <= 0:
        return f"{uuid}.{ext}"
    return f"{uuid}-f{face_index}.{ext}"


class BulkImageDownloader:
    """High-throughput bulk image downloader using Scryfall data.

    Requires a ``CardImageCache`` instance for persistence.  The downloader
    never touches SQLite directly -- all reads and writes go through the
    cache's public interface.
    """

    def __init__(self, cache: Any, max_workers: int = MAX_WORKERS) -> None:
        # Accept ``Any`` to avoid a hard import cycle; callers always pass
        # a CardImageCache instance.  The duck-typed interface is:
        #   cache.cache_dir: Path
        #   cache.is_cached(uuid, size, face_index=...) -> bool
        #   cache.get_image_by_uuid(uuid, size, face_index=...) -> Path | None
        #   cache.add_image(...) -> None
        #   cache.get_bulk_data_record() -> tuple[str|None, str|None]
        #   cache.upsert_bulk_data_meta(downloaded_at, total_cards, bulk_data_uri) -> None
        self.cache = cache
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MTGOMetagameCrawler/1.0"})

    # ------------------------------------------------------------------
    # Bulk-data metadata helpers
    # ------------------------------------------------------------------

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
        self,
        max_staleness_seconds: int | None = None,
        bulk_data_cache_path: Path | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Determine whether the cached bulk data is outdated compared to the vendor.

        Args:
            max_staleness_seconds: Override the default freshness threshold.
            bulk_data_cache_path: Path to the bulk_data.json file.  Defaults
                to the module-level ``BULK_DATA_CACHE`` when called via the
                facade in ``card_images``.  Callers on the facade side pass it
                explicitly; internal tests may override it.
        """
        # Import here to avoid circular dependency with card_images
        from utils.card_images import BULK_DATA_CACHE

        cache_path = bulk_data_cache_path or BULK_DATA_CACHE

        metadata = self._fetch_bulk_metadata()
        download_uri = metadata.get("download_uri")
        updated_at = metadata.get("updated_at")

        if not cache_path.exists():
            return True, metadata

        cached_updated, cached_uri = self._get_cached_bulk_data_record()
        if updated_at and download_uri and cached_updated and cached_uri:
            if updated_at == cached_updated and download_uri == cached_uri:
                return False, metadata
            return True, metadata

        # Fallback to age-based check when the vendor metadata lacks timestamps/URIs
        threshold = max_staleness_seconds or BULK_DATA_CACHE_FRESHNESS_SECONDS
        try:
            age_seconds = datetime.now().timestamp() - cache_path.stat().st_mtime
            if age_seconds < threshold:
                return False, metadata
        except OSError:
            pass

        return True, metadata

    # ------------------------------------------------------------------
    # Bulk-data download
    # ------------------------------------------------------------------

    def download_bulk_metadata(self, force: bool = False) -> tuple[bool, str]:
        """Download Scryfall bulk data JSON.

        Args:
            force: Force re-download even if cached

        Returns:
            (success, message)
        """
        # Import here to avoid circular dependency with card_images
        from utils.card_images import BULK_DATA_CACHE

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

    # ------------------------------------------------------------------
    # Image download – orchestration
    # ------------------------------------------------------------------

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
        # Import here to avoid circular dependency with card_images
        from utils.card_images import BULK_DATA_CACHE

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

    # ------------------------------------------------------------------
    # Image download – per-card helpers
    # ------------------------------------------------------------------

    def _download_single_image(
        self, card: dict[str, Any], size: str = "normal"
    ) -> tuple[bool, str]:
        """Download a single card image."""
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
        filename = _build_face_filename(uuid, face_index, ext)
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
