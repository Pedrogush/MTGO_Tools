"""Parsing and analysis helpers for deck text.

The line scanning itself lives in :mod:`utils.deck_text`, which is what the
deck-VCS normalizer and the collection diff read through as well, so a decklist
is read identically wherever it enters the app. What is here is the *analysis*
shaped on top of it: zone totals in deck order, the dictionary form the builder
keys on, and the land estimate.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from utils.deck_text import DeckEntry, iter_entries

__all__ = ["DeckEntry", "DeckParser", "DeckParserMixin"]


class DeckParserMixin:
    """Parse deck text into structured data for downstream services."""

    def deck_to_dictionary(self, deck_text: str) -> dict[str, float]:
        # Sideboard cards are keyed as "Sideboard {name}".
        deck_dict: dict[str, float] = {}

        for entry in iter_entries(deck_text):
            key = f"Sideboard {entry.name}" if entry.is_sideboard else entry.name
            deck_dict[key] = deck_dict.get(key, 0.0) + entry.count

        return deck_dict

    def analyze_deck(self, deck_content: str) -> dict[str, Any]:
        mainboard_totals: dict[str, float] = {}
        sideboard_totals: dict[str, float] = {}
        mainboard_order: list[str] = []
        sideboard_order: list[str] = []

        for entry in iter_entries(deck_content):
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

    def iter_deck_entries(
        self, deck_text: str, *, strip_printing_id: bool = True
    ) -> Iterable[DeckEntry]:
        """Yield every parsed line of *deck_text* in deck order, tagged by zone.

        The public view of the parse that :meth:`analyze_deck` and
        :meth:`deck_to_dictionary` build on, for callers that need the entries
        themselves rather than an aggregate (the collection diff, #1044).

        *strip_printing_id* is passed through: analysis wants bare card names,
        while anything that will write the line back out has to keep the art the
        user picked.
        """
        return iter_entries(deck_text, strip_printing_id=strip_printing_id)

    @staticmethod
    def _build_card_list(
        order: list[str], totals: dict[str, float]
    ) -> list[tuple[str, int | float]]:
        cards: list[tuple[str, int | float]] = []
        for card in order:
            total = totals[card]
            cards.append((card, int(total) if float(total).is_integer() else total))
        return cards


class DeckParser(DeckParserMixin):
    """Standalone parser for direct instantiation (tests, ad-hoc usage)."""
