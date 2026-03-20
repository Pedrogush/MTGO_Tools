"""
Deck Stats Panel - Displays deck statistics, mana curve, and color distribution.

Shows summary statistics, mana curve breakdown, color concentration, type counts,
and opening-hand land probability analysis.
"""

from collections import Counter
from typing import Any

import wx
import wx.dataview as dv

from services.deck_service import DeckService, get_deck_service
from utils.card_data import CardDataManager
from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.math_utils import hypergeometric_at_least

_CARD_TYPES = [
    "Land",
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Battle",
]


class DeckStatsPanel(wx.Panel):
    """Panel that displays deck statistics and analysis."""

    def __init__(
        self,
        parent: wx.Window,
        card_manager: CardDataManager | None = None,
        deck_service: DeckService | None = None,
    ):
        """
        Initialize the deck stats panel.

        Args:
            parent: Parent window
            card_manager: Card data manager for metadata lookups
            deck_service: Deck service for analysis
        """
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.card_manager = card_manager
        self.deck_service = deck_service or get_deck_service()
        self.zone_cards: dict[str, list[dict[str, Any]]] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Summary statistics
        self.summary_label = wx.StaticText(self, label="No deck loaded.")
        self.summary_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.summary_label, 0, wx.ALL, 6)

        # Split view for curve, color, and type charts
        split = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(split, 1, wx.EXPAND | wx.ALL, 6)

        # Mana curve list
        self.curve_list = dv.DataViewListCtrl(self)
        self.curve_list.AppendTextColumn("CMC", width=80)
        self.curve_list.AppendTextColumn("Count", width=80)
        self.curve_list.SetBackgroundColour(DARK_ALT)
        self.curve_list.SetForegroundColour(LIGHT_TEXT)
        split.Add(self.curve_list, 0, wx.RIGHT, 12)

        # Color concentration list
        self.color_list = dv.DataViewListCtrl(self)
        self.color_list.AppendTextColumn("Color", width=120)
        self.color_list.AppendTextColumn("Share", width=100)
        self.color_list.SetBackgroundColour(DARK_ALT)
        self.color_list.SetForegroundColour(LIGHT_TEXT)
        split.Add(self.color_list, 0, wx.RIGHT, 12)

        # Type counts list
        self.type_list = dv.DataViewListCtrl(self)
        self.type_list.AppendTextColumn("Type", width=120)
        self.type_list.AppendTextColumn("Count", width=80)
        self.type_list.SetBackgroundColour(DARK_ALT)
        self.type_list.SetForegroundColour(LIGHT_TEXT)
        split.Add(self.type_list, 0)

        # Hand/land probability label
        self.hand_land_label = wx.StaticText(self, label="")
        self.hand_land_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.hand_land_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

    # ============= Public API =============

    def update_stats(self, deck_text: str, zone_cards: dict[str, list[dict[str, Any]]]) -> None:
        """
        Update the statistics display.

        Args:
            deck_text: Full deck text for analysis
            zone_cards: Dictionary mapping zone names to card lists
        """
        self.zone_cards = zone_cards

        if not deck_text.strip():
            self.summary_label.SetLabel("No deck loaded.")
            self.curve_list.DeleteAllItems()
            self.color_list.DeleteAllItems()
            self.type_list.DeleteAllItems()
            self.hand_land_label.SetLabel("")
            return

        # Analyze deck
        stats = self.deck_service.analyze_deck(deck_text)

        # Update summary
        summary = (
            f"Mainboard: {stats['mainboard_count']} cards ({stats['unique_mainboard']} unique)  |  "
            f"Sideboard: {stats['sideboard_count']} cards ({stats['unique_sideboard']} unique)  |  "
            f"Estimated lands: {stats['estimated_lands']}"
        )
        self.summary_label.SetLabel(summary)

        # Render charts
        self._render_curve()
        self._render_color_concentration()
        self._render_type_counts()
        self._render_hand_land_pct(stats["mainboard_count"], stats["estimated_lands"])

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        """Set the card data manager for metadata lookups."""
        self.card_manager = card_manager

    def clear(self) -> None:
        """Clear all statistics."""
        self.summary_label.SetLabel("No deck loaded.")
        self.curve_list.DeleteAllItems()
        self.color_list.DeleteAllItems()
        self.type_list.DeleteAllItems()
        self.hand_land_label.SetLabel("")

    # ============= Private Methods =============

    def _render_curve(self) -> None:
        """Render the mana curve chart."""
        self.curve_list.DeleteAllItems()

        if not self.card_manager:
            return

        # Count cards by mana value
        counts: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            meta = self.card_manager.get_card(entry["name"])
            mana_value = meta.get("mana_value") if meta else None

            # Bucket the mana value
            if isinstance(mana_value, int | float):
                value = int(mana_value)
                bucket = "7+" if value >= 7 else str(value)
            else:
                bucket = "X"

            counts[bucket] += entry["qty"]

        # Sort buckets numerically
        def curve_key(bucket: str) -> int:
            if bucket == "X":
                return 99
            if bucket.endswith("+") and bucket[:-1].isdigit():
                return int(bucket[:-1]) + 10
            if bucket.isdigit():
                return int(bucket)
            return 98

        # Add to list
        for bucket in sorted(counts.keys(), key=curve_key):
            self.curve_list.AppendItem([bucket, str(counts[bucket])])

    def _render_color_concentration(self) -> None:
        """Render the color concentration chart."""
        self.color_list.DeleteAllItems()

        if not self.card_manager:
            return

        # Count cards by color identity
        totals: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            meta = self.card_manager.get_card(entry["name"])
            identity = meta.get("color_identity") if meta else []

            if not identity:
                totals["Colorless"] += entry["qty"]
            else:
                # Count each color separately
                for color in identity:
                    totals[color] += entry["qty"]

        # Calculate total for percentages
        grand_total = sum(totals.values())
        if grand_total == 0:
            return

        # Sort by count descending
        sorted_colors = sorted(totals.items(), key=lambda x: x[1], reverse=True)

        # Color name mapping
        color_names = {
            "W": "White",
            "U": "Blue",
            "B": "Black",
            "R": "Red",
            "G": "Green",
            "C": "Colorless",
        }

        # Add to list with percentages
        for color, count in sorted_colors:
            name = color_names.get(color, color)
            percentage = (count / grand_total) * 100
            share = f"{count} ({percentage:.1f}%)"
            self.color_list.AppendItem([name, share])

    def _render_type_counts(self) -> None:
        """Render card type counts for the mainboard."""
        self.type_list.DeleteAllItems()

        counts: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            type_line = ""
            if self.card_manager:
                meta = self.card_manager.get_card(entry["name"])
                type_line = (meta.get("type_line") or "") if meta else ""

            matched = False
            for card_type in _CARD_TYPES:
                if card_type.lower() in type_line.lower():
                    counts[card_type] += entry["qty"]
                    matched = True
            if not matched:
                counts["Other"] += entry["qty"]

        # Show types in display order, omit zero-count types
        display_order = _CARD_TYPES + ["Other"]
        for card_type in display_order:
            if counts[card_type]:
                self.type_list.AppendItem([card_type, str(counts[card_type])])

    def _render_hand_land_pct(self, deck_size: int, land_count: int) -> None:
        """Render opening-hand land probability label."""
        if deck_size <= 0 or land_count <= 0:
            self.hand_land_label.SetLabel("")
            return

        parts = []
        for target in (2, 3, 4):
            if target > land_count:
                break
            try:
                pct = hypergeometric_at_least(deck_size, land_count, 7, target) * 100
                parts.append(f"≥{target} lands: {pct:.1f}%")
            except ValueError:
                break

        if parts:
            self.hand_land_label.SetLabel("Opening hand (7 cards) — " + "  |  ".join(parts))
        else:
            self.hand_land_label.SetLabel("")
