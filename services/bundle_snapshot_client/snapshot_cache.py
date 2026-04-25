"""Format card pool and radar snapshot hydration for the bundle snapshot client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from repositories.format_card_pool_repository import FormatCardPoolRepository
from repositories.radar_repository import RadarRepository

if TYPE_CHECKING:
    from services.bundle_snapshot_client.protocol import BundleSnapshotClientProto

    _Base = BundleSnapshotClientProto
else:
    _Base = object


class SnapshotCacheMixin(_Base):
    """Hydrate SQLite-backed format card pool and precomputed radar stores."""

    def _hydrate_format_card_pools(self, card_pool_entries: list[dict[str, Any]]) -> int:
        if not card_pool_entries:
            return 0
        try:
            repo = FormatCardPoolRepository(self.format_card_pool_db_file)
            replaced = repo.bulk_replace(card_pool_entries)
            logger.debug(f"Hydrated {replaced}/{len(card_pool_entries)} format card pool snapshots")
            return replaced
        except Exception as exc:
            logger.warning(f"Failed to hydrate format card pools: {exc}")
            return 0

    def _hydrate_radars(self, radar_entries: list[dict[str, Any]]) -> int:
        if not radar_entries:
            return 0
        try:
            repo = RadarRepository(self.radar_db_file)
            replaced = repo.bulk_replace(radar_entries)
            logger.debug(f"Hydrated {replaced}/{len(radar_entries)} precomputed radars")
            return replaced
        except Exception as exc:
            logger.warning(f"Failed to hydrate radars: {exc}")
            return 0
