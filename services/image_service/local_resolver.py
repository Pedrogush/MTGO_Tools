"""Local-index resolution for :class:`BulkImageDownloader`.

Owns the lazily-built name -> :class:`BulkCardImage` index
(``_local_image_index``/``_mtime``/``_lock``, initialized on the composed class)
and the Scryfall ``/cards/named`` and ``/cards/search`` API fallbacks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from services.image_service.schemas import (
    SCRYFALL_CARD_NAMED_URL,
    SCRYFALL_CARD_SEARCH_URL,
    BulkCardImage,
)
from utils.atomic_io import locked_path
from utils.constants import SCRYFALL_REQUEST_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from services.image_service.downloader_protocol import BulkImageDownloaderProto

    _Base = BulkImageDownloaderProto
else:
    _Base = object


class LocalResolverMixin(_Base):
    """Local bulk-data image resolution plus Scryfall name/search fallbacks."""

    def fetch_card_by_name(self, name: str, set_code: str | None = None) -> dict[str, Any]:
        params = {"exact": name}
        if set_code:
            params["set"] = set_code.lower()
        resp = self.session.get(
            SCRYFALL_CARD_NAMED_URL, params=params, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_printings_by_name(self, name: str) -> list[dict[str, Any]]:
        params = {"q": f'!"{name}"', "unique": "prints", "order": "released"}
        results: list[dict[str, Any]] = []
        url: str | None = SCRYFALL_CARD_SEARCH_URL
        while url:
            resp = self.session.get(url, params=params, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            payload = resp.json()
            results.extend(payload.get("data", []))
            url = payload.get("next_page")
            params = None
        return results

    def _resolve_card_locally(self, name: str, set_code: str | None = None) -> BulkCardImage | None:
        """Resolve a card's image metadata from the locally-cached bulk data.

        Returns ``None`` on any miss (no bulk data, name absent, or no
        matching printing for the requested set) so callers fall back to the
        Scryfall ``/cards/named`` API.
        """
        index = self._get_local_image_index()
        if not index:
            return None
        entries = index.get((name or "").strip().lower())
        if not entries:
            return None
        if set_code:
            wanted = set_code.strip().lower()
            for entry in entries:
                if (entry.set or "").strip().lower() == wanted:
                    return entry
            # Requested a specific printing we don't have locally; defer to the
            # API so the correct set printing is fetched.
            return None
        return entries[0]

    def _get_local_image_index(self) -> dict[str, list[BulkCardImage]] | None:
        """Lazily build (and cache) the name -> image-record index.

        The index is rebuilt when the on-disk bulk data file changes. Building
        parses the full bulk file once; subsequent lookups are in-memory.
        """
        from services.image_service import schemas as _schemas
        from services.image_service.printing_index import _collect_face_aliases
        from services.image_service.schemas import _bulk_card_images_decoder

        bulk_path = _schemas.BULK_DATA_CACHE
        if not bulk_path.exists():
            return None

        try:
            mtime = bulk_path.stat().st_mtime
        except OSError:
            return None

        with self._local_image_index_lock:
            if self._local_image_index is not None and self._local_image_index_mtime == mtime:
                return self._local_image_index

            try:
                with locked_path(bulk_path):
                    raw = bulk_path.read_bytes()
                cards = _bulk_card_images_decoder.decode(raw)
            except Exception as exc:
                logger.warning(f"Failed to build local image index from bulk data: {exc}")
                self._local_image_index = {}
                self._local_image_index_mtime = mtime
                return self._local_image_index

            index: dict[str, list[BulkCardImage]] = {}
            for card in cards:
                name = (card.name or "").strip()
                if not name or not card.id:
                    continue
                key = name.lower()
                index.setdefault(key, []).append(card)
                # Alias individual face names (and split halves) so that deck
                # entries that reference a single face still resolve locally,
                # mirroring Scryfall's exact-name face matching.
                for alias in _collect_face_aliases(card, name):
                    alias_key = alias.lower()
                    if alias_key != key:
                        index.setdefault(alias_key, []).append(card)
            self._local_image_index = index
            self._local_image_index_mtime = mtime
            logger.debug(f"Built local image index ({len(index)} names) from bulk data")
            return self._local_image_index
