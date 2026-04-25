"""Shared ``self`` contract that the :class:`DeckRepository` mixins assume.

Each mixin in this package uses :class:`DeckRepositoryProto` as a
``TYPE_CHECKING``-only base so type checkers can see the attributes
that are initialized on ``DeckRepository`` itself.
"""

from __future__ import annotations

from typing import Any, Protocol

import pymongo


class DeckRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckRepository``."""

    _client: pymongo.MongoClient | None
    _db: Any
    _decks: list[dict[str, Any]]
    _current_deck: dict[str, Any] | None
    _current_deck_text: str
    _deck_buffer: dict[str, float]
    _decks_added: int
