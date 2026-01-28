"""Deck analysis helpers based on collection ownership."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def analyze_deck_ownership(
    deck_text: str,
    owned_count_lookup: Callable[[str], int],
) -> dict[str, Any]:
    """Analyze what cards from a deck are owned."""
    card_requirements: dict[str, int] = {}

    for line in deck_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        try:
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue

            count = int(float(parts[0]))
            card_name = parts[1].strip()

            if card_name.startswith("Sideboard "):
                card_name = card_name[10:]

            card_requirements[card_name] = card_requirements.get(card_name, 0) + count
        except (ValueError, IndexError):
            continue

    fully_owned = 0
    partially_owned = 0
    not_owned = 0
    missing_cards: list[tuple[str, int, int]] = []

    for card_name, needed in card_requirements.items():
        owned = owned_count_lookup(card_name)

        if owned >= needed:
            fully_owned += 1
        elif owned > 0:
            partially_owned += 1
            missing_cards.append((card_name, owned, needed))
        else:
            not_owned += 1
            missing_cards.append((card_name, 0, needed))

    total_unique = len(card_requirements)
    ownership_percentage = (fully_owned / total_unique * 100) if total_unique > 0 else 0.0

    return {
        "total_unique": total_unique,
        "fully_owned": fully_owned,
        "partially_owned": partially_owned,
        "not_owned": not_owned,
        "missing_cards": missing_cards,
        "ownership_percentage": ownership_percentage,
    }


def get_missing_cards_list(
    deck_text: str,
    owned_count_lookup: Callable[[str], int],
) -> list[tuple[str, int]]:
    """Get a list of missing cards for a deck."""
    analysis = analyze_deck_ownership(deck_text, owned_count_lookup)
    missing: list[tuple[str, int]] = []

    for card_name, owned, needed in analysis["missing_cards"]:
        missing_count = needed - owned
        if missing_count > 0:
            missing.append((card_name, missing_count))

    return missing
