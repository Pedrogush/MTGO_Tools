"""Shared ``self`` contract that the :class:`RadarService` mixins assume."""

from __future__ import annotations

from typing import Protocol

from repositories.metagame_repository import MetagameRepository
from repositories.radar_repository import RadarRepository
from services.deck_service import DeckService
from services.radar_service.models import RadarData


class RadarServiceProto(Protocol):
    """Cross-mixin ``self`` surface for ``RadarService``."""

    metagame_repo: MetagameRepository
    deck_service: DeckService
    radar_repo: RadarRepository

    def _get_precomputed_radar(
        self,
        format_name: str,
        archetype_href: str,
        *,
        max_decks: int | None,
    ) -> RadarData | None: ...
