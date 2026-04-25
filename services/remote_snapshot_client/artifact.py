"""Per-format artifact download and disk staging."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from services.remote_snapshot_client.protocol import RemoteSnapshotClientProto

    _Base = RemoteSnapshotClientProto
else:
    _Base = object

_SUPPORTED_SCHEMA_VERSION = "1"


class ArtifactMixin(_Base):
    """Download/cache the per-format archetype and metagame-stats artifacts."""

    def _get_artifact(self, artifact_path: str) -> dict[str, Any] | None:
        local_path = self._local_artifact_path(artifact_path)

        if local_path.exists():
            try:
                age = time.time() - local_path.stat().st_mtime
                if age < self.max_age:
                    try:
                        return json.loads(local_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        logger.debug(f"Cached artifact invalid, re-fetching: {exc}")
            except OSError:
                pass

        return self._download_artifact(artifact_path, local_path)

    def _download_artifact(self, artifact_path: str, local_path: Path) -> dict[str, Any] | None:
        url = f"{self.base_url}/{artifact_path}"
        data = self._http_get_json(url)
        if data is None:
            return None

        if data.get("schema_version") != _SUPPORTED_SCHEMA_VERSION:
            logger.warning(f"Artifact '{artifact_path}' schema_version mismatch; skipping")
            return None

        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            local_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Could not cache artifact '{artifact_path}': {exc}")

        return data

    def _local_artifact_path(self, artifact_path: str) -> Path:
        # artifact_path looks like "data/latest/modern/archetypes.json"
        return self.cache_dir / artifact_path.lstrip("/")
