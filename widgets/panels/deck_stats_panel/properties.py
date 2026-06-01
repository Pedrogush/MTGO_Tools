"""Read-only item getters for the deck stats panel mixin.

Reads ``self.zone_cards``/``self.card_manager`` and produces the plain tuples
consumed by the stateless HTML builders in :mod:`stats_chart_html`. Static data
tables live in :mod:`stats_constants`; the HTML/CSS subsystem lives in
:mod:`stats_chart_html`.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from utils.constants.deck_rules import (
    STATS_CURVE_HIGH_CMC_BUCKET,
    STATS_CURVE_UNKNOWN_SORT_KEY,
    STATS_CURVE_X_SORT_KEY,
    STATS_HAND_COLLAPSE_THRESHOLD,
    STATS_HAND_SIZE,
)
from utils.math_utils import hypergeometric_exactly
from widgets.panels.deck_stats_panel.stats_chart_html import _curve_colour
from widgets.panels.deck_stats_panel.stats_constants import (
    _CARD_TYPES,
    _COLOR_MAP,
    _HAND_COLOURS,
    _TYPE_COLOURS,
)

if TYPE_CHECKING:
    from widgets.panels.deck_stats_panel.protocol import DeckStatsPanelProto

    _Base = DeckStatsPanelProto
else:
    _Base = object


class DeckStatsPanelPropertiesMixin(_Base):
    """Read-only data getters and pure-data helpers for :class:`DeckStatsPanel`.

    Kept as a mixin (no ``__init__``) so :class:`DeckStatsPanel` remains the
    single source of truth for instance-state initialization.
    """

    def _card_data_available(self) -> bool:
        return self.card_manager is not None and self.card_manager.is_loaded

    def _count_lands(self) -> tuple[int, int]:
        lands = mdfcs = 0
        for entry in self.zone_cards.get("main", []):
            qty = entry["qty"]
            meta = (
                self.card_manager.get_card(entry["name"]) if self._card_data_available() else None
            )
            type_line = (meta.get("type_line") or "").lower() if meta else ""
            back_type_line = (meta.get("back_type_line") or "").lower() if meta else ""
            if "land" in type_line:
                lands += qty
            elif "land" in back_type_line:
                mdfcs += qty
        return lands, mdfcs

    def _curve_items(self) -> list[tuple[str, str, float, str, str]]:
        if not self._card_data_available():
            return []

        counts: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            meta = self.card_manager.get_card(entry["name"])
            mana_value = meta.get("mana_value") if meta else None
            if isinstance(mana_value, int | float):
                value = int(mana_value)
                bucket = (
                    f"{STATS_CURVE_HIGH_CMC_BUCKET}+"
                    if value >= STATS_CURVE_HIGH_CMC_BUCKET
                    else str(value)
                )
            else:
                bucket = "X"
            counts[bucket] += entry["qty"]

        if not counts:
            return []

        def curve_key(b: str) -> int:
            if b == "X":
                return STATS_CURVE_X_SORT_KEY
            if b.endswith("+") and b[:-1].isdigit():
                return int(b[:-1]) + 10
            if b.isdigit():
                return int(b)
            return STATS_CURVE_UNKNOWN_SORT_KEY

        # Fill in zero buckets so the curve is continuous from 0 to the max CMC present
        numeric_buckets = [int(b) for b in counts if b.isdigit()]
        if numeric_buckets:
            max_cmc = max(numeric_buckets)
            for cmc in range(0, max_cmc + 1):
                counts.setdefault(str(cmc), 0)

        items = []
        for bucket in sorted(counts.keys(), key=curve_key):
            count = counts[bucket]
            colour = _curve_colour(bucket)
            label_text = "X" if bucket == "X" else bucket
            mv_label = "X" if bucket == "X" else f"{label_text}"
            tooltip = f"Mana Value {mv_label}: {count} card{'s' if count != 1 else ''}"
            items.append((label_text, str(count), float(count), colour, tooltip))
        return items

    def _color_items(self) -> list[tuple[str, str, float, str, str]]:
        if not self._card_data_available():
            return []

        totals: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            meta = self.card_manager.get_card(entry["name"])
            identity = meta.get("color_identity") if meta else []
            if not identity:
                totals["Colorless"] += entry["qty"]
            else:
                for color in identity:
                    totals[color] += entry["qty"]

        grand_total = sum(totals.values())
        if grand_total == 0:
            return []

        items = []
        for color, count in sorted(totals.items(), key=lambda x: x[1], reverse=True):
            full_name, hex_colour = _COLOR_MAP.get(color, (color, "#828282"))
            pct = count / grand_total * 100
            tooltip = f"{full_name}: {pct:.1f}%"
            items.append((color, f"{pct:.0f}%", pct, hex_colour, tooltip))
        return items

    def _type_items(self) -> list[tuple[str, int, int, str, str]]:
        counts: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            type_line = ""
            if self._card_data_available():
                meta = self.card_manager.get_card(entry["name"])
                type_line = (meta.get("type_line") or "") if meta else ""

            matched = False
            for card_type in _CARD_TYPES:
                if card_type.lower() in type_line.lower():
                    counts[card_type] += entry["qty"]
                    matched = True
            if not matched:
                counts["Other"] += entry["qty"]

        display_order = _CARD_TYPES + ["Other"]
        # Only include "Other" if something actually fell into it
        if not counts.get("Other"):
            display_order = _CARD_TYPES

        max_count = max((counts[t] for t in display_order), default=1) or 1
        items = []
        for card_type in display_order:
            count = counts[card_type]
            colour = _TYPE_COLOURS.get(card_type, "#828282")
            tooltip = f"{card_type}: {count} card{'s' if count != 1 else ''}"
            items.append((card_type, count, max_count, colour, tooltip))
        return items

    def _hand_items(
        self, deck_size: int | float, land_count: int | float
    ) -> list[tuple[str, str, float, str, str]]:
        deck_size = round(deck_size)
        land_count = round(land_count)
        if deck_size <= 0:
            return []

        hand_size = STATS_HAND_SIZE
        probs = [
            hypergeometric_exactly(deck_size, land_count, hand_size, k) * 100
            for k in range(hand_size + 1)
        ]

        # Collapse the last two counts into "6+" to avoid unreadably tiny bars
        collapsed_prob = (
            probs[STATS_HAND_COLLAPSE_THRESHOLD] + probs[STATS_HAND_COLLAPSE_THRESHOLD + 1]
        )
        display = list(
            zip(range(STATS_HAND_COLLAPSE_THRESHOLD), probs[:STATS_HAND_COLLAPSE_THRESHOLD])
        ) + [(STATS_HAND_COLLAPSE_THRESHOLD, collapsed_prob)]

        items = []
        for k, pct in display:
            label = f"{k}+" if k == STATS_HAND_COLLAPSE_THRESHOLD else str(k)
            n_word = "land" if k == 1 else "lands"
            tooltip = f"{label} {n_word} in opener: {pct:.1f}%"
            colour = _HAND_COLOURS[min(k, len(_HAND_COLOURS) - 1)]
            items.append((label, f"{pct:.1f}%", pct, colour, tooltip))
        return items
