"""Helpers for parsing and normalizing collection data."""

from __future__ import annotations

from typing import Any


def build_inventory(cards: list[dict[str, Any]]) -> dict[str, int]:
    """Normalize a list of card entries into a name -> quantity mapping."""
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
        key = name.lower()
        inventory[key] = inventory.get(key, 0) + quantity
    return inventory
