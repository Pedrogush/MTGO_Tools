"""Card repository package.

Combines two layers of card-data access into a single repository:

- ``CardRepository`` (composed from the ``collection``, ``metadata``, and
  ``state`` mixins via ``repository.py``) is the UI-facing read/write surface
  for the user's collection plus the loaded card-data manager handle.
- ``CardDataManager`` (``card_data_manager.py``, supported by ``schemas``,
  ``builder``, ``remote``, and ``storage``) owns the MTGJSON AtomicCards
  dataset: download, on-disk index format, and in-memory query API.

Both halves are exposed at the package level so callers don't need to know
the internal file split. ``CardDataManager`` used to live under
``services.card_data_service``; it moved here in the layer cleanup that
followed the analysis in PR #458 — by the layer rules in ``ARCHITECTURE.md``,
owning a data source and shaping it into domain records is a repository's
job, not a service's.
"""

from __future__ import annotations

from repositories.card_repository.card_data_manager import CardDataManager, load_card_manager
from repositories.card_repository.protocol import CardDataManagerProto, CardRepositoryProto
from repositories.card_repository.repository import CardRepository
from repositories.card_repository.schemas import CardEntry, CardIndex

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
    "CardDataManager",
    "CardDataManagerProto",
    "CardEntry",
    "CardIndex",
    "CardRepository",
    "CardRepositoryProto",
    "get_card_repository",
    "load_card_manager",
    "reset_card_repository",
]
