"""Which card names have ever been printed at common.

This exists for one question the format detector asks: *is this deck Pauper?*

Pauper is the only MTGO format whose card pool is defined by **rarity** rather
than by a set list, and that makes it invisible to the legality intersection in
:mod:`services.gamelog_service.formats`. Every Pauper-legal card is also Legacy-
and Vintage-legal, so intersecting "formats this card is legal in" over a Pauper
deck yields ``{legacy, vintage, pauper, ...}`` and the intersection can never
single Pauper out. Re-ordering that list so Pauper wins the tie only papers over
the same mistake: it keys off legality when the property that actually
distinguishes the format is rarity.

The rule this module supports, stated by the user and measured below, is:

    If **every** card in the deck has a printing at common, the deck is Pauper.

Note "has a printing at common", not "is currently common": a card first printed
at common and reprinted at uncommon still counts, which is exactly how Pauper
legality works and is why a per-printing scan (rather than a single rarity field)
is required.

Where the data comes from
-------------------------
Per-printing rarity is **not** in the local card index. ``CardEntry``
(:mod:`repositories.card_repository.schemas`) has no rarity field, and it could
not have one usefully: it is built from MTGJSON *AtomicCards*, which is
oracle-level and deduplicated across printings, so it carries no rarity at all.

The one rarity source already on disk is the Scryfall **default-cards** bulk file
the image service downloads for card art
(:data:`services.image_service.schemas.BULK_DATA_CACHE`) -- one record per
printing, each with a ``rarity``. Scanning it costs ~2.4 s and ~620 MB of peak
memory, so the derived answer (a sorted list of ~17.8k folded names, ~400 KB) is
persisted next to the other caches and rebuilt only when the bulk file changes.

When the bulk file is absent -- a fresh install before the art download finishes
-- :meth:`CardRarityService.is_loaded` stays ``False`` and the format detector
skips the Pauper test entirely, which is exactly its behaviour today.
"""

from __future__ import annotations

import json
from pathlib import Path

import msgspec
from loguru import logger

from utils.atomic_io import atomic_write_json
from utils.card_names import fold_card_name
from utils.constants import CACHE_DIR

#: Bumped when the derived shape changes, so a stale file is ignored rather than
#: misread. ``v1`` is
#: ``{"bulk_mtime": float, "common": [str, ...], "known": [str, ...]}``.
COMMON_PRINTINGS_CACHE = CACHE_DIR / "common_printings_v1.json"


class _BulkFace(msgspec.Struct, gc=False):
    """The one face field needed to alias a double-faced card's halves."""

    name: str | None = None


class _BulkCard(msgspec.Struct, gc=False):
    """A Scryfall bulk printing, decoded down to name + rarity.

    msgspec skips every field not declared here, which is what keeps a 620 MB
    document down to a sub-second decode.
    """

    name: str | None = None
    rarity: str | None = None
    printed_name: str | None = None
    card_faces: list[_BulkFace] | None = None


_bulk_decoder: msgspec.json.Decoder[list[_BulkCard]] = msgspec.json.Decoder(list[_BulkCard])


def _name_keys(name: str | None) -> list[str]:
    """Return every folded key a decklist might spell *name* as.

    Both halves of a ``A // B`` name are indexed alongside the combined form,
    because MTGO's game log names the half that was cast.
    """
    if not name:
        return []
    keys = [fold_card_name(name)]
    if "//" in name:
        keys.extend(fold_card_name(part.strip()) for part in name.split("//") if part.strip())
    return [key for key in keys if key]


def build_common_printing_names(bulk_json: bytes) -> tuple[set[str], set[str]]:
    """Return ``(names printed at common, every name seen)``, both folded.

    Both halves are needed, and the second is the one that is easy to forget: a
    name the bulk has *never* heard of has to be distinguishable from a name it
    knows only above common. Without that distinction one unrecognised string
    reads as "not common" and vetoes the Pauper verdict for the whole deck --
    which is not hypothetical, it is how a spelling difference behaves. MTGO and
    MTGGoldfish write ``Summon: Choco/Mog`` and ``Summon: Choco // Mog``; the
    card is a common either way.

    Pure: takes the decompressed bulk document and returns the derived sets, so
    the scan is testable without a 620 MB file on disk.
    """
    common: set[str] = set()
    known: set[str] = set()
    for card in _bulk_decoder.decode(bulk_json):
        keys = _name_keys(card.name) + _name_keys(card.printed_name)
        for face in card.card_faces or ():
            keys.extend(_name_keys(face.name))
        known.update(keys)
        if card.rarity == "common":
            common.update(keys)
    return common, known


