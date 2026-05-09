"""Cross-archetype card-usage aggregation for :class:`RadarService`.

Surfaces the same primitives the Card panel's Stats tab consumes per archetype,
but rolled up across every archetype radar in a format. Used by the Top Cards
widget so users can compare not just raw copy totals but also how widely a card
spreads across archetypes and the four (Karsten/arithmetic × mb/sb) format-wide
average copies it averages out to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from repositories.radar_repository import CardAggregateStats

if TYPE_CHECKING:
    from services.radar_service.protocol import RadarServiceProto

    _Base = RadarServiceProto
else:
    _Base = object


@dataclass(frozen=True)
class CardUsageStats:
    """Format-wide rollup of a card's usage from cached radar snapshots."""

    card_name: str
    format_name: str
    total_decks: int  # Decks across every archetype radar in the format
    mainboard_archetypes: int
    sideboard_archetypes: int
    mainboard_copies: int
    sideboard_copies: int
    mainboard_decks_present: int  # Decks running the card mainboard
    sideboard_decks_present: int  # Decks running the card sideboard

    @property
    def mainboard_avg_karsten(self) -> float | None:
        """Avg copies in mainboard among decks that include it (Karsten)."""
        if self.mainboard_decks_present <= 0:
            return None
        return self.mainboard_copies / self.mainboard_decks_present

    @property
    def sideboard_avg_karsten(self) -> float | None:
        if self.sideboard_decks_present <= 0:
            return None
        return self.sideboard_copies / self.sideboard_decks_present

    @property
    def mainboard_avg_arithmetic(self) -> float | None:
        """Avg copies in mainboard across every deck in the format."""
        if self.total_decks <= 0:
            return None
        return self.mainboard_copies / self.total_decks

    @property
    def sideboard_avg_arithmetic(self) -> float | None:
        if self.total_decks <= 0:
            return None
        return self.sideboard_copies / self.total_decks


class CardStatsMixin(_Base):
    """Cross-archetype usage stats and effective legality lookups."""

    def get_card_usage_stats(
        self, format_name: str, card_names: list[str]
    ) -> dict[str, CardUsageStats]:
        """Bulk usage rollup for the given cards in one format."""
        names = [str(name).strip() for name in card_names if str(name).strip()]
        if not names:
            return {}
        aggregates = self.radar_repo.get_card_aggregates(format_name, names)
        total_decks = self.radar_repo.get_total_decks(format_name)
        return {
            name: _to_usage(aggregates.get(name), name, format_name, total_decks) for name in names
        }

    def get_effective_legalities(self, card_names: list[str]) -> dict[str, list[str]]:
        """For each card, the formats whose cached radars actually include it."""
        names = [str(name).strip() for name in card_names if str(name).strip()]
        if not names:
            return {}
        return self.radar_repo.get_formats_for_cards(names)


def _to_usage(
    agg: CardAggregateStats | None,
    name: str,
    format_name: str,
    total_decks: int,
) -> CardUsageStats:
    if agg is None:
        return CardUsageStats(
            card_name=name,
            format_name=format_name.strip().lower(),
            total_decks=total_decks,
            mainboard_archetypes=0,
            sideboard_archetypes=0,
            mainboard_copies=0,
            sideboard_copies=0,
            mainboard_decks_present=0,
            sideboard_decks_present=0,
        )
    return CardUsageStats(
        card_name=name,
        format_name=agg.format_name,
        total_decks=total_decks,
        mainboard_archetypes=agg.mainboard_archetypes,
        sideboard_archetypes=agg.sideboard_archetypes,
        mainboard_copies=agg.mainboard_copies,
        sideboard_copies=agg.sideboard_copies,
        mainboard_decks_present=agg.mainboard_appearances,
        sideboard_decks_present=agg.sideboard_appearances,
    )
