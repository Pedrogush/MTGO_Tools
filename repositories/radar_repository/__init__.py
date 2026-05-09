"""Radar Repository package — locally cached precomputed radar snapshots.

Split by responsibility into internal modules:

- ``models``: :class:`StoredRadar`, :class:`StoredRadarCard`, and
  :class:`CardAggregateStats` dataclasses
- ``schema``: SQLite connection helper and DDL bootstrap
- ``writes``: bulk and per-archetype snapshot replacement
- ``reads``: snapshot lookup and reconstruction
- ``repository``: :class:`RadarRepository` composed from the above
"""

from __future__ import annotations

from repositories.radar_repository.models import (
    CardAggregateStats,
    StoredRadar,
    StoredRadarCard,
)
from repositories.radar_repository.repository import RadarRepository

_default_repository: RadarRepository | None = None


def get_radar_repository() -> RadarRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = RadarRepository()
    return _default_repository


def reset_radar_repository() -> None:
    global _default_repository
    _default_repository = None


__all__ = [
    "CardAggregateStats",
    "RadarRepository",
    "StoredRadar",
    "StoredRadarCard",
    "get_radar_repository",
    "reset_radar_repository",
]
