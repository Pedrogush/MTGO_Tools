"""Parsing and analysis helpers for deck text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class DeckEntry:
    count: float
    name: str
    is_sideboard: bool


class DeckParser:
    """Parse deck text into structured data for downstream services."""

    def deck_to_dictionary(self, deck_text: str) -> dict[str, float]:
        """
        Convert deck text to a dictionary representation.

        Args:
            deck_text: Deck list as text (format: "quantity card_name")

        Returns:
            Dictionary mapping card names to quantities (floats to preserve averages)
            Sideboard cards are prefixed with "Sideboard "
        """
        deck_dict: dict[str, float] = {}

        for entry in self._iter_entries(deck_text, strip_input=False, ignore_trailing_empty=True):
            key = f"Sideboard {entry.name}" if entry.is_sideboard else entry.name
            deck_dict[key] = deck_dict.get(key, 0.0) + entry.count

        return deck_dict

    def analyze_deck(self, deck_content: str) -> dict[str, Any]:
        """
        Analyze a deck and return statistics.

        Args:
            deck_content: Deck list as text

        Returns:
            Dictionary with keys:
                - mainboard_count: int
                - sideboard_count: int
                - total_cards: int
                - unique_mainboard: int
                - unique_sideboard: int
                - mainboard_cards: list of (card_name, count) tuples
                - sideboard_cards: list of (card_name, count) tuples
                - estimated_lands: int
        """
        mainboard_totals: dict[str, float] = {}
        sideboard_totals: dict[str, float] = {}
        mainboard_order: list[str] = []
        sideboard_order: list[str] = []

        for entry in self._iter_entries(deck_content, strip_input=True, ignore_trailing_empty=False):
            if entry.is_sideboard:
                target_totals = sideboard_totals
                target_order = sideboard_order
            else:
                target_totals = mainboard_totals
                target_order = mainboard_order

            if entry.name not in target_totals:
                target_order.append(entry.name)
            target_totals[entry.name] = target_totals.get(entry.name, 0.0) + entry.count

        mainboard = self._build_card_list(mainboard_order, mainboard_totals)
        sideboard = self._build_card_list(sideboard_order, sideboard_totals)

        mainboard_count = sum(count for _, count in mainboard)
        sideboard_count = sum(count for _, count in sideboard)

        land_keywords = ["mountain", "island", "swamp", "forest", "plains", "land", "wastes"]
        estimated_lands = sum(
            count
            for card, count in mainboard
            if any(keyword in card.lower() for keyword in land_keywords)
        )

        return {
            "mainboard_count": mainboard_count,
            "sideboard_count": sideboard_count,
            "total_cards": mainboard_count + sideboard_count,
            "unique_mainboard": len(mainboard),
            "unique_sideboard": len(sideboard),
            "mainboard_cards": mainboard,
            "sideboard_cards": sideboard,
            "estimated_lands": estimated_lands,
        }

    def _iter_entries(
        self, deck_text: str, *, strip_input: bool, ignore_trailing_empty: bool
    ) -> Iterable[DeckEntry]:
        lines = deck_text.strip().split("\n") if strip_input else deck_text.split("\n")
        is_sideboard = False

        for index, line in enumerate(lines):
            line = line.strip()

            if not line and ignore_trailing_empty and index == len(lines) - 1:
                continue

            if not line:
                is_sideboard = True
                continue

            if line.lower() == "sideboard":
                is_sideboard = True
                continue

            try:
                parts = line.split(" ", 1)
                if len(parts) < 2:
                    continue

                card_amount = float(parts[0])
                card_name = parts[1].strip()

                yield DeckEntry(count=card_amount, name=card_name, is_sideboard=is_sideboard)
            except (ValueError, IndexError):
                continue

    @staticmethod
    def _build_card_list(
        order: list[str], totals: dict[str, float]
    ) -> list[tuple[str, int | float]]:
        cards: list[tuple[str, int | float]] = []
        for card in order:
            total = totals[card]
            cards.append((card, int(total) if float(total).is_integer() else total))
        return cards
