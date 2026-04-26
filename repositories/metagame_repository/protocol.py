"""Shared ``self`` contract that the :class:`MetagameRepository` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from services.remote_snapshot_client import RemoteSnapshotClient


class MetagameRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``MetagameRepository``."""

    cache_ttl: int
    archetype_list_cache_file: Path
    archetype_decks_cache_file: Path
    _remote_client: RemoteSnapshotClient | None

    def _load_cached_archetypes(
        self, mtg_format: str, max_age: int | None | object = ...
    ) -> list[dict[str, Any]] | None: ...

    def _save_cached_archetypes(self, mtg_format: str, items: list[dict[str, Any]]) -> None: ...

    def _load_cached_decks(
        self, archetype_url: str, max_age: int | None | object = ...
    ) -> list[dict[str, Any]] | None: ...

    def _save_cached_decks(self, archetype_url: str, items: list[dict[str, Any]]) -> None: ...

    def _filter_decks_by_source(
        self, decks: list[dict[str, Any]], source_filter: str | None
    ) -> list[dict[str, Any]]: ...

    def _sort_decks_by_date(self, decks: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def _remote_client_or_default(self) -> RemoteSnapshotClient | None: ...

    def _trigger_background_refresh(
        self,
        mtg_format: str,
        callback: Callable[[list[dict[str, Any]]], None],
    ) -> None: ...
