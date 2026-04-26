"""Precomputed-snapshot resolution for :class:`RadarService`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repositories.radar_repository import StoredRadar
from services.radar_service.models import CardFrequency, RadarData

if TYPE_CHECKING:
    from services.radar_service.protocol import RadarServiceProto

    _Base = RadarServiceProto
else:
    _Base = object


class PrecomputedMixin(_Base):
    """Look up cached radar snapshots and convert them into :class:`RadarData`."""

    def _get_precomputed_radar(
        self,
        format_name: str,
        archetype_href: str,
        *,
        max_decks: int | None,
    ) -> RadarData | None:
        if not archetype_href:
            return None
        snapshot = self.radar_repo.get_radar(format_name, archetype_href)
        if snapshot is None:
            return None
        if not snapshot.mainboard_cards and not snapshot.sideboard_cards:
            return None
        if max_decks is not None and snapshot.total_decks_analyzed > max_decks:
            return None
        return self._snapshot_to_radar_data(snapshot)

    def _snapshot_to_radar_data(self, snapshot: StoredRadar) -> RadarData:
        return RadarData(
            archetype_name=snapshot.archetype_name,
            format_name=snapshot.format_name.title(),
            mainboard_cards=[
                CardFrequency(
                    card_name=card.card_name,
                    appearances=card.appearances,
                    total_copies=card.total_copies,
                    max_copies=card.max_copies,
                    avg_copies=card.avg_copies,
                    inclusion_rate=card.inclusion_rate,
                    expected_copies=card.expected_copies,
                    copy_distribution=card.copy_distribution,
                )
                for card in snapshot.mainboard_cards
            ],
            sideboard_cards=[
                CardFrequency(
                    card_name=card.card_name,
                    appearances=card.appearances,
                    total_copies=card.total_copies,
                    max_copies=card.max_copies,
                    avg_copies=card.avg_copies,
                    inclusion_rate=card.inclusion_rate,
                    expected_copies=card.expected_copies,
                    copy_distribution=card.copy_distribution,
                )
                for card in snapshot.sideboard_cards
            ],
            total_decks_analyzed=snapshot.total_decks_analyzed,
            decks_failed=snapshot.decks_failed,
        )
