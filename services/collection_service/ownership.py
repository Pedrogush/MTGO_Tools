"""Ownership queries and display-formatting for collection inventories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.card_names import fold_card_name

if TYPE_CHECKING:
    from services.collection_service.protocol import CollectionServiceProto

    _Base = CollectionServiceProto
else:
    _Base = object


def format_owned_status(owned: int, required: int) -> tuple[str, tuple[int, int, int]]:
    """Return a display label and RGB color for owned vs required counts."""
    if owned >= required:
        return (f"Owned {owned}/{required}", (120, 200, 120))
    if owned > 0:
        return (f"Owned {owned}/{required}", (230, 200, 90))
    return (f"Owned 0/{required}", (230, 120, 120))


class OwnershipMixin(_Base):
    """Ownership lookup and formatting on top of the collection state."""

    def owns_card(self, card_name: str, required_count: int = 1) -> bool:
        owned = self.get_owned_count(card_name)
        return owned >= required_count

    def get_owned_count(self, card_name: str) -> int:
        # Inventories from the canonical load paths are normalized with
        # fold_card_name (see parsing.build_inventory), but legacy cached files
        # and hand-built inventories may still contain title-cased or accented
        # keys. Probe every form so ownership is never underreported regardless
        # of how the inventory was built (#469).
        if card_name in self._collection:
            return self._collection[card_name]
        lowered = card_name.lower()
        if lowered in self._collection:
            return self._collection[lowered]
        # The bridge reports "Kíli the Resourceful" while decklists spell it
        # "Kili the Resourceful"; fold both sides with the same helper the card
        # index uses so the two spellings meet.
        folded = fold_card_name(card_name)
        if folded and folded in self._collection:
            return self._collection[folded]
        # Fall back to a scan for legacy mixed-case / unfolded keys.
        for key, value in self._collection.items():
            if key.lower() == lowered or (folded and fold_card_name(key) == folded):
                return value
        return 0

    def get_owned_status(self, name: str, required: int) -> tuple[str, tuple[int, int, int]]:
        if not self.get_inventory():
            return ("Owned —", (185, 191, 202))  # Subdued text color
        have = self.get_owned_count(name)
        return format_owned_status(have, required)

    def get_ownership_status(
        self, card_name: str, required: int
    ) -> tuple[str, tuple[int, int, int]]:
        owned = self.get_owned_count(card_name)
        return format_owned_status(owned, required)
