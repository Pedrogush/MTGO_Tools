"""Bundle snapshot client — downloads and applies the remote client bundle at startup.

The remote repository publishes a single compressed archive (``client-bundle.tar.gz``)
that contains archetype lists and deck lists for all supported formats.  This module
downloads that archive in-memory, extracts it, and writes the data into the local
caches used by ``MetagameRepository``, so that archetype fetching, deck loading,
radar analysis, and metagame analysis all start with warm caches.

Bundle layout inside the archive (paths relative to the tar root):
    latest/latest.json                     — manifest: generated_at, lists all entries
    latest/archetypes/{format}.json        — archetype list for one format
    latest/decks/{format}/{slug}.json      — deck list for one archetype slug

The client writes into:
    ARCHETYPE_LIST_CACHE_FILE   — ``{format: {timestamp, items: [...]}}``
    ARCHETYPE_DECKS_CACHE_FILE  — ``{archetype_href: {timestamp, items: [...]}}``

Staleness is tracked via a stamp file (``REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE``).
If the stamp is fresher than ``REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS``, the
bundle download is skipped entirely.
"""

from __future__ import annotations

import io
import json
import tarfile
import time
from pathlib import Path
from typing import Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import (
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    REMOTE_SNAPSHOT_BASE_URL,
    REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS,
    REMOTE_SNAPSHOT_BUNDLE_PATH,
    REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE,
    REMOTE_SNAPSHOT_CACHE_DIR,
    REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
)

_SUPPORTED_SCHEMA_VERSION = "1"


class BundleSnapshotError(Exception):
    """Raised when the bundle cannot be downloaded or applied."""


