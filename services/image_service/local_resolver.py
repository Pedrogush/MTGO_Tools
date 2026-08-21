"""Local-index resolution for :class:`BulkImageDownloader`.

Owns the lazily-built name -> :class:`BulkCardImage` index
(``_local_image_index``/``_mtime``/``_lock``, initialized on the composed class)
and the Scryfall ``/cards/named`` and ``/cards/search`` API fallbacks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from services.image_service.bulk_store import decode_bulk_bytes
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


def _printed_names(card: dict[str, Any]) -> set[str]:
    """Lowercased printed/flavor names carried by ``card`` or any of its faces."""
    names: set[str] = set()
    for source in (card, *(card.get("card_faces") or [])):
        for field in ("printed_name", "flavor_name"):
            value = (source.get(field) or "").strip().lower()
            if value:
                names.add(value)
    return names


def _pick_printed_name_match(
    cards: list[dict[str, Any]], name: str, set_code: str | None
) -> dict[str, Any] | None:
    """Pick the printing that actually shows ``name``, preferring ``set_code``.

    Search returns every printing of the matched card, most of which show the
    oracle name; only the ones whose printed/flavor name is the requested name
    can honestly answer the request, so those are preferred (and the requested
    set wins among them). Falls back to the first result so a match on some
    other alias shape still yields an image rather than nothing.
    """
    if not cards:
        return None
    wanted = (name or "").strip().lower()
    wanted_set = (set_code or "").strip().lower()

    def rank(card: dict[str, Any]) -> tuple[int, int]:
        printed = 0 if wanted in _printed_names(card) else 1
        in_set = 0 if wanted_set and (card.get("set") or "").lower() == wanted_set else 1
        return (printed, in_set)

    return min(cards, key=rank)


class LocalResolverMixin(_Base):
    """Local bulk-data image resolution plus Scryfall name/search fallbacks."""

    def fetch_card_by_name(self, name: str, set_code: str | None = None) -> dict[str, Any]:
        params = {"exact": name}
        if set_code:
            params["set"] = set_code.lower()
        resp = self.session.get(
            SCRYFALL_CARD_NAMED_URL, params=params, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS
        )
        if resp.status_code == 404:
            card = self._fetch_card_by_printed_name(name, set_code=set_code)
            if card is not None:
                return card
        resp.raise_for_status()
        return resp.json()

    def _fetch_card_by_printed_name(
        self, name: str, set_code: str | None = None
    ) -> dict[str, Any] | None:
        """Resolve a name that is a *printing's* name rather than a card name.

        ``/cards/named?exact=`` matches Scryfall's ``name`` (and ``flavor_name``)
        only. The MTGO-only Omenpaths "Universes Within" printings carry the
        name MTGO shows in ``printed_name`` instead — "Kavaero, Mind-Bitten" is
        the Omenpaths printing of "Superior Spider-Man" — so exact lookups 404
        forever and the card never gets an image (issue #986). The search
        endpoint's exact operator (``!"..."``) *does* match printed names, so
        it is the general fallback: no per-card alias table needed.

        Returns ``None`` when the search finds nothing, leaving the caller's
        original 404 to stand as the genuine "no such card" answer.
        """
        params = {"q": f'!"{name}"', "unique": "prints", "order": "released"}
        try:
            resp = self.session.get(
                SCRYFALL_CARD_SEARCH_URL, params=params, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS
            )
            if resp.status_code == 404:
                # Scryfall answers 404 for "no cards matched", not just for a
                # bad URL; that is a miss, not an error worth raising.
                return None
            resp.raise_for_status()
            cards = resp.json().get("data") or []
        except Exception as exc:
            logger.debug(f"Printed-name search failed for {name}: {exc}")
            return None
        return _pick_printed_name_match(cards, name, set_code)

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

    def warm_local_index(self) -> None:
        """Build the local name -> image index now instead of on first use.

        The build parses the full bulk-data file (~2s); triggered lazily it
        stalls the first wave of image downloads behind the index lock, so
        callers that know downloads are coming (the download queue at app
        startup) warm it up front on a background thread (issue #951).
        """
        self._get_local_image_index()

    def _resolve_card_locally(
        self, name: str, set_code: str | None = None, uuid: str | None = None
    ) -> BulkCardImage | None:
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
        if uuid:
            wanted_uuid = uuid.strip().lower()
            for entry in entries:
                if (entry.id or "").strip().lower() == wanted_uuid:
                    return entry
            # The exact printing isn't in the local bulk data; fall through to
            # the set/name resolution below rather than failing outright.
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
        from services.image_service.printing_index import collect_name_aliases
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
                    raw = decode_bulk_bytes(bulk_path.read_bytes())
                cards = _bulk_card_images_decoder.decode(raw)
            except Exception as exc:
                logger.warning(f"Failed to build local image index from bulk data: {exc}")
                self._local_image_index = {}
                self._local_image_index_mtime = mtime
                return self._local_image_index

            # A face name that is *also* a real standalone card must not alias
            # into that card's entry list (e.g. "Emeritus of Conflict //
            # Lightning Bolt" must not resolve for "Lightning Bolt"), matching
            # the guard build_printing_index applies (issue #792). Without it
            # this index and the printing index disagree, so the hover path can
            # download a different card than the one the inspector shows.
            primary_names = {
                (card.name or "").strip().lower()
                for card in cards
                if (card.name or "").strip() and card.id
            }
            index: dict[str, list[BulkCardImage]] = {}
            for card in cards:
                name = (card.name or "").strip()
                if not name or not card.id:
                    continue
                key = name.lower()
                index.setdefault(key, []).append(card)
                # Alias individual face names (and split halves) so that deck
                # entries that reference a single face still resolve locally,
                # mirroring Scryfall's exact-name face matching — plus the
                # printing's own printed/flavor name, which is how MTGO spells
                # the Omenpaths "Universes Within" cards (issue #986).
                for alias in collect_name_aliases(card, name):
                    alias_key = alias.lower()
                    if alias_key != key and alias_key not in primary_names:
                        index.setdefault(alias_key, []).append(card)
            self._local_image_index = index
            self._local_image_index_mtime = mtime
            logger.debug(f"Built local image index ({len(index)} names) from bulk data")
            return self._local_image_index
