"""
Metagame Repository - Data access layer for metagame information.

This module handles all metagame-related data fetching including:
- MTGGoldfish archetype scraping
- Deck list downloading
- Caching of metagame data
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from loguru import logger

from navigators.mtggoldfish import (
    fetch_deck_text,
    get_archetype_decks,
    get_archetypes,
)
from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import (
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    METAGAME_CACHE_TTL_SECONDS,
    MTGO_DECKLISTS_ENABLED,
    REMOTE_SNAPSHOTS_ENABLED,
)

if TYPE_CHECKING:
    from services.remote_snapshot_client import RemoteSnapshotClient

_USE_DEFAULT_MAX_AGE: Final = object()


def _parse_deck_date(date_str: str) -> tuple[int, int, int]:
    """
    Parse deck date strings in supported formats.

    Supported formats:
    - YYYY-MM-DD (MTGGoldfish)
    - MM/DD/YYYY (MTGO exports)
    """
    if not date_str:
        return (0, 0, 0)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            return (parsed.year, parsed.month, parsed.day)
        except (TypeError, ValueError):
            continue

    return (0, 0, 0)


class MetagameRepository:
    """Repository for metagame data access operations."""

    def __init__(
        self,
        cache_ttl: int = METAGAME_CACHE_TTL_SECONDS,
        *,
        archetype_list_cache_file: Path = ARCHETYPE_LIST_CACHE_FILE,
        archetype_decks_cache_file: Path = ARCHETYPE_DECKS_CACHE_FILE,
        remote_snapshot_client: "RemoteSnapshotClient | None" = None,
    ):
        """
        Initialize the metagame repository.

        Args:
            cache_ttl: Time-to-live for cached data in seconds (default: 1 hour)
            archetype_list_cache_file: Path to archetype list cache (overridable for testing)
            archetype_decks_cache_file: Path to archetype deck cache (overridable for testing)
            remote_snapshot_client: Optional remote snapshot client; injected for testing.
                When ``None`` the default singleton is used if ``REMOTE_SNAPSHOTS_ENABLED``
                is set, otherwise remote snapshots are skipped entirely.
        """
        self.cache_ttl = cache_ttl
        self.archetype_list_cache_file = Path(archetype_list_cache_file)
        self.archetype_decks_cache_file = Path(archetype_decks_cache_file)
        self._remote_client = remote_snapshot_client

    # ============= Archetype Operations =============

    def get_archetypes_for_format(
        self, mtg_format: str, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get list of archetypes for a specific format.

        Resolution order (unless force_refresh):
        1. Local cache (if still fresh)
        2. Remote snapshot (if REMOTE_SNAPSHOTS_ENABLED)
        3. Live MTGGoldfish scrape
        4. Stale local cache (last-resort fallback on live-scrape failure)

        Args:
            mtg_format: MTG format (e.g., "Modern", "Standard")
            force_refresh: If True, bypass local cache and fetch fresh data

        Returns:
            List of archetype dictionaries with keys: name, url, share, etc.
        """
        # 1. Local cache
        if not force_refresh:
            cached = self._load_cached_archetypes(mtg_format)
            if cached is not None:
                logger.debug(f"[local-cache] archetypes for {mtg_format}")
                return cached

        # 2. Remote snapshot
        remote = self._remote_client_or_default()
        if remote is not None:
            try:
                remote_archetypes = remote.get_archetypes_for_format(mtg_format)
                if remote_archetypes is not None:
                    logger.info(f"[remote-snapshot] archetypes for {mtg_format}")
                    self._save_cached_archetypes(mtg_format, remote_archetypes)
                    return remote_archetypes
            except Exception as exc:
                logger.warning(f"Remote snapshot archetypes failed for {mtg_format}: {exc}")

        # 3. Live scrape
        logger.info(f"[live-scrape] archetypes for {mtg_format}")
        try:
            archetypes = get_archetypes(mtg_format)
            self._save_cached_archetypes(mtg_format, archetypes)
            return archetypes
        except Exception as exc:
            logger.error(f"Failed to fetch archetypes: {exc}")
            # 4. Stale cache as last resort
            cached = self._load_cached_archetypes(mtg_format, max_age=None)
            if cached:
                logger.warning(f"[stale-cache] archetypes for {mtg_format}")
                return cached
            raise

    def get_stats_for_format(self, mtg_format: str, force_refresh: bool = False) -> dict[str, Any]:
        """Return per-day deck-count stats for *mtg_format*.

        Resolution order:
        1. Remote snapshot  (if REMOTE_SNAPSHOTS_ENABLED and not force_refresh)
        2. Live ``get_archetype_stats`` scrape (also populates the archetype
           stats cache used by the navigator module)

        The returned dict matches the shape produced by
        ``navigators.mtggoldfish.get_archetype_stats``:

        .. code-block:: python

            {
                "<format>": {
                    "timestamp": <float>,
                    "<archetype name>": {
                        "results": {"<YYYY-MM-DD>": <int>, ...}
                    },
                }
            }
        """
        # 1. Remote snapshot
        if not force_refresh:
            remote = self._remote_client_or_default()
            if remote is not None:
                try:
                    remote_stats = remote.get_metagame_stats_for_format(mtg_format)
                    if remote_stats is not None:
                        logger.info(f"[remote-snapshot] metagame stats for {mtg_format}")
                        return remote_stats
                except Exception as exc:
                    logger.warning(f"Remote snapshot stats failed for {mtg_format}: {exc}")

        # 2. Live scrape via existing navigator function
        from navigators.mtggoldfish import get_archetype_stats

        logger.info(f"[live-scrape] metagame stats for {mtg_format}")
        return get_archetype_stats(mtg_format)

    def get_decks_for_archetype(
        self,
        archetype: dict[str, Any],
        force_refresh: bool = False,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get deck lists for a specific archetype.

        Args:
            archetype: Archetype dictionary with 'href' or 'url' key
            force_refresh: If True, bypass cache and fetch fresh data
            source_filter: Optional source filter ('mtggoldfish', 'mtgo', or 'both')

        Returns:
            List of deck dictionaries
        """
        # Support both 'href' (from get_archetypes) and 'url' for compatibility
        archetype_href = archetype.get("href") or archetype.get("url", "")
        archetype_name = archetype.get("name", "Unknown")

        # Try cache first unless forced refresh
        if not force_refresh:
            cached = self._load_cached_decks(archetype_href)
            if cached is not None:
                logger.debug(f"Using cached decks for {archetype_name}")
                mtggoldfish_decks = self._filter_decks_by_source(cached, source_filter)
                mtgo_decks = self._get_mtgo_decks_from_db(archetype_name, source_filter)
                return self._merge_and_sort_decks(mtggoldfish_decks, mtgo_decks)

        # Fetch fresh data
        logger.info(f"Fetching fresh decks for {archetype_name}")
        try:
            # get_archetype_decks expects just the href string, not the dict
            decks = get_archetype_decks(archetype_href)
            # Preserve any MTGO-sourced entries hydrated from the remote bundle so
            # a live MTGGoldfish refresh does not evict them from the cache.
            existing = self._load_cached_decks(archetype_href, max_age=None) or []
            bundle_mtgo = [d for d in existing if d.get("source") == "mtgo"]
            merged = decks + bundle_mtgo
            self._save_cached_decks(archetype_href, merged)
            filtered = self._filter_decks_by_source(merged, source_filter)
            mtgo_decks = self._get_mtgo_decks_from_db(archetype_name, source_filter)
            return self._merge_and_sort_decks(filtered, mtgo_decks)
        except Exception as exc:
            logger.error(f"Failed to fetch decks for {archetype_name}: {exc}")
            # Try to return stale cache if available
            cached = self._load_cached_decks(archetype_href, max_age=None)
            if cached:
                logger.warning(f"Returning stale cached decks for {archetype_name}")
                mtggoldfish_decks = self._filter_decks_by_source(cached, source_filter)
                mtgo_decks = self._get_mtgo_decks_from_db(archetype_name, source_filter)
                return self._merge_and_sort_decks(mtggoldfish_decks, mtgo_decks)
            raise

    def download_deck_content(self, deck: dict[str, Any], source_filter: str | None = None) -> str:
        """
        Download the actual deck list content.

        Args:
            deck: Deck dictionary with 'number' key (deck ID)
            source_filter: Optional source filter ('mtggoldfish', 'mtgo', or 'both')

        Returns:
            Deck list as text string

        Raises:
            Exception: If download fails
        """
        deck_name = deck.get("name", "Unknown")
        deck_number = deck.get("number", "")

        if not deck_number:
            raise ValueError(f"Deck {deck_name} has no 'number' field")

        logger.info(f"Downloading deck: {deck_name}")
        try:
            # fetch_deck_text handles caching and returns the text directly
            # This avoids unnecessary write-to-file and read-from-file operations
            deck_content = fetch_deck_text(deck_number, source_filter=source_filter)
            return deck_content
        except Exception as exc:
            logger.error(f"Failed to download deck {deck_name}: {exc}")
            raise

    # ============= Remote snapshot helpers =============

    def _remote_client_or_default(self) -> "RemoteSnapshotClient | None":
        """Return the remote snapshot client when remote snapshots are enabled.

        Uses the injected client (for testing) when present; otherwise falls
        back to the module-level singleton, gated on ``REMOTE_SNAPSHOTS_ENABLED``.
        """
        if self._remote_client is not None:
            return self._remote_client
        if not REMOTE_SNAPSHOTS_ENABLED:
            return None
        from services.remote_snapshot_client import get_remote_snapshot_client

        return get_remote_snapshot_client()

    # ============= Cache Management =============

    def _load_cached_archetypes(
        self, mtg_format: str, max_age: int | None | object = _USE_DEFAULT_MAX_AGE
    ) -> list[dict[str, Any]] | None:
        """
        Load cached archetype list.

        Args:
            mtg_format: MTG format to load
            max_age: Maximum age in seconds (None = ignore age, -1 = use default TTL)

        Returns:
            List of archetypes or None if cache miss
        """
        if max_age == -1:
            max_age = _USE_DEFAULT_MAX_AGE
        effective_max_age = self.cache_ttl if max_age is _USE_DEFAULT_MAX_AGE else max_age

        if not self.archetype_list_cache_file.exists():
            return None

        try:
            with locked_path(self.archetype_list_cache_file):
                with self.archetype_list_cache_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Cached archetype list invalid: {exc}")
            return None

        entry = data.get(mtg_format)
        if not entry:
            return None

        # Check age if max_age is specified
        if effective_max_age is not None:
            timestamp = entry.get("timestamp", 0)
            if time.time() - timestamp > effective_max_age:
                logger.debug(f"Archetype cache for {mtg_format} expired")
                return None

        return entry.get("items")

    def _save_cached_archetypes(self, mtg_format: str, items: list[dict[str, Any]]) -> None:
        """
        Save archetypes to cache.

        Args:
            mtg_format: MTG format
            items: List of archetype dictionaries
        """
        with locked_path(self.archetype_list_cache_file):
            data: dict[str, Any] = {}
            if self.archetype_list_cache_file.exists():
                try:
                    with self.archetype_list_cache_file.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except json.JSONDecodeError as exc:
                    logger.warning(f"Archetype cache invalid, rebuilding: {exc}")

            data[mtg_format] = {"timestamp": time.time(), "items": items}

            try:
                atomic_write_json(self.archetype_list_cache_file, data, indent=2)
                logger.debug(f"Cached {len(items)} archetypes for {mtg_format}")
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to cache archetypes: {exc}")

    def _load_cached_decks(
        self, archetype_url: str, max_age: int | None | object = _USE_DEFAULT_MAX_AGE
    ) -> list[dict[str, Any]] | None:
        """
        Load cached deck list for an archetype.

        Args:
            archetype_url: URL identifying the archetype
            max_age: Maximum age in seconds (None = ignore age, -1 = use default TTL)

        Returns:
            List of decks or None if cache miss
        """
        if max_age == -1:
            max_age = _USE_DEFAULT_MAX_AGE
        effective_max_age = self.cache_ttl if max_age is _USE_DEFAULT_MAX_AGE else max_age

        if not self.archetype_decks_cache_file.exists():
            return None

        try:
            with locked_path(self.archetype_decks_cache_file):
                with self.archetype_decks_cache_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Cached deck list invalid: {exc}")
            return None

        entry = data.get(archetype_url)
        if not entry:
            return None

        # Check age if max_age is specified
        if effective_max_age is not None:
            timestamp = entry.get("timestamp", 0)
            if time.time() - timestamp > effective_max_age:
                logger.debug("Deck cache for archetype expired")
                return None

        return entry.get("items")

    def _save_cached_decks(self, archetype_url: str, items: list[dict[str, Any]]) -> None:
        """
        Save decks to cache.

        Args:
            archetype_url: URL identifying the archetype
            items: List of deck dictionaries
        """
        with locked_path(self.archetype_decks_cache_file):
            data: dict[str, Any] = {}
            if self.archetype_decks_cache_file.exists():
                try:
                    with self.archetype_decks_cache_file.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except json.JSONDecodeError as exc:
                    logger.warning(f"Deck cache invalid, rebuilding: {exc}")

            data[archetype_url] = {"timestamp": time.time(), "items": items}

            try:
                atomic_write_json(self.archetype_decks_cache_file, data, indent=2)
                logger.debug(f"Cached {len(items)} decks for archetype")
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to cache decks: {exc}")

    def _filter_decks_by_source(
        self, decks: list[dict[str, Any]], source_filter: str | None
    ) -> list[dict[str, Any]]:
        """
        Filter decks by source.

        Args:
            decks: List of deck dictionaries
            source_filter: Optional source filter ('mtggoldfish', 'mtgo', or 'both')

        Returns:
            Filtered list of decks
        """
        if not source_filter or source_filter == "both":
            return decks

        return [deck for deck in decks if deck.get("source") == source_filter]

    def _get_mtgo_decks_from_db(
        self, archetype_name: str, source_filter: str | None
    ) -> list[dict[str, Any]]:
        """
        Retrieve MTGO decks from JSON cache for a specific archetype.

        Args:
            archetype_name: Name of the archetype
            source_filter: Optional source filter ('mtggoldfish', 'mtgo', or 'both')

        Returns:
            List of MTGO deck dictionaries formatted for UI display
        """
        if not MTGO_DECKLISTS_ENABLED:
            logger.info("MTGO decklists disabled; skipping MTGO deck lookup.")
            return []

        if source_filter == "mtggoldfish":
            return []

        try:
            from services.mtgo_background_service import load_mtgo_deck_metadata

            mtgo_decks = []
            for fmt in ("modern", "standard", "pioneer", "legacy"):
                decks = load_mtgo_deck_metadata(archetype_name, fmt)
                mtgo_decks.extend(decks)

            logger.debug(f"Retrieved {len(mtgo_decks)} MTGO decks from cache for {archetype_name}")
            return mtgo_decks

        except Exception as exc:
            logger.warning(f"Failed to retrieve MTGO decks from cache: {exc}")
            return []

    def _merge_and_sort_decks(
        self, mtggoldfish_decks: list[dict[str, Any]], mtgo_decks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Merge MTGGoldfish and MTGO decks and sort by date (newest first).

        Args:
            mtggoldfish_decks: Decks from MTGGoldfish
            mtgo_decks: Decks from MTGO (MongoDB)

        Returns:
            Merged and sorted list of decks
        """
        all_decks = mtggoldfish_decks + mtgo_decks

        all_decks.sort(key=lambda d: _parse_deck_date(d.get("date", "")), reverse=True)
        return all_decks

    def clear_cache(self) -> None:
        """Clear all metagame caches."""
        for cache_file in [self.archetype_list_cache_file, self.archetype_decks_cache_file]:
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    logger.info(f"Cleared cache: {cache_file}")
                except OSError as exc:
                    logger.warning(f"Failed to clear cache {cache_file}: {exc}")


# Global instance for backward compatibility
_default_repository = None


def get_metagame_repository() -> MetagameRepository:
    """Get the default metagame repository instance."""
    global _default_repository
    if _default_repository is None:
        _default_repository = MetagameRepository()
    return _default_repository


def reset_metagame_repository() -> None:
    """
    Reset the global metagame repository instance.

    This is primarily useful for testing to ensure test isolation
    and prevent state leakage between tests.
    """
    global _default_repository
    _default_repository = None
