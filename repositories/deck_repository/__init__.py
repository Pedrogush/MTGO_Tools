"""Deck Repository package — centralised persistence and state for decks.

Split by responsibility into internal modules:

- ``database``: MongoDB CRUD (``save_to_db``, ``get_decks``, ``update_in_db`` …)
- ``filesystem``: deck-text file I/O and legacy-path migration
- ``metadata_store``: per-deck notes, outboard, and sideboard-guide JSON stores
- ``ui_state``: in-memory deck/current-deck/averaging buffer kept for the UI layer
- ``repository``: :class:`DeckRepository` composed from the above mixins
"""

from __future__ import annotations

from repositories.deck_repository.repository import DeckRepository

_default_repository: DeckRepository | None = None


def get_deck_repository() -> DeckRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = DeckRepository()
    return _default_repository


def reset_deck_repository() -> None:
    """Reset the global deck repository (use in tests for isolation)."""
    global _default_repository
    _default_repository = None


__all__ = [
    "DeckRepository",
    "get_deck_repository",
    "reset_deck_repository",
]
