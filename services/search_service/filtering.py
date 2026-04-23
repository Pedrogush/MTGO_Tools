"""Per-card predicate filters and combined ``filter_cards`` pipeline."""

from __future__ import annotations

from typing import Any

from utils.search_filters import matches_color_filter, matches_mana_cost, matches_mana_value


class FilteringMixin:
    """Card-level filter predicates and the combined ``filter_cards`` pipeline."""

    def filter_cards(
        self,
        cards: list[dict[str, Any]],
        colors: list[str] | None = None,
        color_mode: str = "Any",
        types: list[str] | None = None,
        mana_cost_query: str | None = None,
        mana_cost_mode: str = "at_least",
        mana_value: float | None = None,
        mana_value_comparator: str = "=",
        text_contains: str | None = None,
        text_mode: str = "all",
    ) -> list[dict[str, Any]]:
        filtered = cards

        if colors and color_mode != "Any":
            filtered = [
                card for card in filtered if self._matches_color_filter(card, colors, color_mode)
            ]

        if types:
            filtered = [card for card in filtered if self._matches_type_filter(card, types)]

        if mana_cost_query:
            filtered = [
                card
                for card in filtered
                if self._matches_mana_cost_filter(card, mana_cost_query, mana_cost_mode)
            ]

        if mana_value is not None:
            filtered = [
                card
                for card in filtered
                if self._matches_mana_value_filter(card, mana_value, mana_value_comparator)
            ]

        if text_contains:
            filtered = [
                card
                for card in filtered
                if self._matches_text_filter(card, text_contains, text_mode)
            ]

        return filtered

    def _matches_color_filter(self, card: dict[str, Any], colors: list[str], mode: str) -> bool:
        card_colors = self._get_card_colors_for_filter(card)
        return matches_color_filter(card_colors, colors, mode)

    def _get_card_colors_for_filter(self, card: dict[str, Any]) -> list[str]:
        # Most lands are treated as colorless. Lands that have actual card
        # colors in their mtgjson entry (e.g. Dryad Arbor — a green Forest Land
        # creature with colors=["G"]) retain those colors.
        type_line = (card.get("type_line") or card.get("type") or "").lower()
        if "land" in type_line:
            card_colors = card.get("colors", [])
            if isinstance(card_colors, str):
                card_colors = list(card_colors)
            return card_colors
        card_colors = card.get("colors", []) or card.get("color_identity", [])
        if isinstance(card_colors, str):
            card_colors = list(card_colors)
        return card_colors

    def _matches_type_filter(self, card: dict[str, Any], types: list[str]) -> bool:
        card_type = card.get("type_line", "") or card.get("type", "")
        if not card_type:
            return False

        card_type_lower = card_type.lower()
        return any(type_keyword.lower() in card_type_lower for type_keyword in types)

    def _matches_mana_cost_filter(self, card: dict[str, Any], query: str, mode: str) -> bool:
        card_cost = card.get("mana_cost", "")
        if not card_cost:
            return False
        return matches_mana_cost(card_cost, query, mode)

    def _matches_mana_value_filter(
        self, card: dict[str, Any], target: float, comparator: str
    ) -> bool:
        card_value = card.get("cmc") or card.get("mana_value")
        if card_value is None:
            return False
        return matches_mana_value(card_value, target, comparator)

    def _matches_text_filter(self, card: dict[str, Any], query: str, mode: str = "all") -> bool:
        # mode="all": full phrase match; mode="any": every word must appear somewhere
        text = card.get("oracle_text", "") or card.get("text", "")
        if not text:
            return False
        text_lower = text.lower()
        if mode == "any":
            return all(word in text_lower for word in query.lower().split())
        return query.lower() in text_lower
