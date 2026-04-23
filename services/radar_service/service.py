"""RadarService composed from responsibility-specific mixins."""

from __future__ import annotations

from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from repositories.radar_repository import RadarRepository, get_radar_repository
from services.deck_service import DeckService, get_deck_service
from services.radar_service.analysis import AnalysisMixin
from services.radar_service.export import ExportMixin
from services.radar_service.precomputed import PrecomputedMixin


class RadarService(
    PrecomputedMixin,
    AnalysisMixin,
    ExportMixin,
):
    """Service for calculating archetype radar (card frequency analysis)."""

    def __init__(
        self,
        metagame_repository: MetagameRepository | None = None,
        deck_service: DeckService | None = None,
        radar_repository: RadarRepository | None = None,
    ):
        self.metagame_repo = metagame_repository or get_metagame_repository()
        self.deck_service = deck_service or get_deck_service()
        self.radar_repo = radar_repository or get_radar_repository()
