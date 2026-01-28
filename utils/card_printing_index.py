"""Card printings index builder and cache manager.

Constructs a compact JSON index mapping card names (including double-faced
aliases) to their Scryfall printing records so that the GUI can perform
fast set/collector-number lookups without re-parsing the full bulk data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017

PRINTING_INDEX_VERSION = 2


def collect_face_aliases(card: dict[str, Any], display_name: str) -> set[str]:
    """Return alternate face names for MDFCs, split, and adventure cards.

    Given a card record and its canonical ``display_name``, produce the set
    of individual face names that should map to the same printing entries.
    The canonical name itself is excluded from the returned set.
    """
    aliases: set[str] = set()
    for raw_face in card.get("card_faces") or []:
        face_name = (raw_face.get("name") or "").strip()
        if face_name:
            aliases.add(face_name)

    if "//" in display_name:
        for piece in display_name.split("//"):
            face_name = piece.strip()
            if face_name:
                aliases.add(face_name)

    display_key = display_name.strip().lower()
    return {alias for alias in aliases if alias.lower() != display_key}


def _load_printing_index_payload(
    printing_index_cache: Path,
    expected_version: int = PRINTING_INDEX_VERSION,
) -> dict[str, Any] | None:
    """Load the cached card printings index if available and current."""
    if not printing_index_cache.exists():
        return None
    try:
        with printing_index_cache.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        logger.warning(f"Failed to read printings index cache: {exc}")
        return None
    if payload.get("version") != expected_version:
        logger.info("Discarding printings index cache due to version mismatch")
        return None
    return payload


def ensure_printing_index_cache(
    force: bool = False,
    *,
    image_cache_dir: Path | None = None,
    bulk_data_cache: Path | None = None,
    printing_index_cache: Path | None = None,
) -> dict[str, Any]:
    """Ensure a compact card printings index exists for fast GUI lookups.

    Args:
        force: Rebuild the index even when an up-to-date cache exists.
        image_cache_dir: Directory for the card image cache.  Defaults to
            the module-level constant from ``card_images`` when *None*.
        bulk_data_cache: Path to the Scryfall bulk data JSON file.
        printing_index_cache: Path to the printings index JSON file.

    Returns:
        The full index payload dict (version, data, metadata).

    Raises:
        FileNotFoundError: When bulk data has not been downloaded yet.
    """
    # Resolve defaults via lazy import to avoid circular dependency
    if image_cache_dir is None or bulk_data_cache is None or printing_index_cache is None:
        from utils.card_images import BULK_DATA_CACHE as _bdc
        from utils.card_images import IMAGE_CACHE_DIR as _icd
        from utils.card_images import PRINTING_INDEX_CACHE as _pic

        image_cache_dir = image_cache_dir or _icd
        bulk_data_cache = bulk_data_cache or _bdc
        printing_index_cache = printing_index_cache or _pic

    image_cache_dir.mkdir(parents=True, exist_ok=True)
    existing = None if force else _load_printing_index_payload(printing_index_cache)
    bulk_mtime = bulk_data_cache.stat().st_mtime if bulk_data_cache.exists() else None

    if existing and (bulk_mtime is None or existing.get("bulk_mtime", 0) >= bulk_mtime):
        return existing

    if bulk_mtime is None:
        raise FileNotFoundError("Bulk data cache not found; cannot build printings index")

    logger.info("Building card printings index from bulk data\u2026")
    with bulk_data_cache.open("r", encoding="utf-8") as fh:
        cards = json.load(fh)

    by_name: dict[str, list[dict[str, Any]]] = {}
    total_printings = 0
    for card in cards:
        name = (card.get("name") or "").strip()
        uuid = card.get("id")
        if not name or not uuid:
            continue
        key = name.lower()
        entry = {
            "id": uuid,
            "set": (card.get("set") or "").upper(),
            "set_name": card.get("set_name") or "",
            "collector_number": card.get("collector_number") or "",
            "released_at": card.get("released_at") or "",
        }
        by_name.setdefault(key, []).append(entry)
        for alias in collect_face_aliases(card, name):
            alias_key = alias.lower()
            if alias_key == key:
                continue
            by_name.setdefault(alias_key, []).append(entry)
        total_printings += 1

    for entries in by_name.values():
        entries.sort(key=lambda c: c.get("released_at") or "", reverse=True)

    payload = {
        "version": PRINTING_INDEX_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "bulk_mtime": bulk_mtime,
        "unique_names": len(by_name),
        "total_printings": total_printings,
        "data": by_name,
    }

    try:
        with printing_index_cache.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        logger.info(
            "Cached card printings index ({unique_names} names, {total_printings} printings)",
            unique_names=payload["unique_names"],
            total_printings=payload["total_printings"],
        )
    except Exception as exc:
        logger.warning(f"Failed to write printings index cache: {exc}")

    return payload
