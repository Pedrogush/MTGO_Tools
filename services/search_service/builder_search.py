"""Deck-builder multi-filter search orchestration."""

from __future__ import annotations

from typing import Any

from loguru import logger

from utils.card_data import CardDataManager
from utils.mana_query import normalize_mana_query
from utils.search_filters import matches_color_filter, matches_mana_cost, matches_mana_value


class BuilderSearchMixin:
    """Combined filter pipeline used by the Deck Builder search panel."""

    def search_with_builder_filters(
        self,
        filters: dict[str, Any],
        card_manager: CardDataManager,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        mana_query = normalize_mana_query(filters.get("mana", ""))
        mana_mode = "exact" if filters.get("mana_exact") else "contains"
        mv_cmp = filters.get("mv_comparator", "Any")

        mv_value = None
        mv_value_text = filters.get("mv_value", "")
        if mv_value_text:
            try:
                mv_value = float(mv_value_text)
            except ValueError:
                logger.warning(f"Invalid mana value: {mv_value_text}")
                mv_value = None

        selected_formats = filters.get("formats", [])
        color_mode = filters.get("color_mode", "Any")
        selected_colors = filters.get("selected_colors", [])
        format_pool_cards: set[str] = set()
        if filters.get("format_pool_enabled") and selected_formats:
            format_pool_cards = self.format_card_pool_service.get_card_pool_names(
                selected_formats[0]
            )

        # Pre-filter by name only; oracle text is matched per-card below.
        query = filters.get("name") or ""
        results = card_manager.search_cards(query=query, format_filter=None)

        filtered: list[dict[str, Any]] = []
        for card in results:
            if filters.get("name"):
                name_lower = card.get("name_lower", "")
                if filters["name"].lower() not in name_lower:
                    continue

            if filters.get("type"):
                type_line = (card.get("type_line") or "").lower()
                if filters["type"].lower() not in type_line:
                    continue

            if mana_query:
                mana_cost = (card.get("mana_cost") or "").upper()
                if not matches_mana_cost(mana_cost, mana_query, mana_mode):
                    continue

            if filters.get("text"):
                if not self._matches_text_filter(
                    card, filters["text"], filters.get("text_mode", "all")
                ):
                    continue

            if selected_formats:
                legalities = card.get("legalities", {}) or {}
                if not all(legalities.get(fmt) == "Legal" for fmt in selected_formats):
                    continue

            if filters.get("format_pool_enabled") and format_pool_cards:
                card_name = card.get("name", "")
                if card_name not in format_pool_cards:
                    continue

            if mv_value is not None and mv_cmp not in ("Any", "-"):
                if not matches_mana_value(card.get("mana_value"), mv_value, mv_cmp):
                    continue

            # Lands are treated as colorless by ``_get_card_colors_for_filter``.
            if selected_colors and color_mode not in ("Any", "-"):
                if not matches_color_filter(
                    self._get_card_colors_for_filter(card), selected_colors, color_mode
                ):
                    continue

            if filters.get("radar_enabled") and filters.get("radar_cards"):
                radar_cards = filters.get("radar_cards", set())
                card_name = card.get("name", "")
                if card_name not in radar_cards:
                    continue

            filtered.append(card)
            if limit is not None and len(filtered) >= limit:
                break

        logger.debug(
            f"Search completed: {len(results)} initial results, "
            f"{len(filtered)} after filtering"
        )
        return filtered
