"""Schemas, constants, and request types for the image service.

Contains:
- Cache-related path constants (``IMAGE_CACHE_DIR``, ``BULK_DATA_CACHE``, ...)
- Image size catalog and Scryfall endpoints
- msgspec structs for fast bulk-data / printing-index decoding
- :class:`CardImageRequest` dataclass used by the download queue
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any

import msgspec
import msgspec.json

try:  # Python 3.11+ has UTC
    from datetime import UTC
except ImportError:  # pragma: no cover - compatibility shim for Python 3.10
    UTC = timezone.utc  # noqa: UP017

from utils.constants import CACHE_DIR

# Image cache configuration
IMAGE_CACHE_DIR = CACHE_DIR / "card_images"
IMAGE_DB_PATH = IMAGE_CACHE_DIR / "images.db"
BULK_DATA_CACHE = IMAGE_CACHE_DIR / "bulk_data.json"
# v5: face-name aliases no longer overwrite a real standalone card's printing
# list (e.g. "Emeritus of Conflict // Lightning Bolt" must not pollute
# "Lightning Bolt"); bumping forces a rebuild of the cached index (issue #792).
PRINTING_INDEX_VERSION = 5
PRINTING_INDEX_CACHE = IMAGE_CACHE_DIR / f"printings_v{PRINTING_INDEX_VERSION}.json"

# Image size options (in order of preference for storage)
IMAGE_SIZES = {
    "small": "small",  # 146x204 - thumbnails
    "normal": "normal",  # 488x680 - default
    "large": "large",  # 672x936 - high quality
    "png": "png",  # 745x1040 - highest quality, transparent
}

# Download configuration
BULK_DATA_URL = "https://api.scryfall.com/bulk-data/default-cards"
SCRYFALL_CARD_NAMED_URL = "https://api.scryfall.com/cards/named"
SCRYFALL_CARD_SEARCH_URL = "https://api.scryfall.com/cards/search"


# ---------------------------------------------------------------------------
# msgspec schemas for fast JSON loading
# ---------------------------------------------------------------------------


class BulkCardFace(msgspec.Struct, gc=False):
    """Minimal face entry from Scryfall bulk data (only fields we use)."""

    name: str | None = None
    image_uris: dict[str, str] | None = None

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None


class BulkCard(msgspec.Struct, gc=False):
    """Minimal Scryfall bulk-data card record containing only the fields
    required by :func:`build_printing_index`.  msgspec silently skips all
    other fields present in the JSON, which makes parsing even faster.

    Dict-compatible accessors are provided so that the existing
    ``card.get(...)`` call sites continue to work unchanged.
    """

    name: str | None = None
    id: str | None = None
    set: str | None = None
    set_name: str | None = None
    collector_number: str | None = None
    released_at: str | None = None
    flavor_text: str | None = None
    artist: str | None = None
    full_art: bool | None = None
    card_faces: list[BulkCardFace] | None = None

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None


class BulkCardImage(msgspec.Struct, gc=False):
    """Minimal Scryfall bulk-data card record carrying image URLs.

    Used to build an in-memory name -> image-URL map so that
    :meth:`BulkImageDownloader.download_card_image_by_name` can resolve image
    URLs from the locally-cached bulk data instead of issuing a Scryfall
    ``/cards/named`` round-trip on every uncached card.  Only the fields
    consumed by ``_download_single_image`` are decoded; msgspec skips the rest.
    """

    name: str | None = None
    id: str | None = None
    set: str | None = None
    collector_number: str | None = None
    scryfall_uri: str | None = None
    artist: str | None = None
    image_uris: dict[str, str] | None = None
    card_faces: list[BulkCardFace] | None = None

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None


class PrintingEntry(msgspec.Struct, gc=False):
    """A single card printing record stored in the printings index."""

    id: str
    set: str
    set_name: str
    collector_number: str
    released_at: str
    flavor_text: str = ""
    artist: str = ""
    full_art: bool = False

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None


class PrintingIndexPayload(msgspec.Struct):
    """Root structure of the saved printing index cache file."""

    version: int
    generated_at: str
    bulk_mtime: float
    unique_names: int
    total_printings: int
    data: dict[str, list[PrintingEntry]]


# Pre-instantiated decoders – reusing avoids re-building on every call.
_bulk_cards_decoder: msgspec.json.Decoder[list[BulkCard]] = msgspec.json.Decoder(list[BulkCard])
_bulk_card_images_decoder: msgspec.json.Decoder[list[BulkCardImage]] = msgspec.json.Decoder(
    list[BulkCardImage]
)
_printing_index_decoder: msgspec.json.Decoder[PrintingIndexPayload] = msgspec.json.Decoder(
    PrintingIndexPayload
)


@dataclass(frozen=True)
class CardImageRequest:
    """Represents a single card image download request."""

    card_name: str
    uuid: str | None
    set_code: str | None
    collector_number: str | None
    size: str = "normal"

    def queue_key(self) -> tuple[str, str, str, str]:
        if self.uuid:
            return ("uuid", self.uuid.lower(), self.size, "")
        set_code = (self.set_code or "").lower()
        collector = (self.collector_number or "").lower()
        return ("set", set_code, collector, self.size)

    def can_fetch(self) -> bool:
        return bool((self.card_name or "").strip())


__all__ = [
    "BULK_DATA_CACHE",
    "BULK_DATA_URL",
    "BulkCard",
    "BulkCardFace",
    "BulkCardImage",
    "CardImageRequest",
    "IMAGE_CACHE_DIR",
    "IMAGE_DB_PATH",
    "IMAGE_SIZES",
    "PRINTING_INDEX_CACHE",
    "PRINTING_INDEX_VERSION",
    "PrintingEntry",
    "PrintingIndexPayload",
    "SCRYFALL_CARD_NAMED_URL",
    "SCRYFALL_CARD_SEARCH_URL",
    "UTC",
    "_bulk_card_images_decoder",
    "_bulk_cards_decoder",
    "_printing_index_decoder",
]
