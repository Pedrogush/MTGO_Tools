"""RemoteSnapshotClient composed from responsibility-specific mixins."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from services.remote_snapshot_client.artifact import ArtifactMixin
from services.remote_snapshot_client.http import HttpMixin, RemoteSnapshotError
from services.remote_snapshot_client.manifest import ManifestMixin
from utils.constants import (
    REMOTE_SNAPSHOT_BASE_URL,
    REMOTE_SNAPSHOT_CACHE_DIR,
    REMOTE_SNAPSHOT_MANIFEST_FILE,
    REMOTE_SNAPSHOT_MAX_AGE_SECONDS,
    REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
)


class RemoteSnapshotClient(
    HttpMixin,
    ManifestMixin,
    ArtifactMixin,
):
    """Downloads and caches remote metagame snapshot artifacts.

    Downloads are staged under ``REMOTE_SNAPSHOT_CACHE_DIR``.  Repeated calls
    within ``max_age`` seconds reuse the local copy without hitting the network.
    ETags in the manifest are persisted so unchanged artifacts are never
    re-downloaded unnecessarily.
    """

    def __init__(
        self,
        base_url: str = REMOTE_SNAPSHOT_BASE_URL,
        cache_dir: Path = REMOTE_SNAPSHOT_CACHE_DIR,
        manifest_file: Path = REMOTE_SNAPSHOT_MANIFEST_FILE,
        max_age: int = REMOTE_SNAPSHOT_MAX_AGE_SECONDS,
        request_timeout: int = REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.manifest_file = Path(manifest_file)
        self.max_age = max_age
        self.request_timeout = request_timeout

        self._etag_file = self.cache_dir / "etags.json"
        self._etags: dict[str, str] = {}

    def get_archetypes_for_format(self, mtg_format: str) -> list[dict[str, Any]] | None:
        """Return the archetype list for *mtg_format* from the remote snapshot.

        Returns ``None`` on any failure (network, missing format, schema mismatch)
        so callers can transparently fall back to the live scraper.
        """
        fmt = mtg_format.lower()
        manifest = self._get_manifest()
        if manifest is None:
            return None

        format_entry = manifest.get("formats", {}).get(fmt)
        if not format_entry:
            logger.debug(f"Remote snapshot has no entry for format '{fmt}'")
            return None

        artifact_path = format_entry.get("archetypes_url", "")
        if not artifact_path:
            logger.debug(f"Remote manifest missing archetypes_url for '{fmt}'")
            return None

        data = self._get_artifact(artifact_path)
        if data is None:
            return None

        archetypes = data.get("archetypes")
        if not isinstance(archetypes, list):
            logger.warning(f"Remote archetypes artifact for '{fmt}' has unexpected shape")
            return None

        logger.info(f"Loaded {len(archetypes)} archetypes for '{fmt}' from remote snapshot")
        return archetypes

    def get_metagame_stats_for_format(self, mtg_format: str) -> dict[str, Any] | None:
        """Return per-day deck-count stats for *mtg_format* from the remote snapshot.

        Shape matches what ``MetagameRepository`` consumes from
        ``get_archetype_stats``:

        .. code-block:: python

            {
                "<format>": {
                    "timestamp": <float>,
                    "<archetype name>": {"results": {"<YYYY-MM-DD>": <int>, ...}},
                }
            }
        """
        fmt = mtg_format.lower()
        manifest = self._get_manifest()
        if manifest is None:
            return None

        format_entry = manifest.get("formats", {}).get(fmt)
        if not format_entry:
            logger.debug(f"Remote snapshot has no stats entry for format '{fmt}'")
            return None

        artifact_path = format_entry.get("metagame_stats_url", "")
        if not artifact_path:
            logger.debug(f"Remote manifest missing metagame_stats_url for '{fmt}'")
            return None

        data = self._get_artifact(artifact_path)
        if data is None:
            return None

        raw_archetypes = data.get("archetypes")
        if not isinstance(raw_archetypes, dict):
            logger.warning(f"Remote metagame stats for '{fmt}' has unexpected shape")
            return None

        result: dict[str, Any] = {fmt: {"timestamp": time.time()}}
        for name, archetype_data in raw_archetypes.items():
            result[fmt][name] = {"results": archetype_data.get("results", {})}

        logger.info(f"Loaded metagame stats for '{fmt}' from remote snapshot")
        return result

    def is_available(self) -> bool:
        return self._get_manifest() is not None


__all__ = ["RemoteSnapshotClient", "RemoteSnapshotError"]
