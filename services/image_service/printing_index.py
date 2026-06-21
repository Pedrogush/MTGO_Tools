"""Printing index loading and state management.

Contains:
- Pure functions for building / loading / persisting the printing index
  cache (used both in-process and by the subprocess worker)
- :class:`PrintingIndexMixin` — async coordination on :class:`ImageService`
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import msgspec
from loguru import logger

from services.image_service.schemas import (
    BULK_DATA_CACHE,
    IMAGE_CACHE_DIR,
    PRINTING_INDEX_CACHE,
    PRINTING_INDEX_VERSION,
    UTC,
    _bulk_cards_decoder,
    _printing_index_decoder,
)
from utils.atomic_io import atomic_write_json, locked_path

if TYPE_CHECKING:
    from services.image_service.protocol import ImageServiceProto

    _Base = ImageServiceProto
else:
    _Base = object


# ---------------------------------------------------------------------------
# Pure helpers (also reused by the subprocess worker)
# ---------------------------------------------------------------------------


def _collect_face_aliases(card: dict[str, Any], display_name: str) -> set[str]:
    """Return alternate face names for MDFCs, split, and adventure cards."""
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


def build_printing_index(
    cards: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Build a compact printing index from bulk card data.

    Face names are indexed as aliases so a deck listing a single face of an
    MDFC/split/adventure card still resolves to its printings. A face name that
    is *also* a real standalone card is left alone, though: e.g. "Emeritus of
    Conflict // Lightning Bolt" must not inject itself into the genuine
    "Lightning Bolt" printing list, or the inspector/dropdown would offer that
    adventure card as a Lightning Bolt printing (issue #792).
    """
    primary_names = {
        (card.get("name") or "").strip().lower()
        for card in cards
        if (card.get("name") or "").strip() and card.get("id")
    }
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
            "flavor_text": card.get("flavor_text") or "",
            "artist": card.get("artist") or "",
            "full_art": bool(card.get("full_art")),
        }
        by_name.setdefault(key, []).append(entry)
        for alias in _collect_face_aliases(card, name):
            alias_key = alias.lower()
            if alias_key == key or alias_key in primary_names:
                continue
            by_name.setdefault(alias_key, []).append(entry)
        total_printings += 1

    for entries in by_name.values():
        entries.sort(key=lambda c: c.get("released_at") or "", reverse=True)

    stats = {
        "unique_names": len(by_name),
        "total_printings": total_printings,
    }
    return by_name, stats


def _load_printing_index_payload() -> dict[str, Any] | None:
    """Load the cached card printings index if available."""
    # Honour test monkeypatches that replace the constants on this module.
    from services.image_service import schemas as _schemas

    if not _schemas.PRINTING_INDEX_CACHE.exists():
        return None
    try:
        with locked_path(_schemas.PRINTING_INDEX_CACHE):
            raw = _schemas.PRINTING_INDEX_CACHE.read_bytes()
        payload = _printing_index_decoder.decode(raw)
    except (msgspec.DecodeError, OSError) as exc:
        logger.warning(f"Failed to read printings index cache: {exc}")
        return None
    if payload.version != PRINTING_INDEX_VERSION:
        logger.info("Discarding printings index cache due to version mismatch")
        return None
    # Convert to plain dict so callers can use .get() / [] as before.
    return msgspec.to_builtins(payload)


def load_printing_index_payload() -> dict[str, Any] | None:
    """Load the cached card printings index without rebuilding it."""
    return _load_printing_index_payload()


