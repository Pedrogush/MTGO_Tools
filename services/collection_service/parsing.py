"""Helpers for parsing and normalizing collection data."""

from __future__ import annotations

from typing import Any

from utils.card_names import fold_card_name


def build_inventory(cards: list[dict[str, Any]], normalize_names: bool = True) -> dict[str, int]:
    """Normalize a list of card entries into a name -> quantity mapping.

    Keys use :func:`utils.card_names.fold_card_name` — the same accent/
    punctuation folding the card index and image lookups key on — because the
    MTGO bridge reports the typographically correct name ("Kíli the
    Resourceful") while decklists routinely spell it in ASCII ("Kili the
    Resourceful"). Keying on ``name.lower()`` alone left those cards reported as
    unowned even with four copies in the collection.
    """
    inventory: dict[str, int] = {}
    for entry in cards:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if not name:
            continue
        try:
            quantity = int(entry.get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        if quantity == 0:
            continue
        key = (fold_card_name(name) or name.lower()) if normalize_names else name
        inventory[key] = inventory.get(key, 0) + quantity
    return inventory
