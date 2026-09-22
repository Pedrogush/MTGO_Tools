"""Helpers for building deck text from card zones.

The format itself is :func:`utils.deck_text.render_deck_text`, shared with the
deck-VCS normalizer and the collection diff. What is here is the mapping from
the zone-editor's dictionaries onto it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.deck_text import render_deck_text

if TYPE_CHECKING:
    from services.deck_service.protocol import DeckServiceProto

    _Base = DeckServiceProto
else:
    _Base = object


class DeckTextBuilderMixin(_Base):
    """Construct deck list text from zone dictionaries."""

    def build_deck_text_from_zones(self, zone_cards: dict[str, list[dict[str, Any]]]) -> str:
        return render_deck_text(
            [(entry["qty"], entry["name"]) for entry in zone_cards.get("main", [])],
            [(entry["qty"], entry["name"]) for entry in zone_cards.get("side", [])],
        )

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


class DeckTextBuilder(DeckTextBuilderMixin):
    """Standalone text-builder for direct instantiation."""
