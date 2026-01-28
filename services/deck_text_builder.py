"""Helpers for building deck text from card zones."""

from __future__ import annotations

from typing import Any


class DeckTextBuilder:
    """Construct deck list text from zone dictionaries."""

    def build_deck_text_from_zones(self, zone_cards: dict[str, list[dict[str, Any]]]) -> str:
        if not zone_cards.get("main") and not zone_cards.get("side"):
            return ""
        lines: list[str] = []
        for entry in zone_cards.get("main", []):
            lines.append(f"{entry['qty']} {entry['name']}")
        if zone_cards.get("side"):
            lines.append("")
            lines.append("Sideboard")
            for entry in zone_cards["side"]:
                lines.append(f"{entry['qty']} {entry['name']}")
        return "\n".join(lines).strip()

    def build_deck_text(self, zones: dict[str, list[dict[str, Any]]]) -> str:
        lines: list[str] = []

        for zone in ["Maindeck", "Deck", "Main"]:
            if zone in zones:
                for card in zones[zone]:
                    count = card.get("count", 1)
                    name = card.get("name", "")
                    if name:
                        lines.append(f"{count} {name}")
                break

        sideboard_found = False
        for zone in ["Sideboard", "Side"]:
            if zone in zones and zones[zone]:
                if not sideboard_found:
                    lines.append("")
                    sideboard_found = True
                for card in zones[zone]:
                    count = card.get("count", 1)
                    name = card.get("name", "")
                    if name:
                        lines.append(f"{count} {name}")
                break

        return "\n".join(lines)
