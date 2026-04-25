"""Remote manifest download and caching."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from services.remote_snapshot_client.protocol import RemoteSnapshotClientProto

    _Base = RemoteSnapshotClientProto
else:
    _Base = object

_MANIFEST_PATH = "data/latest/manifest.json"
_SUPPORTED_SCHEMA_VERSION = "1"


class ManifestMixin(_Base):
    """Fetch and cache the top-level remote snapshot manifest."""

    def _get_manifest(self) -> dict[str, Any] | None:
        cached = self._load_cached_manifest()
        if cached is not None:
            return cached

        return self._fetch_and_cache_manifest()

    def _load_cached_manifest(self) -> dict[str, Any] | None:
        if not self.manifest_file.exists():
            return None
        try:
            raw = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(f"Could not read cached manifest: {exc}")
            return None

        cached_at = raw.get("_cached_at", 0)
        if time.time() - cached_at > self.max_age:
            logger.debug("Cached remote manifest is stale")
            return None

        return raw.get("manifest")

    def _fetch_and_cache_manifest(self) -> dict[str, Any] | None:
        url = f"{self.base_url}/{_MANIFEST_PATH}"
        data = self._http_get_json(url)
        if data is None:
            return None

        if data.get("schema_version") != _SUPPORTED_SCHEMA_VERSION:
            logger.warning(
                f"Remote manifest schema_version '{data.get('schema_version')}' "
                f"!= '{_SUPPORTED_SCHEMA_VERSION}'; skipping remote snapshots"
            )
            return None

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        envelope = {"_cached_at": time.time(), "manifest": data}
        try:
            self.manifest_file.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Could not cache remote manifest: {exc}")

        return data
