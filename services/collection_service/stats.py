"""Collection statistics aggregated from the current inventory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.collection_service.protocol import CollectionServiceProto

    _Base = CollectionServiceProto
else:
    _Base = object


class StatsMixin(_Base):
    """Summarize the loaded collection (rarity, counts, averages)."""

    def get_collection_statistics(self) -> dict[str, Any]:
        if not self._collection_loaded:
            return {
                "loaded": False,
                "message": "Collection not loaded",
            }

        total_cards = sum(self._collection.values())
        unique_cards = len(self._collection)

        rarity_counts: dict[str, int] = {}

        for card_name, count in self._collection.items():
            metadata = self.card_repo.get_card_metadata(card_name)
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
