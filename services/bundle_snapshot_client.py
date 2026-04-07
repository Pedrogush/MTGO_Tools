"""Bundle snapshot client — downloads and applies the remote client bundle at startup.

The remote repository publishes a single compressed archive (``client-bundle.tar.gz``)
that contains archetype lists and deck lists for all supported formats.  This module
downloads that archive in-memory, extracts it, and writes the data into the local
caches used by ``MetagameRepository``, so that archetype fetching, deck loading,
radar analysis, and metagame analysis all start with warm caches.

Bundle layout inside the archive (paths relative to the tar root):
    latest/latest.json                     — manifest: generated_at, lists all entries
    latest/archetypes/{format}.json        — archetype list for one format
    latest/card-pools/{format}.json        — format card pool + copy totals
    latest/decks/{format}/{slug}.json      — deck list for one archetype slug
    latest/radars/{format}/{slug}.json     — precomputed radar for one archetype

The client writes into:
    ARCHETYPE_LIST_CACHE_FILE   — ``{format: {timestamp, items: [...]}}``
    ARCHETYPE_DECKS_CACHE_FILE  — ``{archetype_href: {timestamp, items: [...]}}``
    FORMAT_CARD_POOL_DB_FILE    — SQLite store for per-format card pools
    RADAR_CACHE_DB_FILE         — SQLite store for precomputed archetype radars

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

from repositories.format_card_pool_repository import FormatCardPoolRepository
from repositories.radar_repository import RadarRepository
from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import (
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    FORMAT_CARD_POOL_DB_FILE,
    RADAR_CACHE_DB_FILE,
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
        format_card_pool_db_file: Path = FORMAT_CARD_POOL_DB_FILE,
        radar_db_file: Path = RADAR_CACHE_DB_FILE,
        stamp_file: Path = REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE,
        max_age: int = REMOTE_SNAPSHOT_BUNDLE_MAX_AGE_SECONDS,
        request_timeout: int = REMOTE_SNAPSHOT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bundle_path = bundle_path
        self.archetype_list_cache_file = Path(archetype_list_cache_file)
        self.archetype_decks_cache_file = Path(archetype_decks_cache_file)
        self.format_card_pool_db_file = Path(format_card_pool_db_file)
        self.radar_db_file = Path(radar_db_file)
        self.stamp_file = Path(stamp_file)
        self.max_age = max_age
        self.request_timeout = request_timeout

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def apply(self) -> tuple[bool, dict[str, list[dict[str, Any]]] | None]:
        """Download the bundle (if stale) and hydrate local caches.

        Returns a ``(updated, archetypes_by_format)`` tuple:

        - ``updated`` is ``True`` if caches were written, ``False`` if the local
          stamp was still fresh (no network activity).
        - ``archetypes_by_format`` maps lowercase format name to the archetype list
          parsed from the bundle, or ``None`` when the bundle was not applied.

        The caller can use ``archetypes_by_format`` to skip a redundant disk read
        immediately after hydration.

        Raises ``BundleSnapshotError`` only when the download itself fails
        unrecoverably; individual parse errors are logged and skipped.
        """
        if self._is_stamp_fresh():
            logger.debug("Bundle stamp is fresh — skipping download")
            return False, None

        logger.info("Downloading remote client bundle…")
        bundle_bytes = self._download_bundle()
        (
            manifest,
            archetype_entries,
            deck_entries,
            deck_texts,
            card_pool_entries,
            radar_entries,
            mtgo_decklist_entries,
        ) = self._parse_bundle(bundle_bytes)

        generated_at = manifest.get("generated_at", "")
        now = time.time()

        self._hydrate_archetype_lists(archetype_entries, now)
        self._hydrate_archetype_decks(deck_entries, now)
        mtgo_merged = self._hydrate_mtgo_decklists(mtgo_decklist_entries, archetype_entries, now)
        card_pools = self._hydrate_format_card_pools(card_pool_entries)
        radars = self._hydrate_radars(radar_entries)
        inserted = self._hydrate_deck_texts(deck_texts)
        self._write_stamp(generated_at, now)

        logger.info(
            f"Bundle applied: {len(archetype_entries)} archetype lists, "
            f"{len(deck_entries)} deck lists, "
            f"{mtgo_merged} MTGO decks merged, "
            f"{card_pools}/{len(card_pool_entries)} card pools, "
            f"{radars}/{len(radar_entries)} radars, "
            f"{inserted}/{len(deck_texts)} deck texts inserted (generated_at={generated_at})"
        )

        archetypes_by_format: dict[str, list[dict[str, Any]]] = {}
        for entry in archetype_entries:
            fmt = entry.get("format", "").lower()
            archetypes = entry.get("archetypes")
            if fmt and isinstance(archetypes, list):
                archetypes_by_format[fmt] = archetypes

        return True, archetypes_by_format or None

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

    def _parse_bundle(self, bundle_bytes: bytes) -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[tuple[str, str, str]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """Extract the bundle and return bundle entries grouped by artifact type.

        Each archetype entry is the full parsed JSON from
        ``latest/archetypes/{format}.json``.  Each deck entry is the full parsed
        JSON from ``latest/decks/{format}/{slug}.json``.  Each deck_texts element
        is a ``(deck_id, deck_text, source)`` tuple ready for ``DeckTextCache.bulk_set``,
        extracted from ``archive/deck-texts/{format}/{id}.json``.
        Each mtgo_decklist entry is the full parsed JSON from
        ``latest/mtgo-decklists/{format}.json``.
        """
        manifest: dict[str, Any] = {}
        archetype_entries: list[dict[str, Any]] = []
        deck_entries: list[dict[str, Any]] = []
        deck_texts: list[tuple[str, str, str]] = []
        card_pool_entries: list[dict[str, Any]] = []
        radar_entries: list[dict[str, Any]] = []
        mtgo_decklist_entries: list[dict[str, Any]] = []

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
                elif name.startswith("latest/mtgo-decklists/") and name.endswith(".json"):
                    mtgo_decklist_entries.append(data)
                elif "/archetypes/" in name and name.endswith(".json"):
                    archetype_entries.append(data)
                elif "/card-pools/" in name and name.endswith(".json"):
                    card_pool_entries.append(data)
                elif name.startswith("archive/deck-texts/") and name.endswith(".json"):
                    deck_id = data.get("deck_id", "")
                    text = data.get("deck_text", "")
                    source = data.get("source", "mtggoldfish")
                    if deck_id and text:
                        deck_texts.append((deck_id, text, source))
                elif "/radars/" in name and name.endswith(".json"):
                    radar_entries.append(data)
                elif "/decks/" in name and name.endswith(".json"):
                    deck_entries.append(data)

        return (
            manifest,
            archetype_entries,
            deck_entries,
            deck_texts,
            card_pool_entries,
            radar_entries,
            mtgo_decklist_entries,
        )

    # ------------------------------------------------------------------ #
    # Cache hydration                                                       #
    # ------------------------------------------------------------------ #

    def _hydrate_archetype_lists(self, archetype_entries: list[dict[str, Any]], now: float) -> None:
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

    def _hydrate_deck_texts(self, deck_texts: list[tuple[str, str, str]]) -> int:
        """Insert deck texts into the SQLite deck text cache.

        Uses INSERT OR IGNORE so already-cached entries are preserved.

        Returns the number of rows inserted.
        """
        if not deck_texts:
            return 0
        try:
            from utils.deck_text_cache import get_deck_cache

            inserted = get_deck_cache().bulk_set(deck_texts, skip_existing=True)
            logger.debug(f"Hydrated {inserted}/{len(deck_texts)} deck texts into SQLite cache")
            return inserted
        except Exception as exc:
            logger.warning(f"Failed to hydrate deck texts: {exc}")
            return 0

    def _hydrate_mtgo_decklists(
        self,
        mtgo_decklist_entries: list[dict[str, Any]],
        archetype_entries: list[dict[str, Any]],
        now: float,
    ) -> int:
        """Merge MTGO event decklists from bundle into the archetype deck cache.

        Builds a name→href lookup from ``archetype_entries``, then for each MTGO
        deck whose ``archetype`` field matches a known archetype name, injects the
        deck metadata into the archetype deck cache and stores the inline deck text
        in the SQLite deck text cache.

        Returns the number of MTGO decks merged.
        """
        if not mtgo_decklist_entries:
            return 0

        # Build {format: {archetype_name: href}} from the archetype list entries
        name_to_href: dict[str, dict[str, str]] = {}
        for entry in archetype_entries:
            fmt = entry.get("format", "").lower()
            for arch in entry.get("archetypes", []):
                name = arch.get("name", "")
                href = arch.get("href", "")
                if name and href:
                    name_to_href.setdefault(fmt, {})[name] = href

        # Collect deck texts and per-href metadata from all MTGO events
        deck_texts: list[tuple[str, str, str]] = []
        decks_by_href: dict[str, list[dict[str, Any]]] = {}

        for entry in mtgo_decklist_entries:
            fmt = entry.get("format", "").lower()
            fmt_lookup = name_to_href.get(fmt, {})
            for event in entry.get("events", []):
                for deck in event.get("decks", []):
                    arch_name = deck.get("archetype", "")
                    href = fmt_lookup.get(arch_name)
                    if not href:
                        continue
                    deck_id = deck.get("number", "")
                    deck_text = deck.get("deck_text", "")
                    if deck_id and deck_text:
                        deck_texts.append((deck_id, deck_text, "mtgo"))
                    date_raw = deck.get("date", "")
                    metadata: dict[str, Any] = {
                        "date": date_raw[:10] if date_raw else "",
                        "number": deck_id,
                        "player": deck.get("player", ""),
                        "event": deck.get("event", ""),
                        "result": deck.get("result", ""),
                        "name": deck.get("name", ""),
                        "source": "mtgo",
                    }
                    decks_by_href.setdefault(href, []).append(metadata)

        if not decks_by_href:
            logger.debug("No MTGO decks could be matched to known archetypes")
            return 0

        # Store deck texts
        if deck_texts:
            try:
                from utils.deck_text_cache import get_deck_cache

                get_deck_cache().bulk_set(deck_texts, skip_existing=True)
            except Exception as exc:
                logger.warning(f"Failed to insert MTGO deck texts: {exc}")

        # Merge into archetype decks cache
        total = 0
        with locked_path(self.archetype_decks_cache_file):
            existing: dict[str, Any] = {}
            if self.archetype_decks_cache_file.exists():
                try:
                    existing = json.loads(
                        self.archetype_decks_cache_file.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    pass

            for href, mtgo_decks in decks_by_href.items():
                existing_entry = existing.get(href, {})
                existing_items = existing_entry.get("items", [])
                # Replace any previously merged MTGO entries to avoid duplicates
                goldfish_items = [d for d in existing_items if d.get("source") != "mtgo"]
                existing[href] = {
                    "timestamp": existing_entry.get("timestamp", now),
                    "items": goldfish_items + mtgo_decks,
                }
                total += len(mtgo_decks)

            try:
                atomic_write_json(self.archetype_decks_cache_file, existing, indent=2)
                logger.debug(
                    f"Merged {total} MTGO decks into {len(decks_by_href)} archetype cache entries"
                )
            except OSError as exc:
                logger.warning(f"Failed to write archetype decks cache with MTGO decks: {exc}")

        return total

    def _hydrate_format_card_pools(self, card_pool_entries: list[dict[str, Any]]) -> int:
        if not card_pool_entries:
            return 0
        try:
            repo = FormatCardPoolRepository(self.format_card_pool_db_file)
            replaced = repo.bulk_replace(card_pool_entries)
            logger.debug(f"Hydrated {replaced}/{len(card_pool_entries)} format card pool snapshots")
            return replaced
        except Exception as exc:
            logger.warning(f"Failed to hydrate format card pools: {exc}")
            return 0

    def _hydrate_radars(self, radar_entries: list[dict[str, Any]]) -> int:
        if not radar_entries:
            return 0
        try:
            repo = RadarRepository(self.radar_db_file)
            replaced = repo.bulk_replace(radar_entries)
            logger.debug(f"Hydrated {replaced}/{len(radar_entries)} precomputed radars")
            return replaced
        except Exception as exc:
            logger.warning(f"Failed to hydrate radars: {exc}")
            return 0

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
    global _default_client
    if _default_client is None:
        _default_client = BundleSnapshotClient()
    return _default_client


def reset_bundle_snapshot_client() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_client
    _default_client = None
