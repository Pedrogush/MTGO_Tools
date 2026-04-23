"""CollectionService composed from responsibility-specific mixins."""

from __future__ import annotations

from pathlib import Path

from repositories.card_repository import CardRepository, get_card_repository
from services.collection_service.bridge_refresh import BridgeRefreshMixin
from services.collection_service.cache import CollectionCacheMixin
from services.collection_service.deck_analysis import DeckAnalysisMixin
from services.collection_service.exporter import ExporterMixin
from services.collection_service.ownership import OwnershipMixin
from services.collection_service.stats import StatsMixin


class CollectionService(
    CollectionCacheMixin,
    OwnershipMixin,
    DeckAnalysisMixin,
    StatsMixin,
    BridgeRefreshMixin,
    ExporterMixin,
):
    """Service for collection/inventory management logic."""

    def __init__(self, card_repository: CardRepository | None = None):
        self.card_repo = card_repository or get_card_repository()
        self._collection: dict[str, int] = {}
        self._collection_path: Path | None = None
        self._collection_loaded = False
