"""Ownership queries and display-formatting for collection inventories."""

from __future__ import annotations


def format_owned_status(owned: int, required: int) -> tuple[str, tuple[int, int, int]]:
    """Return a display label and RGB color for owned vs required counts."""
    if owned >= required:
        return (f"Owned {owned}/{required}", (120, 200, 120))
    if owned > 0:
        return (f"Owned {owned}/{required}", (230, 200, 90))
    return (f"Owned 0/{required}", (230, 120, 120))


class OwnershipMixin:
    """Ownership lookup and formatting on top of the collection state."""

    def owns_card(self, card_name: str, required_count: int = 1) -> bool:
        owned = self.get_owned_count(card_name)
        return owned >= required_count

    def get_owned_count(self, card_name: str) -> int:
        if card_name in self._collection:
            return self._collection[card_name]
        return self._collection.get(card_name.lower(), 0)

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
