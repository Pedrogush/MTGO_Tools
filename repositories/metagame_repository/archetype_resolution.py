"""Archetype-list and metagame-stats resolution (cache → remote snapshot → live)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

import repositories.metagame_repository as _pkg

if TYPE_CHECKING:
    from repositories.metagame_repository.protocol import MetagameRepositoryProto
    from services.remote_snapshot_client import RemoteSnapshotClient

    _Base = MetagameRepositoryProto
else:
    _Base = object


class ArchetypeResolutionMixin(_Base):
    """``get_archetypes_for_format`` / ``get_stats_for_format`` and remote lookup."""

    def get_archetypes_for_format(
        self,
        mtg_format: str,
        force_refresh: bool = False,
        on_background_refresh: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolution order (unless force_refresh):
        1. Local cache (if still fresh)
        2. Stale local cache + background re-fetch via on_background_refresh
        3. Remote snapshot (if REMOTE_SNAPSHOTS_ENABLED)
        4. Live MTGGoldfish scrape
        5. Stale local cache (last-resort fallback)
        """
        if not force_refresh:
            cached = self._load_cached_archetypes(mtg_format)
            if cached is not None:
                logger.debug(f"[local-cache] archetypes for {mtg_format}")
                return cached

            stale = self._load_cached_archetypes(mtg_format, max_age=None)
            if stale is not None:
                logger.info(f"[stale-while-revalidate] archetypes for {mtg_format}")
                if on_background_refresh is not None:
                    self._trigger_background_refresh(mtg_format, on_background_refresh)
                return stale

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

        logger.info(f"[live-scrape] archetypes for {mtg_format}")
        try:
            # Dynamic attribute lookup so tests that monkeypatch
            # ``repositories.metagame_repository.get_archetypes`` take effect.
            archetypes = _pkg.get_archetypes(mtg_format)
            self._save_cached_archetypes(mtg_format, archetypes)
            return archetypes
        except Exception as exc:
            logger.error(f"Failed to fetch archetypes: {exc}")
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
        """
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

        from navigators.mtggoldfish import get_archetype_stats

        logger.info(f"[live-scrape] metagame stats for {mtg_format}")
        return get_archetype_stats(mtg_format)

    def _remote_client_or_default(self) -> RemoteSnapshotClient | None:
        """Return the remote snapshot client when remote snapshots are enabled."""
        if self._remote_client is not None:
            return self._remote_client
        # Dynamic attribute lookup so tests that monkeypatch
        # ``repositories.metagame_repository.REMOTE_SNAPSHOTS_ENABLED`` take effect.
        if not _pkg.REMOTE_SNAPSHOTS_ENABLED:
            return None
        from services.remote_snapshot_client import get_remote_snapshot_client

        return get_remote_snapshot_client()
