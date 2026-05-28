"""Top-level orchestrator for the card-data side of :mod:`repositories.card_repository`.

``CardDataManager`` ties the remote, builder, and storage modules together
and exposes the in-memory query API (``search_cards``, ``get_card``,
``available_formats``).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from loguru import logger

from repositories.card_repository import remote, storage
from repositories.card_repository.builder import build_index
from repositories.card_repository.schemas import CardEntry
from utils.constants import CARD_DATA_DIR
from utils.perf import timed


def load_card_manager(data_dir: Path | str = CARD_DATA_DIR, force: bool = False) -> CardDataManager:
    # Synchronous – call from a background thread. Downloads/updates card data if needed.
    manager = CardDataManager(data_dir)
    manager.ensure_latest(force=force)
    return manager


class CardDataManager:
    def __init__(self, data_dir: Path | str = CARD_DATA_DIR):
        self.data_dir, self.index_path, self.meta_path = storage.resolve_paths(data_dir)
        self._cards: list[CardEntry] | None = None
        self._cards_by_name: dict[str, CardEntry] | None = None

    def ensure_latest(self, force: bool = False) -> None:
        # One-time conversion of a pre-msgpack JSON index so existing installs
        # avoid a needless re-download on first launch after the format change.
        storage.migrate_legacy_index(self.index_path, storage.legacy_index_path(self.data_dir))
        remote_meta = remote.fetch_dataset_headers()
        local_meta = storage.load_meta(self.meta_path) or {}
        missing_index = not self.index_path.exists()
        needs_refresh = force or missing_index
        if not needs_refresh and remote_meta:
            remote_size = remote_meta.get("content_length")
            local_size = local_meta.get("content_length")
            if remote_size and local_size != remote_size:
                logger.warning(f"File size changed: local={local_size}, remote={remote_size}")
                logger.warning("Forcing a refresh")
                needs_refresh = True

        if needs_refresh:
            logger.warning("No atomic card index found or force refresh requested")
            try:
                if remote_meta:
                    logger.info("Refreshing MTGJSON AtomicCards dataset")
                else:
                    logger.info("Fetching MTGJSON AtomicCards dataset (using headers for metadata)")
                self._download_and_rebuild(remote_meta)
            except Exception as exc:
                if missing_index:
                    raise RuntimeError(
                        "Card data download failed and no cache is available"
                    ) from exc
                logger.warning(f"Failed to refresh MTGJSON data, using cache: {exc}")
        self._load_index()

    def search_cards(
        self,
        query: str = "",
        format_filter: str | None = None,
        type_filter: str | None = None,
        color_identity: list[str] | None = None,
        limit: int | None = None,
    ) -> list[CardEntry]:
        self._require_cards()
        query = (query or "").strip().lower()
        fmt = (format_filter or "").strip().lower()
        type_filter = (type_filter or "").strip().lower()
        color_identity = [c.upper() for c in (color_identity or [])]
        results: list[CardEntry] = []
        for card in self._cards or []:
            name_lower = card.name_lower
            type_line = (card.type_line or "").lower()
            oracle_text = (card.oracle_text or "").lower()
            if query:
                haystacks = (
                    name_lower,
                    type_line,
                    oracle_text,
                )
                if not any(query in h for h in haystacks if h):
                    continue
            if fmt and card.legalities.get(fmt) != "Legal":
                continue
            if type_filter and type_filter not in type_line:
                continue
            if color_identity:
                identity = card.color_identity
                if not all(c in identity for c in color_identity):
                    continue
            results.append(card)
            if limit and len(results) >= limit:
                break
        return results

    def get_card(self, name: str) -> CardEntry | None:
        self._require_cards()
        return (self._cards_by_name or {}).get(name.lower())

    def available_formats(self) -> list[str]:
        self._require_cards()
        seen = set()
        formats: list[str] = []
        for card in self._cards or []:
            for fmt, state in card.legalities.items():
                if state != "Legal" or fmt in seen:
                    continue
                seen.add(fmt)
                formats.append(fmt)
        return sorted(formats)

    @property
    def is_loaded(self) -> bool:
        return self._cards is not None

    def _require_cards(self) -> None:
        if self._cards is None:
            raise RuntimeError("Card data not loaded; call ensure_latest first")

    def _download_and_rebuild(self, remote_meta: dict[str, Any] | None) -> None:
        content, headers = remote.download_atomic_cards_zip()
        digest = hashlib.sha512(content).hexdigest()
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            with zf.open("AtomicCards.json") as source:
                raw = json.load(source)
        index = build_index(raw.get("data", {}))
        storage.write_index(self.index_path, index)
        meta_to_store: dict[str, Any] = remote_meta.copy() if remote_meta else {}
        meta_to_store.setdefault("sha512", digest)
        if "etag" in headers:
            meta_to_store.setdefault("etag", headers["etag"].strip('"'))
        if "last-modified" in headers:
            meta_to_store.setdefault("last_modified", headers["last-modified"])
        if "content-length" in headers:
            meta_to_store.setdefault("content_length", headers["content-length"])
        storage.write_meta(self.meta_path, meta_to_store)
        self._cards = index["cards"]
        self._cards_by_name = index["cards_by_name"]

    @timed
    def _load_index(self) -> None:
        card_index = storage.load_index(self.index_path)
        self._cards = card_index.cards
        self._cards_by_name = card_index.cards_by_name


__all__ = ["CardDataManager", "load_card_manager"]