def ensure_printing_index_cache(force: bool = False) -> dict[str, Any]:
    """Ensure a compact card printings index exists for fast wx lookups."""
    from services.image_service import schemas as _schemas

    _schemas.IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    existing = None if force else _load_printing_index_payload()
    bulk_mtime = (
        _schemas.BULK_DATA_CACHE.stat().st_mtime if _schemas.BULK_DATA_CACHE.exists() else None
    )

    if existing and (bulk_mtime is None or existing.get("bulk_mtime", 0) >= bulk_mtime):
        return existing

    if bulk_mtime is None:
        raise FileNotFoundError("Bulk data cache not found; cannot build printings index")

    logger.info("Building card printings index from bulk data…")
    with locked_path(_schemas.BULK_DATA_CACHE):
        raw = _schemas.BULK_DATA_CACHE.read_bytes()
    cards = _bulk_cards_decoder.decode(raw)

    by_name, stats = build_printing_index(cards)

    payload = {
        "version": PRINTING_INDEX_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "bulk_mtime": bulk_mtime,
        "unique_names": stats["unique_names"],
        "total_printings": stats["total_printings"],
        "data": by_name,
    }

    try:
        atomic_write_json(_schemas.PRINTING_INDEX_CACHE, payload, separators=(",", ":"))
        logger.info(
            "Cached card printings index ({unique_names} names, {total_printings} printings)",
            unique_names=payload["unique_names"],
            total_printings=payload["total_printings"],
        )
    except Exception as exc:
        logger.warning(f"Failed to write printings index cache: {exc}")

    return payload


# Re-export for callers that previously imported these names from this module
# (avoids unused-import warnings while keeping module-level constants resolvable).
__all__ = [
    "BULK_DATA_CACHE",
    "IMAGE_CACHE_DIR",
    "PRINTING_INDEX_CACHE",
    "PRINTING_INDEX_VERSION",
    "PrintingIndexMixin",
    "build_printing_index",
    "ensure_printing_index_cache",
    "load_printing_index_payload",
]


# ---------------------------------------------------------------------------
# Mixin for :class:`ImageService`
# ---------------------------------------------------------------------------


class PrintingIndexMixin(_Base):
    """Load and track the printing index in the background."""

    def load_printing_index_async(
        self,
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> bool:
        from services.image_service import schemas as _schemas
        from services.image_service.workers import build_printing_index_worker

        if self.printing_index_loading and not force:
            logger.debug("Printing index already loading")
            return False

        if self.bulk_data_by_name and not force:
            logger.debug("Printing index already loaded")
            return False

        self.printing_index_loading = True

        existing = None if force else load_printing_index_payload()
        bulk_mtime = (
            _schemas.BULK_DATA_CACHE.stat().st_mtime if _schemas.BULK_DATA_CACHE.exists() else None
        )
        if existing and (bulk_mtime is None or existing.get("bulk_mtime", 0) >= bulk_mtime):
            data = existing.get("data", {})
            stats = {
                "unique_names": existing.get("unique_names", len(data)),
                "total_printings": existing.get(
                    "total_printings", sum(len(v) for v in data.values())
                ),
            }
            on_success(data, stats)
            return True

        if self._printings_handle and self._printings_handle.process.is_alive():
            logger.debug("Printing index process already running")
            return False

        def _on_success(result: dict[str, Any]) -> None:
            payload = load_printing_index_payload()
            if not payload:
                on_error("Printings index cache missing after build.")
                return
            data = payload.get("data", {})
            stats = {
                "unique_names": payload.get("unique_names", len(data)),
                "total_printings": payload.get(
                    "total_printings", sum(len(v) for v in data.values())
                ),
            }
            on_success(data, stats)

        def _on_error(msg: str) -> None:
            on_error(msg)

        try:
            self._printings_handle = self._process_worker.run_async(
                target=build_printing_index_worker,
                args=(),
                kwargs={
                    "bulk_data_path": str(_schemas.BULK_DATA_CACHE),
                    "printings_path": str(_schemas.PRINTING_INDEX_CACHE),
                    "printings_version": PRINTING_INDEX_VERSION,
                },
                on_success=_on_success,
                on_error=_on_error,
                call_after=self._call_after,
            )
        except Exception as exc:
            logger.exception("Failed to start printings index process")
            on_error(str(exc))
            self.printing_index_loading = False
            return False

        return True

    def set_bulk_data(self, bulk_data: dict[str, list[dict[str, Any]]]) -> None:
        self.bulk_data_by_name = bulk_data

    def clear_printing_index_loading(self) -> None:
        self.printing_index_loading = False

    def get_bulk_data(self) -> dict[str, list[dict[str, Any]]] | None:
        return self.bulk_data_by_name

    def is_loading(self) -> bool:
        return self.printing_index_loading
