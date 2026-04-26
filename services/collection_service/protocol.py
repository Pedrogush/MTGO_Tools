"""Shared ``self`` contract that the :class:`CollectionService` mixins assume."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from repositories.card_repository import CardRepository


class CollectionServiceProto(Protocol):
    """Cross-mixin ``self`` surface for ``CollectionService``."""

    card_repo: CardRepository
    _collection: dict[str, int]
    _collection_path: Path | None
    _collection_loaded: bool

    def get_inventory(self) -> dict[str, int]: ...
    def set_inventory(self, inventory: dict[str, int]) -> None: ...
    def clear_inventory(self) -> None: ...
    def set_collection_path(self, path: Path | None) -> None: ...
    def find_latest_cached_file(self, directory: Path, pattern: str = ...) -> Path | None: ...
    def load_from_cached_file(self, directory: Path, pattern: str = ...) -> dict[str, Any]: ...
    def get_owned_count(self, card_name: str) -> int: ...
    def export_to_file(
        self,
        cards: list[dict[str, Any]],
        directory: Path,
        filename_prefix: str = ...,
    ) -> Path: ...
