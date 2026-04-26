"""Shared ``self`` contract that the :class:`BundleSnapshotClient` mixins assume."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class BundleSnapshotClientProto(Protocol):
    """Cross-mixin ``self`` surface for ``BundleSnapshotClient``."""

    base_url: str
    bundle_path: str
    archetype_list_cache_file: Path
    archetype_decks_cache_file: Path
    format_card_pool_db_file: Path
    radar_db_file: Path
    stamp_file: Path
    max_age: int
    request_timeout: int

    def _http_get_bytes(self, url: str) -> bytes | None: ...
    def _is_stamp_fresh(self) -> bool: ...
    def _write_stamp(self, generated_at: str, applied_at: float) -> None: ...