class BundleSnapshotClient:
    """Downloads the remote client bundle and hydrates local metagame caches.

    Parameters
    ----------
    base_url:
        Root URL of the scrape repository (no trailing slash).
    bundle_path:
        Relative path of the bundle within the repository.
    archetype_list_cache_file:
        Destination for the archetype-list cache (overridable for tests).
    archetype_decks_cache_file:
        Destination for the archetype-decks cache (overridable for tests).
    stamp_file:
        Path to the JSON file that records the last successful apply timestamp.
    max_age:
        Seconds before the stamp is considered stale and a new download is attempted.
    request_timeout:
        HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = REMOTE_SNAPSHOT_BASE_URL,
        bundle_path: str = REMOTE_SNAPSHOT_BUNDLE_PATH,
        archetype_list_cache_file: Path = ARCHETYPE_LIST_CACHE_FILE,
        archetype_decks_cache_file: Path = ARCHETYPE_DECKS_CACHE_FILE,
        stamp_file: Path = REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE,
        max_age: int = REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS,
        request_timeout: int = REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bundle_path = bundle_path
        self.archetype_list_cache_file = Path(archetype_list_cache_file)
        self.archetype_decks_cache_file = Path(archetype_decks_cache_file)
        self.stamp_file = Path(stamp_file)
        self.max_age = max_age
        self.request_timeout = request_timeout

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def apply(self) -> bool:
        """Download the bundle (if stale) and hydrate local caches.

        Returns ``True`` if the caches were updated, ``False`` if the local
        stamp was still fresh (no network activity).

        Raises ``BundleSnapshotError`` only when the download itself fails
        unrecoverably; individual parse errors are logged and skipped.
        """
        if self._is_stamp_fresh():
            logger.debug("Bundle stamp is fresh — skipping download")
            return False

        logger.info("Downloading remote client bundle…")
        bundle_bytes = self._download_bundle()
        manifest, archetype_entries, deck_entries = self._parse_bundle(bundle_bytes)

        generated_at = manifest.get("generated_at", "")
        now = time.time()

        self._hydrate_archetype_lists(archetype_entries, now)
        self._hydrate_archetype_decks(deck_entries, now)
        self._write_stamp(generated_at, now)

        logger.info(
            f"Bundle applied: {len(archetype_entries)} archetype lists, "
            f"{len(deck_entries)} deck lists (generated_at={generated_at})"
        )
        return True

    # ------------------------------------------------------------------ #
    # Stamp management                                                      #
    # ------------------------------------------------------------------ #

    def _is_stamp_fresh(self) -> bool:
        if not self.stamp_file.exists():
            return False
        try:
            data = json.loads(self.stamp_file.read_text(encoding="utf-8"))
            applied_at = float(data.get("applied_at", 0))
            return (time.time() - applied_at) < self.max_age
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug(f"Could not read bundle stamp: {exc}")
            return False

    def _write_stamp(self, generated_at: str, applied_at: float) -> None:
        try:
            REMOTE_SNAPSHOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.stamp_file.write_text(
                json.dumps({"generated_at": generated_at, "applied_at": applied_at}, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"Could not write bundle stamp: {exc}")

    # ------------------------------------------------------------------ #
    # Download                                                              #
    # ------------------------------------------------------------------ #

    def _download_bundle(self) -> bytes:
        url = f"{self.base_url}/{self.bundle_path}"
        data = self._http_get_bytes(url)
        if data is None:
            raise BundleSnapshotError(f"Failed to download bundle from {url!r}")
        return data

    # ------------------------------------------------------------------ #
    # Parse                                                                 #
    # ------------------------------------------------------------------ #

    def _parse_bundle(
        self, bundle_bytes: bytes
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Extract the bundle and return (manifest, archetype_entries, deck_entries).

        Each archetype entry is the full parsed JSON from
        ``latest/archetypes/{format}.json``.  Each deck entry is the full parsed
        JSON from ``latest/decks/{format}/{slug}.json``.
        """
        manifest: dict[str, Any] = {}
        archetype_entries: list[dict[str, Any]] = []
        deck_entries: list[dict[str, Any]] = []

        with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue

                name = member.name
                fobj = tf.extractfile(member)
                if fobj is None:
                    continue

                try:
                    data = json.loads(fobj.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.debug(f"Skipping {name!r}: {exc}")
                    continue

                if name.endswith("latest.json"):
                    manifest = data
                elif "/archetypes/" in name and name.endswith(".json"):
                    archetype_entries.append(data)
                elif "/decks/" in name and name.endswith(".json"):
                    deck_entries.append(data)

        return manifest, archetype_entries, deck_entries

    # ------------------------------------------------------------------ #
    # Cache hydration                                                       #
    # ------------------------------------------------------------------ #

    def _hydrate_archetype_lists(self, archetype_entries: list[dict[str, Any]], now: float) -> None:
        """Merge archetype list entries into ARCHETYPE_LIST_CACHE_FILE."""
        if not archetype_entries:
            return

        with locked_path(self.archetype_list_cache_file):
            existing: dict[str, Any] = {}
            if self.archetype_list_cache_file.exists():
                try:
                    existing = json.loads(
                        self.archetype_list_cache_file.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass

            for entry in archetype_entries:
                fmt = entry.get("format", "").lower()
                archetypes = entry.get("archetypes")
                if not fmt or not isinstance(archetypes, list):
                    continue
                existing[fmt] = {"timestamp": now, "items": archetypes}

            try:
                atomic_write_json(self.archetype_list_cache_file, existing, indent=2)
                logger.debug(f"Hydrated archetype lists for {len(archetype_entries)} format(s)")
            except OSError as exc:
                logger.warning(f"Failed to write archetype list cache: {exc}")

    def _hydrate_archetype_decks(self, deck_entries: list[dict[str, Any]], now: float) -> None:
        """Merge deck list entries into ARCHETYPE_DECKS_CACHE_FILE."""
        if not deck_entries:
            return

        with locked_path(self.archetype_decks_cache_file):
            existing: dict[str, Any] = {}
            if self.archetype_decks_cache_file.exists():
                try:
                    existing = json.loads(
                        self.archetype_decks_cache_file.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass

            for entry in deck_entries:
                archetype = entry.get("archetype", {})
                href = archetype.get("href", "") if isinstance(archetype, dict) else ""
                decks = entry.get("decks")
                if not href or not isinstance(decks, list):
                    continue
                existing[href] = {"timestamp": now, "items": decks}

            try:
                atomic_write_json(self.archetype_decks_cache_file, existing, indent=2)
                logger.debug(f"Hydrated deck lists for {len(deck_entries)} archetype(s)")
            except OSError as exc:
                logger.warning(f"Failed to write archetype decks cache: {exc}")

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                          #
    # ------------------------------------------------------------------ #

    def _http_get_bytes(self, url: str) -> bytes | None:
        """Fetch *url* and return the raw response bytes.

        Returns ``None`` (and logs the error) on any failure so callers can
        raise a more informative error themselves.
        """
        try:
            import curl_cffi.requests as requests  # type: ignore[import-untyped]

            response = requests.get(url, impersonate="chrome", timeout=self.request_timeout)
            response.raise_for_status()
            return response.content
        except ImportError:
            pass
        except Exception as exc:
            logger.debug(f"Bundle download (curl_cffi) failed for {url!r}: {exc}")
            return None

        # Fallback to stdlib urllib
        try:
            from urllib.parse import urlparse
            from urllib.request import urlopen

            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
            with urlopen(url, timeout=self.request_timeout) as resp:  # nosec B310
                return resp.read()
        except Exception as exc:
            logger.debug(f"Bundle download (urllib) failed for {url!r}: {exc}")
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_client: BundleSnapshotClient | None = None


def get_bundle_snapshot_client() -> BundleSnapshotClient:
    """Return the shared ``BundleSnapshotClient`` instance."""
    global _default_client
    if _default_client is None:
        _default_client = BundleSnapshotClient()
    return _default_client


def reset_bundle_snapshot_client() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_client
    _default_client = None
