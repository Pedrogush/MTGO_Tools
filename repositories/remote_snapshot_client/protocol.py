"""Shared ``self`` contract that the :class:`RemoteSnapshotClient` mixins assume."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class RemoteSnapshotClientProto(Protocol):
    """Cross-mixin ``self`` surface for ``RemoteSnapshotClient``."""

    base_url: str
    cache_dir: Path
    manifest_file: Path
    max_age: int
    request_timeout: int
    _etag_file: Path
    _etags: dict[str, str]

    def _http_get_json(self, url: str) -> dict[str, Any] | None: ...
    def _local_artifact_path(self, artifact_path: str) -> Path: ...
