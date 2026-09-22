"""Deck version-control repository — git-backed history for saved decks.

One git repo per deck, mirrored under ``<CACHE_DIR>/deck_vcs/<deck_key>/``. The
user's own decklist file stays a plain ``.txt`` with no version metadata in it,
which is the constraint the whole design is built around: it has to keep
importing into MTGO and Manatraders unchanged.

Split by responsibility into internal modules:

- ``normalize``: the canonical decklist form every write goes through
- ``models``: the plain records handed upward (``DeckCommit``, ``DeckDiff``)
- ``store``: repo path resolution, creation, and scoped open handles
- ``commits``: committing a decklist, reading one back, walking history
- ``branches``: named pointers and moving between them (never detaching)
- ``diffs``: card-level and unified differences between versions
- ``repository``: :class:`DeckVcsRepository` composed from the above mixins
"""

from __future__ import annotations

from repositories.deck_vcs_repository.models import CardDelta, DeckCommit, DeckDiff
from repositories.deck_vcs_repository.normalize import decklist_fingerprint, normalize_decklist
from repositories.deck_vcs_repository.repository import DeckVcsRepository

_default_repository: DeckVcsRepository | None = None


def get_deck_vcs_repository() -> DeckVcsRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = DeckVcsRepository()
    return _default_repository


def reset_deck_vcs_repository() -> None:
    """Reset the global deck-VCS repository (use in tests for isolation)."""
    global _default_repository
    _default_repository = None


__all__ = [
    "CardDelta",
    "DeckCommit",
    "DeckDiff",
    "DeckVcsRepository",
    "decklist_fingerprint",
    "get_deck_vcs_repository",
    "normalize_decklist",
    "reset_deck_vcs_repository",
]
