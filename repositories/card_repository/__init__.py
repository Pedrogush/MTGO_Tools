"""Card Repository package — data access for card metadata and collections.

Split by responsibility into internal modules:

- ``metadata``: card lookup and search backed by :class:`CardDataManager`
- ``collection``: collection-file I/O (msgspec decoding, normalization)
- ``state``: in-memory card-data loading/ready flags for the UI layer
- ``repository``: :class:`CardRepository` composed from the above mixins

``CardDataManager`` and ``load_card_manager`` are exposed lazily via :pep:`562`
``__getattr__`` so the only ``services.card_data_service`` references in this
package live in ``TYPE_CHECKING`` blocks, keeping the AST-visible import graph
free of ``repositories → services`` back-edges. The actual import is deferred
until first attribute access (which is also the first time the repository
needs to build a card-data manager).
"""

from __future__ import annotations

from typing import Any

from repositories.card_repository.repository import CardRepository

_default_repository: CardRepository | None = None

# Names re-exported lazily from ``services.card_data_service``. Lookup happens
# on first attribute access (see ``__getattr__`` below); after that the
# resolved value is cached on this module's globals so subsequent accesses are
# regular attribute lookups.
_LAZY_SERVICE_IMPORTS: dict[str, str] = {
    "CardDataManager": "services.card_data_service",
    "load_card_manager": "services.card_data_service",
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
