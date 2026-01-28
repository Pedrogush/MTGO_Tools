"""Collection statistics helpers."""

from __future__ import annotations

from typing import Any

from repositories.card_repository import CardRepository


def get_collection_statistics(
    inventory: dict[str, int],
    card_repo: CardRepository,
    is_loaded: bool,
) -> dict[str, Any]:
    """Return statistics about a collection inventory."""
    if not is_loaded:
        return {
            "loaded": False,
            "message": "Collection not loaded",
        }

    total_cards = sum(inventory.values())
    unique_cards = len(inventory)

    rarity_counts: dict[str, int] = {}

    for card_name, count in inventory.items():
        metadata = card_repo.get_card_metadata(card_name)
        if metadata:
            rarity = metadata.get("rarity", "unknown")
            rarity_counts[rarity] = rarity_counts.get(rarity, 0) + count

    return {
        "loaded": True,
        "unique_cards": unique_cards,
        "total_cards": total_cards,
        "average_copies": total_cards / unique_cards if unique_cards > 0 else 0,
        "rarity_distribution": rarity_counts,
    }