class CardRarityService:
    """Lazily answers "has this card ever been printed at common?".

    Loading is explicit (:meth:`load`) rather than implicit on first query: the
    build reads and decompresses the whole bulk file, which must not happen on
    the UI thread. Callers that have not loaded see ``is_loaded == False`` and
    are expected to skip the Pauper test rather than get a wrong answer.
    """

    def __init__(
        self,
        bulk_path: Path | None = None,
        cache_path: Path | None = None,
    ) -> None:
        from services.image_service.schemas import BULK_DATA_CACHE

        self._bulk_path = Path(bulk_path) if bulk_path is not None else BULK_DATA_CACHE
        self._cache_path = Path(cache_path) if cache_path is not None else COMMON_PRINTINGS_CACHE
        self._common: set[str] | None = None
        self._known: set[str] = set()

    @property
    def is_loaded(self) -> bool:
        return self._common is not None

    @property
    def name_count(self) -> int:
        return len(self._common or ())

    def has_common_printing(self, card_name: str) -> bool | None:
        """``True``/``False`` for a known card, ``None`` when it is not indexed.

        The three-valued answer matters: a name the bulk has never heard of (a
        token, a mis-parsed log line, a printing MTGO spells differently) must
        not be read as "not common", or one unknown string would veto the Pauper
        verdict for a whole deck.
        """
        if self._common is None:
            return None
        key = fold_card_name(card_name)
        if not key or key not in self._known:
            return None
        return key in self._common

    def load(self) -> bool:
        """Populate the index from the derived cache, or build it from the bulk.

        Returns whether an index is available afterwards. Never raises: every
        failure path degrades to "not loaded", which disables the Pauper test.
        """
        if self._common is not None:
            return True

        bulk_mtime = self._bulk_mtime()
        if bulk_mtime is None:
            logger.debug(f"Scryfall bulk data not present at {self._bulk_path}; rarity unavailable")
            return False

        cached = self._load_cache(bulk_mtime)
        if cached is not None:
            self._common, self._known = cached
            logger.debug(f"Loaded {len(self._common)} common-printing names from cache")
            return True

        try:
            from services.image_service.bulk_store import decode_bulk_bytes

            common, known = build_common_printing_names(
                decode_bulk_bytes(self._bulk_path.read_bytes())
            )
        except Exception as exc:  # noqa: BLE001 - any failure means "no rarity data"
            logger.warning(f"Failed to derive common printings from the Scryfall bulk: {exc}")
            return False

        self._common, self._known = common, known
        self._save_cache(bulk_mtime, common, known)
        logger.info(
            f"Derived {len(common)} card names with a printing at common, out of {len(known)}"
        )
        return True

    # ------------------------------------------------------------------ cache
    def _bulk_mtime(self) -> float | None:
        try:
            return self._bulk_path.stat().st_mtime
        except OSError:
            return None

    def _load_cache(self, bulk_mtime: float) -> tuple[set[str], set[str]] | None:
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        # Keyed on the bulk file's mtime so a refreshed bulk (new set, new
        # commons) invalidates the derivation without a version bump.
        if payload.get("bulk_mtime") != bulk_mtime:
            return None
        common, known = payload.get("common"), payload.get("known")
        if not isinstance(common, list) or not isinstance(known, list):
            return None
        return {str(name) for name in common}, {str(name) for name in known}

    def _save_cache(self, bulk_mtime: float, common: set[str], known: set[str]) -> None:
        try:
            atomic_write_json(
                self._cache_path,
                {
                    "bulk_mtime": bulk_mtime,
                    "common": sorted(common),
                    "known": sorted(known),
                },
            )
        except Exception as exc:  # noqa: BLE001 - a cache miss next time is harmless
            logger.debug(f"Could not persist the common-printing cache: {exc}")


_default_service: CardRarityService | None = None


def get_card_rarity_service() -> CardRarityService:
    """Return the shared :class:`CardRarityService` instance."""
    global _default_service
    if _default_service is None:
        _default_service = CardRarityService()
    return _default_service


def reset_card_rarity_service() -> None:
    """Reset the global rarity service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "COMMON_PRINTINGS_CACHE",
    "CardRarityService",
    "build_common_printing_names",
    "get_card_rarity_service",
    "reset_card_rarity_service",
]
