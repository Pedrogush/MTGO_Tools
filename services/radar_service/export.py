"""Decklist export and card-name extraction for :class:`RadarService`."""

from __future__ import annotations

from services.radar_service.models import RadarData
from utils.constants import RADAR_MIN_COPY_COUNT, RADAR_MIN_EXPECTED_COPIES_DEFAULT


class ExportMixin:
    """Render :class:`RadarData` as a decklist and project its card names."""

    def export_radar_as_decklist(
        self,
        radar: RadarData,
        min_expected_copies: float = RADAR_MIN_EXPECTED_COPIES_DEFAULT,
        max_cards: int | None = None,
    ) -> str:
        # Cards are included based on their average count, filtered by min_expected_copies.
        lines = []

        mainboard = [
            card for card in radar.mainboard_cards if card.expected_copies >= min_expected_copies
        ]
        if max_cards is not None:
            mainboard = mainboard[:max_cards]

        for card in mainboard:
            count = max(RADAR_MIN_COPY_COUNT, round(card.avg_copies))
            lines.append(f"{count} {card.card_name}")

        sideboard = [
            card for card in radar.sideboard_cards if card.expected_copies >= min_expected_copies
        ]
        if max_cards is not None:
            sideboard = sideboard[:max_cards]

        if sideboard:
            lines.append("")
            lines.append("Sideboard")
            for card in sideboard:
                count = max(RADAR_MIN_COPY_COUNT, round(card.avg_copies))
                lines.append(f"{count} {card.card_name}")

        return "\n".join(lines)

    def get_radar_card_names(self, radar: RadarData, zone: str = "both") -> set[str]:
        cards = set()

        if zone in ("mainboard", "both"):
            cards.update(card.card_name for card in radar.mainboard_cards)

        if zone in ("sideboard", "both"):
            cards.update(card.card_name for card in radar.sideboard_cards)

        return cards
