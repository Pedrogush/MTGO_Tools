"""Thin service wrapping :class:`MetagameRepository` for widget consumption.

Widgets should not import :mod:`repositories.metagame_repository` directly —
the controller/service layer owns repository access. This module exposes the
small surface that the opponent-tracker, the manual-archetype-load dialog,
the metagame-analysis viewer, and :class:`AppController` need
(``get_archetypes_for_format`` and ``get_stats_for_format``), routing both
through a single :class:`MetagameService` instance backed by the default
repository.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from repositories.metagame_repository import MetagameRepository, get_metagame_repository


class MetagameService:
    """Service exposing read-only metagame queries to the UI layer."""

    def __init__(self, metagame_repository: MetagameRepository | None = None) -> None:
        self.metagame_repo: MetagameRepository = metagame_repository or get_metagame_repository()

    def get_archetypes_for_format(
        self,
        mtg_format: str,
        force_refresh: bool = False,
        on_background_refresh: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the archetype list for ``mtg_format`` via the underlying repository.

        ``force_refresh`` and ``on_background_refresh`` are forwarded to the
        repository so callers (notably :class:`AppController`) can opt into
        stale-while-revalidate behavior without reaching into the repository
        layer directly.
        """
        return self.metagame_repo.get_archetypes_for_format(
            mtg_format,
            force_refresh=force_refresh,
            on_background_refresh=on_background_refresh,
        )

    def get_stats_for_format(self, mtg_format: str) -> dict[str, Any]:
        """Return per-archetype stats for ``mtg_format`` via the underlying repository."""
        return self.metagame_repo.get_stats_for_format(mtg_format)


_default_service: MetagameService | None = None


def get_metagame_service() -> MetagameService:
    """Return the shared :class:`MetagameService` instance."""
    global _default_service
    if _default_service is None:
        _default_service = MetagameService()
    return _default_service


def reset_metagame_service() -> None:
    """Reset the global metagame service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "MetagameService",
    "get_metagame_service",
    "reset_metagame_service",
]
