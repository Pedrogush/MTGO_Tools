"""Deck analysis based on collection ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.collection_service.protocol import CollectionServiceProto

    _Base = CollectionServiceProto
else:
    _Base = object


class DeckAnalysisMixin(_Base):
    """Compare deck requirements against owned inventory."""

    def analyze_deck_ownership(self, deck_text: str) -> dict[str, Any]:
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
            owned = self.get_owned_count(card_name)

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

    def get_missing_cards_list(self, deck_text: str) -> list[tuple[str, int]]:
        analysis = self.analyze_deck_ownership(deck_text)
        missing: list[tuple[str, int]] = []

        for card_name, owned, needed in analysis["missing_cards"]:
            missing_count = needed - owned
            if missing_count > 0:
                missing.append((card_name, missing_count))

        return missing
