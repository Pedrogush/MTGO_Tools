"""MetagameRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from repositories.metagame_repository.archetype_resolution import ArchetypeResolutionMixin
from repositories.metagame_repository.background import BackgroundRefreshMixin
from repositories.metagame_repository.cache import CacheMixin
from repositories.metagame_repository.deck_operations import DeckOperationsMixin
from utils.constants import (
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    METAGAME_CACHE_TTL_SECONDS,
)

if TYPE_CHECKING:
    from services.remote_snapshot_client import RemoteSnapshotClient


class MetagameRepository(
    CacheMixin,
    ArchetypeResolutionMixin,
    DeckOperationsMixin,
    BackgroundRefreshMixin,
):
    """Repository for metagame data access operations."""

    def __init__(
        self,
        cache_ttl: int = METAGAME_CACHE_TTL_SECONDS,
        *,
        archetype_list_cache_file: Path = ARCHETYPE_LIST_CACHE_FILE,
        archetype_decks_cache_file: Path = ARCHETYPE_DECKS_CACHE_FILE,
        remote_snapshot_client: RemoteSnapshotClient | None = None,
    ):
        self.cache_ttl = cache_ttl
        self.archetype_list_cache_file = Path(archetype_list_cache_file)
        self.archetype_decks_cache_file = Path(archetype_decks_cache_file)
        self._remote_client = remote_snapshot_client
