"""Metagame Repository package — data access for archetype and deck metadata.

Split by responsibility into internal modules:

- ``date_utils``: :func:`_parse_deck_date` date-format helper
- ``cache``: archetype-list / archetype-decks JSON cache I/O and filters
- ``archetype_resolution``: format → archetype list / stats resolution with
  cache → remote snapshot → live-scrape fallback order
- ``deck_operations``: deck-list fetching, aggregated listings, and downloads
- ``background``: stale-while-revalidate background refresh helper
- ``repository``: :class:`MetagameRepository` composed from the above mixins

``get_archetypes``, ``get_archetype_decks``, ``fetch_deck_text``, and
``REMOTE_SNAPSHOTS_ENABLED`` are re-exported here so tests can monkeypatch them
through the package namespace exactly as they did when this was a flat module.
Submodules look them up dynamically off this package for the same reason.
"""

from __future__ import annotations

# These re-exports must come first so submodules can pick them up via
# ``repositories.metagame_repository.<attr>`` during their own import.
from navigators.mtggoldfish import (  # noqa: F401
    fetch_deck_text,
    get_archetype_decks,
    get_archetypes,
)
from repositories.metagame_repository.date_utils import _parse_deck_date
from repositories.metagame_repository.repository import MetagameRepository
from utils.constants import REMOTE_SNAPSHOTS_ENABLED  # noqa: F401

_default_repository: MetagameRepository | None = None


def get_metagame_repository() -> MetagameRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = MetagameRepository()
    return _default_repository


def reset_metagame_repository() -> None:
    """Reset the global metagame repository (use in tests for isolation)."""
    global _default_repository
    _default_repository = None


__all__ = [
    "MetagameRepository",
    "_parse_deck_date",
    "fetch_deck_text",
    "get_archetype_decks",
    "get_archetypes",
    "get_metagame_repository",
    "reset_metagame_repository",
]
