"""Live deck-fetch and per-card frequency calculation for :class:`RadarService`."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.radar_service.models import CardFrequency, RadarData
from utils.constants import (
    RADAR_AVG_COPIES_ROUND_DIGITS,
    RADAR_EXPECTED_COPIES_ROUND_DIGITS,
    RADAR_INCLUSION_RATE_ROUND_DIGITS,
)

if TYPE_CHECKING:
    from services.radar_service.protocol import RadarServiceProto

    _Base = RadarServiceProto
else:
    _Base = object


class AnalysisMixin(_Base):
    """Compute card-frequency statistics for an archetype's deck pool."""

    def calculate_radar(
        self,
        archetype: dict[str, Any],
        format_name: str,
        max_decks: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> RadarData:
        archetype_name = archetype.get("name", "Unknown")
        logger.info(f"Calculating radar for {archetype_name} in {format_name}")

        archetype_href = str(archetype.get("href") or archetype.get("url", "")).strip()
        precomputed = self._get_precomputed_radar(format_name, archetype_href, max_decks=max_decks)
        if precomputed is not None:
            logger.info(f"Using precomputed radar for {archetype_name} in {format_name}")
            return precomputed

        try:
            decks = self.metagame_repo.get_decks_for_archetype(archetype)

            if not decks:
                logger.warning(f"No decks found for {archetype_name}")
                return RadarData(
                    archetype_name=archetype_name,
                    format_name=format_name,
                    mainboard_cards=[],
                    sideboard_cards=[],
                    total_decks_analyzed=0,
                    decks_failed=0,
                )

            if max_decks is not None:
                decks = decks[:max_decks]

            mainboard_stats: dict[str, list[int]] = defaultdict(list)
            sideboard_stats: dict[str, list[int]] = defaultdict(list)
            successful_decks = 0
            failed_decks = 0

            for i, deck in enumerate(decks):
                deck_name = deck.get("name", f"Deck {i+1}")

                if progress_callback:
                    progress_callback(i + 1, len(decks), deck_name)

                try:
                    deck_content = self.metagame_repo.download_deck_content(deck)
                    analysis = self.deck_service.analyze_deck(deck_content)

                    for card_name, count in analysis["mainboard_cards"]:
                        count_int = int(count) if isinstance(count, float) else count
                        mainboard_stats[card_name].append(count_int)

                    for card_name, count in analysis["sideboard_cards"]:
                        count_int = int(count) if isinstance(count, float) else count
                        sideboard_stats[card_name].append(count_int)

                    successful_decks += 1

                except Exception as exc:
                    logger.warning(f"Failed to analyze deck {deck_name}: {exc}")
                    failed_decks += 1
                    continue

            if successful_decks == 0:
                logger.error(f"Failed to analyze any decks for {archetype_name}")
                return RadarData(
                    archetype_name=archetype_name,
                    format_name=format_name,
                    mainboard_cards=[],
                    sideboard_cards=[],
                    total_decks_analyzed=0,
                    decks_failed=failed_decks,
                )

            mainboard_frequencies = self._calculate_frequencies(mainboard_stats, successful_decks)
            sideboard_frequencies = self._calculate_frequencies(sideboard_stats, successful_decks)

            mainboard_frequencies.sort(
                key=lambda x: (x.expected_copies, x.inclusion_rate), reverse=True
            )
            sideboard_frequencies.sort(
                key=lambda x: (x.expected_copies, x.inclusion_rate), reverse=True
            )

            logger.info(
                f"Radar calculated: {len(mainboard_frequencies)} mainboard cards, "
                f"{len(sideboard_frequencies)} sideboard cards from {successful_decks} decks"
            )

            return RadarData(
                archetype_name=archetype_name,
                format_name=format_name,
                mainboard_cards=mainboard_frequencies,
                sideboard_cards=sideboard_frequencies,
                total_decks_analyzed=successful_decks,
                decks_failed=failed_decks,
            )

        except Exception as exc:
            logger.error(f"Failed to calculate radar for {archetype_name}: {exc}")
            raise

    def _calculate_frequencies(
        self, card_stats: dict[str, list[int]], total_decks: int
    ) -> list[CardFrequency]:
        frequencies = []

        for card_name, counts in card_stats.items():
            appearances = len(counts)
            total_copies = sum(counts)
            max_copies = max(counts)
            avg_copies = total_copies / appearances if appearances > 0 else 0

            inclusion_rate = (appearances / total_decks) * 100 if total_decks > 0 else 0
            expected_copies = total_copies / total_decks if total_decks > 0 else 0

            copy_distribution: dict[int, int] = defaultdict(int)
            for count in counts:
                copy_distribution[count] += 1
            zero_count = max(total_decks - appearances, 0)
            if zero_count:
                copy_distribution[0] += zero_count

            frequencies.append(
                CardFrequency(
                    card_name=card_name,
                    appearances=appearances,
                    total_copies=total_copies,
                    max_copies=max_copies,
                    avg_copies=round(avg_copies, RADAR_AVG_COPIES_ROUND_DIGITS),
                    inclusion_rate=round(inclusion_rate, RADAR_INCLUSION_RATE_ROUND_DIGITS),
                    expected_copies=round(expected_copies, RADAR_EXPECTED_COPIES_ROUND_DIGITS),
                    copy_distribution=dict(sorted(copy_distribution.items(), reverse=True)),
                )
            )

        return frequencies
