"""Deck rendering utilities for UI display."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from widgets.panels.card_table_panel import CardTablePanel


class DeckRenderer:
    """Renders deck data into card table panels."""

    def __init__(
        self,
        main_table: "CardTablePanel",
        side_table: "CardTablePanel",
        out_table: "CardTablePanel | None" = None,
    ):
        self.main_table = main_table
        self.side_table = side_table
        self.out_table = out_table

    def render_zones(self, zone_cards: dict[str, list[dict[str, Any]]]) -> None:
        """Render all zones from zone_cards dictionary."""
        self.main_table.set_cards(zone_cards.get("main", []))
        self.side_table.set_cards(zone_cards.get("side", []))
        if self.out_table:
            self.out_table.set_cards(zone_cards.get("out", []))

    def clear_all_zones(self) -> None:
        """Clear all zone displays."""
        self.main_table.set_cards([])
        self.side_table.set_cards([])
        if self.out_table:
            self.out_table.set_cards([])

    def has_deck_loaded(self, zone_cards: dict[str, list[dict[str, Any]]]) -> bool:
        """Check if any cards are loaded in main or side."""
        return bool(zone_cards.get("main") or zone_cards.get("side"))
