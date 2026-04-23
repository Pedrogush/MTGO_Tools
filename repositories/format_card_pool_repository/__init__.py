"""Format Card Pool Repository package — locally cached format card-pool snapshots.

Split by responsibility into internal modules:

- ``models``: :class:`FormatCardPoolSummary` and :class:`FormatCardPoolCardTotal`
  dataclasses returned by repository reads
- ``schema``: SQLite connection helper and DDL bootstrap
- ``writes``: bulk and per-format snapshot replacement
- ``reads``: lookup, listing, and summary queries
- ``repository``: :class:`FormatCardPoolRepository` composed from the above
"""

from __future__ import annotations

from repositories.format_card_pool_repository.models import (
    FormatCardPoolCardTotal,
    FormatCardPoolSummary,
)
from repositories.format_card_pool_repository.repository import FormatCardPoolRepository

_default_repository: FormatCardPoolRepository | None = None


def get_format_card_pool_repository() -> FormatCardPoolRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = FormatCardPoolRepository()
    return _default_repository


def reset_format_card_pool_repository() -> None:
    global _default_repository
    _default_repository = None


__all__ = [
    "FormatCardPoolCardTotal",
    "FormatCardPoolRepository",
    "FormatCardPoolSummary",
    "get_format_card_pool_repository",
    "reset_format_card_pool_repository",
]
