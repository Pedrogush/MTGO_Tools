"""Card Repository package — data access for card metadata and collections.

Split by responsibility into internal modules:

- ``metadata``: card lookup and search backed by :class:`CardDataManager`
- ``collection``: collection-file I/O (msgspec decoding, normalization)
- ``state``: in-memory card-data loading/ready flags for the UI layer
- ``repository``: :class:`CardRepository` composed from the above mixins
"""

from __future__ import annotations

from repositories.card_repository.repository import CardRepository

_default_repository: CardRepository | None = None


def get_card_repository() -> CardRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = CardRepository()
    return _default_repository


def reset_card_repository() -> None:
    """Reset the global card repository (use in tests for isolation)."""
    global _default_repository
    _default_repository = None


__all__ = [
    "CardRepository",
    "get_card_repository",
    "reset_card_repository",
]
