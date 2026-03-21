"""
Deck Stats Panel - Displays deck statistics, mana curve, and color distribution.

Shows summary statistics, mana curve breakdown, color concentration, type counts,
and opening-hand land probability analysis.
"""

from collections import Counter
from typing import Any

import wx

from services.deck_service import DeckService, get_deck_service
from utils.card_data import CardDataManager
from utils.constants import DARK_ACCENT, DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
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

# MTG color identity → (display name, bar colour)
_COLOR_MAP: dict[str, tuple[str, tuple[int, int, int]]] = {
    "W": ("White", (220, 210, 170)),
    "U": ("Blue", (59, 130, 246)),
    "B": ("Black", (140, 120, 160)),
    "R": ("Red", (210, 70, 50)),
    "G": ("Green", (60, 160, 70)),
    "C": ("Colorless", (160, 150, 130)),
    "Colorless": ("Colorless", (160, 150, 130)),
}

_ROW_H = 22
_LABEL_W = 90
_VALUE_W = 60
_BAR_PAD = 6
_TITLE_H = 22


class BarChartPanel(wx.Panel):
    """Custom panel that draws a horizontal bar chart."""

    def __init__(self, parent: wx.Window, title: str = "") -> None:
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*DARK_ALT))
        self._title = title
        # list of (label, display_value, raw_value, bar_colour)
        self._items: list[tuple[str, str, int, tuple[int, int, int]]] = []
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_data(
        self,
        items: list[tuple[str, str, int]],
        bar_colour: tuple[int, int, int] = DARK_ACCENT,
        per_item_colours: list[tuple[int, int, int]] | None = None,
    ) -> None:
        """Set chart data and trigger a repaint.

        Args:
            items: List of (label, display_value, raw_value) tuples.
            bar_colour: Default bar colour for all items.
            per_item_colours: Optional per-item override colours.
        """
        self._items = [
            (
                label,
                display_val,
                raw_val,
                per_item_colours[i] if per_item_colours else bar_colour,
            )
            for i, (label, display_val, raw_val) in enumerate(items)
        ]
        min_h = _TITLE_H + len(self._items) * _ROW_H + _BAR_PAD * 2
        self.SetMinSize((-1, min_h))
        self.Refresh()

    def clear(self) -> None:
        self._items = []
        self.Refresh()

    # ---- drawing ----

    def _on_size(self, _evt: wx.SizeEvent) -> None:
        self.Refresh()

    def _on_paint(self, _evt: wx.PaintEvent) -> None:
        dc = wx.BufferedPaintDC(self)
        self._draw(dc)

    def _draw(self, dc: wx.DC) -> None:
        w, h = self.GetClientSize()
        if w <= 0 or h <= 0:
            return

        dc.SetBackground(wx.Brush(wx.Colour(*DARK_ALT)))
        dc.Clear()

        # Title
        y = 4
        if self._title:
            dc.SetTextForeground(wx.Colour(*SUBDUED_TEXT))
            dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            dc.DrawText(self._title, _BAR_PAD, y)
            y += _TITLE_H

        if not self._items:
            return

        max_val = max(raw for _, _, raw, _ in self._items) or 1
        bar_area_w = max(w - _LABEL_W - _VALUE_W - _BAR_PAD * 3, 20)

        dc.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

        for label, display_val, raw_val, colour in self._items:
            bar_w = int(bar_area_w * raw_val / max_val)

            # Row background (subtle alternation already from panel bg)
            row_y = y + (_ROW_H - 14) // 2

            # Label
            dc.SetTextForeground(wx.Colour(*LIGHT_TEXT))
            lbl_tw, _ = dc.GetTextExtent(label)
            lbl_x = _LABEL_W - lbl_tw - _BAR_PAD
            dc.DrawText(label, max(lbl_x, 0), row_y)

            # Bar
            bar_x = _LABEL_W + _BAR_PAD
            bar_y = y + (_ROW_H - 12) // 2
            dc.SetBrush(wx.Brush(wx.Colour(*colour)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            if bar_w > 0:
                dc.DrawRoundedRectangle(bar_x, bar_y, bar_w, 12, 3)

            # Value
            dc.SetTextForeground(wx.Colour(*SUBDUED_TEXT))
            dc.DrawText(display_val, bar_x + bar_area_w + _BAR_PAD, row_y)

            y += _ROW_H


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

        # Mana curve bar chart
        self.curve_chart = BarChartPanel(self, title="Mana Curve")
        split.Add(self.curve_chart, 1, wx.RIGHT | wx.EXPAND, 12)

        # Color concentration bar chart
        self.color_chart = BarChartPanel(self, title="Color Share")
        split.Add(self.color_chart, 1, wx.RIGHT | wx.EXPAND, 12)

        # Type counts bar chart
        self.type_chart = BarChartPanel(self, title="Card Types")
        split.Add(self.type_chart, 1, wx.EXPAND)

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
            self.curve_chart.clear()
            self.color_chart.clear()
            self.type_chart.clear()
            self.hand_land_label.SetLabel("")
            return

        # Analyze deck
        stats = self.deck_service.analyze_deck(deck_text)

        # Count actual lands from zone_cards using type metadata (includes MDFCs)
        land_count, mdfc_count = self._count_lands()
        total_land_count = land_count + mdfc_count

        # Update summary
        land_label = f"{land_count} land{'s' if land_count != 1 else ''}"
        if mdfc_count:
            land_label += f" + {mdfc_count} MDFC{'s' if mdfc_count != 1 else ''}"
        summary = (
            f"Mainboard: {stats['mainboard_count']} cards ({stats['unique_mainboard']} unique)  |  "
            f"Sideboard: {stats['sideboard_count']} cards ({stats['unique_sideboard']} unique)  |  "
            f"Lands: {land_label}"
        )
        self.summary_label.SetLabel(summary)

        # Render charts
        self._render_curve()
        self._render_color_concentration()
        self._render_type_counts()
        self._render_hand_land_pct(stats["mainboard_count"], total_land_count)

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        """Set the card data manager for metadata lookups."""
        self.card_manager = card_manager

    def clear(self) -> None:
        """Clear all statistics."""
        self.summary_label.SetLabel("No deck loaded.")
        self.curve_chart.clear()
        self.color_chart.clear()
        self.type_chart.clear()
        self.hand_land_label.SetLabel("")

    # ============= Private Methods =============

    def _count_lands(self) -> tuple[int, int]:
        """Count lands and MDFC-lands in the mainboard using card type metadata.

        Returns:
            (lands, mdfcs) where lands are cards with Land in front type_line and
            mdfcs are cards with Land only in the back face type_line.
        """
        lands = mdfcs = 0
        for entry in self.zone_cards.get("main", []):
            qty = entry["qty"]
            meta = self.card_manager.get_card(entry["name"]) if self.card_manager else None
            type_line = (meta.get("type_line") or "").lower() if meta else ""
            back_type_line = (meta.get("back_type_line") or "").lower() if meta else ""
            if "land" in type_line:
                lands += qty
            elif "land" in back_type_line:
                mdfcs += qty
        return lands, mdfcs

    def _render_curve(self) -> None:
        """Render the mana curve bar chart."""
        if not self.card_manager:
            self.curve_chart.clear()
            return

        counts: Counter[str] = Counter()
        for entry in self.zone_cards.get("main", []):
            meta = self.card_manager.get_card(entry["name"])
            mana_value = meta.get("mana_value") if meta else None

            if isinstance(mana_value, int | float):
                value = int(mana_value)
                bucket = "7+" if value >= 7 else str(value)
            else:
                bucket = "X"

            counts[bucket] += entry["qty"]

        def curve_key(bucket: str) -> int:
            if bucket == "X":
                return 99
            if bucket.endswith("+") and bucket[:-1].isdigit():
                return int(bucket[:-1]) + 10
            if bucket.isdigit():
                return int(bucket)
            return 98

        items = [
            (bucket, str(counts[bucket]), counts[bucket])
            for bucket in sorted(counts.keys(), key=curve_key)
        ]
        self.curve_chart.set_data(items, bar_colour=DARK_ACCENT)

    def _render_color_concentration(self) -> None:
        """Render the color concentration bar chart."""
        if not self.card_manager:
            self.color_chart.clear()
            return

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
            self.color_chart.clear()
            return

        sorted_colors = sorted(totals.items(), key=lambda x: x[1], reverse=True)

        items = []
        colours = []
        for color, count in sorted_colors:
            name, bar_colour = _COLOR_MAP.get(color, (color, DARK_ACCENT))
            percentage = (count / grand_total) * 100
            display = f"{count} ({percentage:.1f}%)"
            items.append((name, display, count))
            colours.append(bar_colour)

        self.color_chart.set_data(items, per_item_colours=colours)

    def _render_type_counts(self) -> None:
        """Render card type count bar chart for the mainboard."""
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

        display_order = _CARD_TYPES + ["Other"]
        items = [
            (card_type, str(counts[card_type]), counts[card_type])
            for card_type in display_order
            if counts[card_type]
        ]
        self.type_chart.set_data(items, bar_colour=DARK_ACCENT)

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
