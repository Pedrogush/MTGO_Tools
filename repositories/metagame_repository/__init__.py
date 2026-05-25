"""Metagame Repository package — data access for archetype and deck metadata.

Split by responsibility into internal modules:

- ``date_utils``: :func:`_parse_deck_date` date-format helper
- ``cache``: archetype-list / archetype-decks JSON cache I/O and filters
- ``archetype_resolution``: format → archetype list / stats resolution with
  cache → remote snapshot → live-scrape fallback order
- ``deck_operations``: deck-list fetching, aggregated listings, and downloads
- ``background``: stale-while-revalidate background refresh helper
- ``repository``: :class:`MetagameRepository` composed from the above mixins

``get_archetypes``, ``get_archetype_decks``, ``fetch_deck_text``,
``get_archetype_stats``, ``get_remote_snapshot_client``, and
``REMOTE_SNAPSHOTS_ENABLED`` are exposed as attributes on this package so tests
can monkeypatch them through the package namespace exactly as they did when
this was a flat module, and submodules can look them up dynamically off this
package for the same reason. The names sourced from ``services.*`` are
resolved lazily via :pep:`562` ``__getattr__`` to keep the AST-visible import
graph free of ``repositories → services`` back-edges; the actual import only
happens on first access.
"""

from __future__ import annotations

from typing import Any

from repositories.metagame_repository.date_utils import _parse_deck_date
from repositories.metagame_repository.repository import MetagameRepository
from utils.constants import REMOTE_SNAPSHOTS_ENABLED  # noqa: F401

_default_repository: MetagameRepository | None = None

# Names re-exported lazily from ``services.*``. Lookup happens on first
# attribute access (see ``__getattr__`` below); after that the resolved value
# is cached on this module's globals so subsequent accesses are regular
# attribute lookups and ``monkeypatch.setattr`` keeps working.
_LAZY_SERVICE_IMPORTS: dict[str, str] = {
    "fetch_deck_text": "services.scrapers.mtggoldfish",
    "get_archetype_decks": "services.scrapers.mtggoldfish",
    "get_archetype_stats": "services.scrapers.mtggoldfish",
    "get_archetypes": "services.scrapers.mtggoldfish",
    "get_remote_snapshot_client": "services.remote_snapshot_client",
}


def __getattr__(name: str) -> Any:
    source = _LAZY_SERVICE_IMPORTS.get(name)
    if source is not None:
        import importlib

        module = importlib.import_module(source)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
