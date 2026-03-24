"""Remote snapshot client for consuming published metagame artifacts.

This module downloads and stages snapshots from the MTGO_Scrapes_Repository so the
app can resolve archetype lists, deck metadata, and metagame stats without hitting
MTGGoldfish directly in the common path.

Expected remote artifact layout (relative to REMOTE_SNAPSHOT_BASE_URL):
    data/latest/manifest.json                     - top-level manifest
    data/latest/{format}/archetypes.json          - archetype list for a format
    data/latest/{format}/metagame_stats.json      - per-day deck counts per archetype
    data/latest/{format}/decks/{slug}.json        - deck list for one archetype

Manifest schema (schema_version "1"):
    {
        "schema_version": "1",
        "generated_at": "<ISO-8601 timestamp>",
        "formats": {
            "<format>": {
                "archetypes_url": "data/latest/<format>/archetypes.json",
                "metagame_stats_url": "data/latest/<format>/metagame_stats.json",
                "updated_at": "<ISO-8601 timestamp>",
                "etag": "<optional etag string>"
            }
        }
    }

Archetypes artifact schema:
    {
        "schema_version": "1",
        "format": "<format>",
        "generated_at": "<ISO-8601 timestamp>",
        "archetypes": [ { "name": "...", "href": "...", ... } ]
    }

Metagame stats artifact schema:
    {
        "schema_version": "1",
        "format": "<format>",
        "generated_at": "<ISO-8601 timestamp>",
        "archetypes": {
            "<archetype name>": {
                "results": { "<YYYY-MM-DD>": <count>, ... }
            }
        }
    }
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from utils.constants import (
    REMOTE_SNAPSHOT_BASE_URL,
    REMOTE_SNAPSHOT_CACHE_DIR,
    REMOTE_SNAPSHOT_MANIFEST_FILE,
    REMOTE_SNAPSHOT_MAX_AGE_SECONDS,
    REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
)

_MANIFEST_PATH = "data/latest/manifest.json"
_SUPPORTED_SCHEMA_VERSION = "1"


class RemoteSnapshotError(Exception):
    """Raised when a remote snapshot operation fails unrecoverably."""


class RemoteSnapshotClient:
    """Downloads and caches remote metagame snapshot artifacts.

    Downloads are staged under ``REMOTE_SNAPSHOT_CACHE_DIR``.  Repeated calls
    within ``max_age`` seconds reuse the local copy without hitting the network.
    ETags in the manifest are persisted so unchanged artifacts are never
    re-downloaded unnecessarily.

    Parameters
    ----------
    base_url:
        Root URL of the scrape repository (no trailing slash).
    cache_dir:
        Local directory for staging downloaded artifacts.
    manifest_file:
        Local path for the cached manifest.
    max_age:
        Seconds before a cached manifest is considered stale.
    request_timeout:
        HTTP request timeout in seconds.
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

        # Local ETag store: maps remote artifact path -> last-seen ETag
        self._etag_file = self.cache_dir / "etags.json"
        self._etags: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def get_archetypes_for_format(self, mtg_format: str) -> list[dict[str, Any]] | None:
        """Return the archetype list for *mtg_format* from the remote snapshot.

        Returns ``None`` when the feature is unavailable (network failure,
        format not in manifest, schema mismatch).  Callers should treat
        ``None`` as a cache miss and fall back to the live scraper.

        Parameters
        ----------
        mtg_format:
            Format name, case-insensitive (e.g. ``"modern"``, ``"Standard"``).
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

        Returns a dict structured the same way ``get_archetype_stats`` does so
        ``MetagameRepository`` can substitute it directly:

        .. code-block:: python

            {
                "<format>": {
                    "timestamp": <float>,
                    "<archetype name>": {
                        "results": {"<YYYY-MM-DD>": <int>, ...}
                    },
                }
            }

        Returns ``None`` on failure.
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

        # Normalise to the shape MetagameRepository / metagame_analysis expects.
        result: dict[str, Any] = {fmt: {"timestamp": time.time()}}
        for name, archetype_data in raw_archetypes.items():
            result[fmt][name] = {"results": archetype_data.get("results", {})}

        logger.info(f"Loaded metagame stats for '{fmt}' from remote snapshot")
        return result

    def is_available(self) -> bool:
        """Return True if the remote manifest can be fetched successfully."""
        return self._get_manifest() is not None

    # ------------------------------------------------------------------ #
    # Manifest management                                                   #
    # ------------------------------------------------------------------ #

    def _get_manifest(self) -> dict[str, Any] | None:
        """Return the manifest, using a local cache when still fresh."""
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

    # ------------------------------------------------------------------ #
    # Artifact management                                                   #
    # ------------------------------------------------------------------ #

    def _get_artifact(self, artifact_path: str) -> dict[str, Any] | None:
        """Return a cached artifact, downloading it if stale or absent."""
        local_path = self._local_artifact_path(artifact_path)

        # Check local copy freshness
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
        """Convert a remote relative path to a local staging path."""
        # artifact_path looks like "data/latest/modern/archetypes.json"
        return self.cache_dir / artifact_path.lstrip("/")

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                          #
    # ------------------------------------------------------------------ #

    def _http_get_json(self, url: str) -> dict[str, Any] | None:
        """Fetch *url* and decode the response body as JSON.

        Returns ``None`` (and logs the error) instead of raising on any
        network or decode failure, so callers can transparently fall back.
        """
        try:
            import curl_cffi.requests as requests  # type: ignore[import-untyped]

            response = requests.get(url, impersonate="chrome", timeout=self.request_timeout)
            response.raise_for_status()
            return response.json()
        except ImportError:
            pass
        except Exception as exc:
            logger.debug(f"Remote snapshot fetch failed for {url!r}: {exc}")
            return None

        # Fallback to stdlib urllib when curl_cffi is unavailable (e.g. Linux CI)
        try:
            from urllib.request import urlopen

            with urlopen(url, timeout=self.request_timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug(f"Remote snapshot fetch (urllib) failed for {url!r}: {exc}")
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_client: RemoteSnapshotClient | None = None


def get_remote_snapshot_client() -> RemoteSnapshotClient:
    """Return the shared ``RemoteSnapshotClient`` instance."""
    global _default_client
    if _default_client is None:
        _default_client = RemoteSnapshotClient()
    return _default_client


def reset_remote_snapshot_client() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_client
    _default_client = None
