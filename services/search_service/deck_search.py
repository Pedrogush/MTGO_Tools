"""Deck-text search and card type grouping helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.search_service.protocol import SearchServiceProto

    _Base = SearchServiceProto
else:
    _Base = object


class DeckSearchMixin(_Base):
    """Search within a rendered deck text and group cards by type line."""

    def find_cards_in_deck(self, deck_text: str, search_term: str) -> list[tuple[str, int]]:
        results = []
        search_lower = search_term.lower()

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

                if search_lower in card_name.lower():
                    results.append((card_name, count))

            except (ValueError, IndexError):
                continue

        return results

    def group_cards_by_type(self, cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = {
            "Creature": [],
            "Instant": [],
            "Sorcery": [],
            "Enchantment": [],
            "Artifact": [],
            "Planeswalker": [],
            "Land": [],
            "Other": [],
        }

        for card in cards:
            type_line = card.get("type_line", "") or card.get("type", "")
            type_line_lower = type_line.lower()

            assigned = False
            for card_type in groups.keys():
                if card_type.lower() in type_line_lower:
                    groups[card_type].append(card)
                    assigned = True
                    break

            if not assigned:
                groups["Other"].append(card)

        return {k: v for k, v in groups.items() if v}
