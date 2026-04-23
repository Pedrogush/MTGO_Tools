"""BundleSnapshotClient composed from responsibility-specific mixins."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from services.bundle_snapshot_client.archetype_cache import ArchetypeCacheMixin
from services.bundle_snapshot_client.http import BundleSnapshotError, DownloadMixin
from services.bundle_snapshot_client.parser import BundleParserMixin
from services.bundle_snapshot_client.snapshot_cache import SnapshotCacheMixin
from services.bundle_snapshot_client.stamp import StampMixin
from utils.constants import (
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    FORMAT_CARD_POOL_DB_FILE,
    RADAR_CACHE_DB_FILE,
    REMOTE_SNAPSHOT_BASE_URL,
    REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS,
    REMOTE_SNAPSHOT_BUNDLE_PATH,
    REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE,
    REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
)


class BundleSnapshotClient(
    StampMixin,
    DownloadMixin,
    BundleParserMixin,
    ArchetypeCacheMixin,
    SnapshotCacheMixin,
):
    """Downloads the remote client bundle and hydrates local metagame caches."""

    def __init__(
        self,
        base_url: str = REMOTE_SNAPSHOT_BASE_URL,
        bundle_path: str = REMOTE_SNAPSHOT_BUNDLE_PATH,
        archetype_list_cache_file: Path = ARCHETYPE_LIST_CACHE_FILE,
        archetype_decks_cache_file: Path = ARCHETYPE_DECKS_CACHE_FILE,
        format_card_pool_db_file: Path = FORMAT_CARD_POOL_DB_FILE,
        radar_db_file: Path = RADAR_CACHE_DB_FILE,
        stamp_file: Path = REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE,
        max_age: int = REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS,
        request_timeout: int = REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bundle_path = bundle_path
        self.archetype_list_cache_file = Path(archetype_list_cache_file)
        self.archetype_decks_cache_file = Path(archetype_decks_cache_file)
        self.format_card_pool_db_file = Path(format_card_pool_db_file)
        self.radar_db_file = Path(radar_db_file)
        self.stamp_file = Path(stamp_file)
        self.max_age = max_age
        self.request_timeout = request_timeout

    def apply(self) -> tuple[bool, dict[str, list[dict[str, Any]]] | None]:
        """Download the bundle (if stale) and hydrate local caches.

        Returns ``(updated, archetypes_by_format)``:

        - ``updated`` — ``True`` when caches were written; ``False`` when the
          stamp was fresh (no network activity).
        - ``archetypes_by_format`` — lowercase format → archetype list parsed
          from the bundle, or ``None`` when the bundle was not applied.

        Raises :class:`BundleSnapshotError` only when the download itself fails
        unrecoverably; individual parse errors are logged and skipped.
        """
        if self._is_stamp_fresh():
            logger.debug("Bundle stamp is fresh — skipping download")
            return False, None

        logger.info("Downloading remote client bundle…")
        bundle_bytes = self._download_bundle()
        (
            manifest,
            archetype_entries,
            deck_entries,
            deck_texts,
            card_pool_entries,
            radar_entries,
            mtgo_decklist_entries,
        ) = self._parse_bundle(bundle_bytes)

        generated_at = manifest.get("generated_at", "")
        now = time.time()

        self._hydrate_archetype_lists(archetype_entries, now)
        self._hydrate_archetype_decks(deck_entries, now)
        mtgo_merged = self._hydrate_mtgo_decklists(mtgo_decklist_entries, archetype_entries, now)
        card_pools = self._hydrate_format_card_pools(card_pool_entries)
        radars = self._hydrate_radars(radar_entries)
        inserted = self._hydrate_deck_texts(deck_texts)
        self._write_stamp(generated_at, now)

        logger.info(
            f"Bundle applied: {len(archetype_entries)} archetype lists, "
            f"{len(deck_entries)} deck lists, "
            f"{mtgo_merged} MTGO decks merged, "
            f"{card_pools}/{len(card_pool_entries)} card pools, "
            f"{radars}/{len(radar_entries)} radars, "
            f"{inserted}/{len(deck_texts)} deck texts inserted (generated_at={generated_at})"
        )

        archetypes_by_format: dict[str, list[dict[str, Any]]] = {}
        for entry in archetype_entries:
            fmt = entry.get("format", "").lower()
            archetypes = entry.get("archetypes")
            if fmt and isinstance(archetypes, list):
                archetypes_by_format[fmt] = archetypes

        return True, archetypes_by_format or None


__all__ = ["BundleSnapshotClient", "BundleSnapshotError"]
