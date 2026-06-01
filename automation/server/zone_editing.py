"""Zone-editing command handlers: load deck text, add/subtract cards, scroll."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class ZoneEditingMixin(_Base):
    """Mainboard/sideboard/out zone editing and inspection commands."""

    def _handle_load_deck_text(self, deck_text: str) -> dict[str, Any]:
        """Load a deck from text into the mainboard/sideboard zones."""
        if not hasattr(self.frame, "_on_deck_content_ready"):
            return {"loaded": False, "error": "Frame does not support _on_deck_content_ready"}
        self.frame._on_deck_content_ready(deck_text, source="automation")
        zone_cards = getattr(self.frame, "zone_cards", {})
        return {
            "loaded": True,
            "mainboard_count": sum(c["qty"] for c in zone_cards.get("main", [])),
            "sideboard_count": sum(c["qty"] for c in zone_cards.get("side", [])),
        }

    def _handle_get_zone_cards(self, zone: str = "main") -> dict[str, Any]:
        """Get the cards in a zone (main, side, or out)."""
        zone_cards = getattr(self.frame, "zone_cards", {})
        cards = zone_cards.get(zone, [])
        return {
            "zone": zone,
            "cards": [{"name": c["name"], "qty": c["qty"]} for c in cards],
            "total_qty": sum(c["qty"] for c in cards),
            "unique_cards": len(cards),
        }

    def _handle_add_card_to_zone(self, zone: str, card_name: str, qty: int = 1) -> dict[str, Any]:
        """Add a card to a zone by directly calling the zone delta handler."""
        if not hasattr(self.frame, "_handle_zone_delta"):
            return {"added": False, "error": "Frame does not support _handle_zone_delta"}
        self.frame._handle_zone_delta(zone, card_name, qty)
        zone_cards = getattr(self.frame, "zone_cards", {})
        cards = zone_cards.get(zone, [])
        card_entry = next((c for c in cards if c["name"].lower() == card_name.lower()), None)
        return {
            "added": True,
            "zone": zone,
            "card_name": card_name,
            "new_qty": card_entry["qty"] if card_entry else 0,
            "total_qty": sum(c["qty"] for c in cards),
        }

    def _handle_subtract_card_from_zone(
        self, zone: str, card_name: str, qty: int = 1
    ) -> dict[str, Any]:
        """Subtract (decrement) a card from a zone."""
        if not hasattr(self.frame, "_handle_zone_delta"):
            return {"subtracted": False, "error": "Frame does not support _handle_zone_delta"}
        self.frame._handle_zone_delta(zone, card_name, -qty)
        zone_cards = getattr(self.frame, "zone_cards", {})
        cards = zone_cards.get(zone, [])
        card_entry = next((c for c in cards if c["name"].lower() == card_name.lower()), None)
        return {
            "subtracted": True,
            "zone": zone,
            "card_name": card_name,
            "new_qty": card_entry["qty"] if card_entry else 0,
            "total_qty": sum(c["qty"] for c in cards),
        }

    def _handle_get_scroll_pos(self, zone: str = "main") -> dict[str, Any]:
        """Get the scroll position of a zone's scrolled panel."""
        table = None
        if zone == "main":
            table = getattr(self.frame, "main_table", None)
        elif zone == "side":
            table = getattr(self.frame, "side_table", None)
        elif zone == "out":
            table = getattr(self.frame, "out_table", None)

        if table is None:
            return {
                "zone": zone,
                "scroll_x": 0,
                "scroll_y": 0,
                "error": f"No table for zone: {zone}",
            }

        grid_view = getattr(table, "grid_view", None)
        if grid_view is None:
            return {"zone": zone, "scroll_x": 0, "scroll_y": 0, "error": "No grid view on table"}

        x, y = grid_view.GetViewStart()
        return {"zone": zone, "scroll_x": x, "scroll_y": y}

    def _handle_get_card_images_loaded(self, zone: str = "main") -> dict[str, Any]:
        """Count how many cards in a zone's grid view have loaded their images."""
        table = None
        if zone == "main":
            table = getattr(self.frame, "main_table", None)
        elif zone == "side":
            table = getattr(self.frame, "side_table", None)
        elif zone == "out":
            table = getattr(self.frame, "out_table", None)

        if table is None:
            return {"zone": zone, "loaded": 0, "total": 0, "error": f"No table for zone: {zone}"}

        grid_view = getattr(table, "grid_view", None)
        if grid_view is None or not hasattr(grid_view, "count_loaded_images"):
            return {"zone": zone, "loaded": 0, "total": 0}
        loaded, total = grid_view.count_loaded_images()
        return {"zone": zone, "loaded": loaded, "total": total}
