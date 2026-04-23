"""Radar Service package — archetype card-frequency analysis.

Split by responsibility into internal modules:

- ``models``: :class:`CardFrequency` and :class:`RadarData` dataclasses
- ``precomputed``: precomputed-snapshot resolution from :class:`RadarRepository`
- ``analysis``: live deck-fetch + per-card frequency calculation
- ``export``: decklist export and card-name extraction helpers
- ``service``: :class:`RadarService` composed from the above mixins
"""

from __future__ import annotations

from services.radar_service.models import CardFrequency, RadarData
from services.radar_service.service import RadarService

_default_service: RadarService | None = None


def get_radar_service() -> RadarService:
    """Get the default radar service instance."""
    global _default_service
    if _default_service is None:
        _default_service = RadarService()
    return _default_service


def reset_radar_service() -> None:
    """Reset the global radar service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "CardFrequency",
    "RadarData",
    "RadarService",
    "get_radar_service",
    "reset_radar_service",
]
