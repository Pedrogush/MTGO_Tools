"""
Deck Stats Panel - Displays deck statistics using an HTML/CSS visualization.

Shows summary statistics, mana curve breakdown, color distribution, type counts,
and opening-hand land probability analysis.  All charts are rendered in a
wx.html2.WebView so they support hover tooltips and pixel-perfect layout.
"""

import math
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

import wx
import wx.html2

from services.deck_service import DeckService, get_deck_service
from utils.card_data import CardDataManager
from utils.constants import DARK_PANEL
from utils.constants.deck_rules import (
    STATS_CURVE_COLOUR_LERP_MAX_CMC,
    STATS_CURVE_HIGH_CMC_BUCKET,
    STATS_CURVE_UNKNOWN_SORT_KEY,
    STATS_CURVE_X_CMC_FOR_COLOUR,
    STATS_CURVE_X_SORT_KEY,
    STATS_HAND_COLLAPSE_THRESHOLD,
    STATS_HAND_SIZE,
)
from utils.constants.ui_images import (
    STATS_MANA_SVG_DISPLAY_SIZE,
    STATS_MANA_SVG_SOURCE_SIZE,
)
from utils.constants.ui_layout import (
    PADDING_BASE,
    PADDING_MD,
    PADDING_SM,
    STATS_BAR_BORDER_RADIUS,
    STATS_CHART_BORDER_RADIUS,
    STATS_FONT_SIZE_BODY,
    STATS_FONT_SIZE_LABEL,
    STATS_FONT_SIZE_SMALL,
    STATS_FONT_SIZE_VALUE,
    STATS_HBAR_COUNT_WIDTH,
    STATS_HBAR_LABEL_WIDTH,
    STATS_HBAR_ROW_HEIGHT,
    STATS_HBAR_TRACK_HEIGHT,
    STATS_HBAR_ZERO_OPACITY,
    STATS_TOOLTIP_BELOW_OFFSET_Y,
    STATS_TOOLTIP_BORDER_RADIUS,
    STATS_TOOLTIP_EDGE_MARGIN,
    STATS_TOOLTIP_FLIP_OFFSET_X,
    STATS_TOOLTIP_OFFSET_X,
    STATS_TOOLTIP_OFFSET_Y,
    STATS_TOOLTIP_PADDING,
    STATS_TOOLTIP_Z_INDEX,
    STATS_VBAR_XAXIS_BOTTOM_OFFSET,
    STATS_VBAR_XAXIS_PADDING_BOTTOM,
)

_CARD_TYPES = [
    "Land",
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Battle",
    "Kindred",
]

# MTG color identity → (full display label, hex bar colour)
_COLOR_MAP: dict[str, tuple[str, str]] = {
    "W": ("White", "#DCD2AA"),
    "U": ("Blue", "#3B82F6"),
    "B": ("Black", "#8C78A0"),
    "R": ("Red", "#D24632"),
    "G": ("Green", "#3CA046"),
    "C": ("Colorless", "#A0968A"),
    "Colorless": ("Colorless", "#A0968A"),
}

_TYPE_COLOURS: dict[str, str] = {
    "Land": "#917D5F",
    "Creature": "#5A87B9",
    "Instant": "#50A591",
    "Sorcery": "#7864AF",
    "Enchantment": "#A56E96",
    "Artifact": "#9B9BA5",
    "Planeswalker": "#5FA0B9",
    "Battle": "#AF735A",
    "Kindred": "#7A9E6A",
    "Other": "#828282",
}

# Opening-hand land count bar colours (0-7 lands)
# Accent blue for "good" outcomes (2-3 lands), muted gray-blue for bad outcomes.
_HAND_COLOURS = [
    "#4A5568",  # 0 – bad (muted gray-blue)
    "#4A5568",  # 1 – bad
    "#3B82F6",  # 2 – good (accent blue)
    "#3B82F6",  # 3 – good
    "#4A5568",  # 4 – bad
    "#4A5568",  # 5 – bad
    "#4A5568",  # 6 – bad
    "#4A5568",  # 7 – bad
]

# Mana curve gradient: light sky-blue (low CMC) → deep accent blue (high CMC).
_CURVE_WARM = (147, 197, 253)
_CURVE_COLD = (30, 64, 175)

# Color key → mana SVG filename stem
_COLOR_SVG_FILENAMES: dict[str, str] = {
    "W": "w",
    "U": "u",
    "B": "b",
    "R": "r",
    "G": "g",
    "C": "c",
    "Colorless": "c",
}


def _load_mana_svgs() -> dict[str, str]:
    """Load and inline mana symbol SVGs for each color key, sized 18×18."""
    svg_dir = Path(__file__).parent.parent.parent / "assets" / "mana" / "svg"
    result: dict[str, str] = {}
    for key, stem in _COLOR_SVG_FILENAMES.items():
        path = svg_dir / f"{stem}.svg"
        if path.exists():
            svg = path.read_text(encoding="utf-8")
            svg = svg.replace(
                f'width="{STATS_MANA_SVG_SOURCE_SIZE}" height="{STATS_MANA_SVG_SOURCE_SIZE}"',
                f'width="{STATS_MANA_SVG_DISPLAY_SIZE}" height="{STATS_MANA_SVG_DISPLAY_SIZE}"',
            )
            svg = svg.replace('fill="#444"', 'fill="#ECECEC"')
            # Strip the XML comment line to reduce HTML payload
            svg = "\n".join(line for line in svg.splitlines() if not line.startswith("<!--"))
            result[key] = svg.strip()
    return result


_COLOR_SVG_HTML: dict[str, str] = _load_mana_svgs()


def _lerp_hex(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _curve_colour(bucket: str) -> str:
    if bucket == "X":
        cmc = STATS_CURVE_X_CMC_FOR_COLOUR
    elif bucket.endswith("+") and bucket[:-1].isdigit():
        cmc = int(bucket[:-1])
    elif bucket.isdigit():
        cmc = int(bucket)
    else:
        cmc = 0
    return _lerp_hex(_CURVE_WARM, _CURVE_COLD, min(cmc / STATS_CURVE_COLOUR_LERP_MAX_CMC, 1.0))


def _hypergeometric_exactly(n_total: int, n_success: int, n_draw: int, k: int) -> float:
    """P(X = k) under the hypergeometric distribution."""
    n_fail = n_total - n_success
    if k < 0 or k > n_success or n_draw - k < 0 or n_draw - k > n_fail:
        return 0.0
    return math.comb(n_success, k) * math.comb(n_fail, n_draw - k) / math.comb(n_total, n_draw)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body {{
  height: 100%;
  background: #22272E;
  color: #ECECEC;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: {STATS_FONT_SIZE_BODY}px;
  overflow: hidden;
}}

.root {{
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: {PADDING_BASE}px;
  gap: {PADDING_MD}px;
}}

/* ── Summary bar ── */
.summary {{
  color: #B9BFCA;
  font-size: {STATS_FONT_SIZE_LABEL}px;
  flex-shrink: 0;
  padding: {PADDING_SM // 2}px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

/* ── Top row: three charts side-by-side ── */
.top-row {{
  display: flex;
  gap: {PADDING_BASE}px;
  flex: 3;
  min-height: 0;
}}

/* ── Bottom chart ── */
.bottom-row {{
  flex: 2;
  min-height: 0;
}}

/* ── Shared chart container ── */
.chart {{
  display: flex;
  flex-direction: column;
  background: #28303A;
  border-radius: {STATS_CHART_BORDER_RADIUS}px;
  padding: {PADDING_BASE}px {PADDING_BASE}px {PADDING_SM}px {PADDING_BASE}px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}}

.chart-title {{
  font-size: {STATS_FONT_SIZE_LABEL}px;
  font-weight: 600;
  color: #8B929E;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: {PADDING_SM}px;
  flex-shrink: 0;
}}

.chart-empty {{
  color: #555;
  font-style: italic;
  padding: {PADDING_BASE}px;
}}

/* ── Vertical bar chart ── */
.vbar-area {{
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: {PADDING_SM}px;
  flex: 1;
  min-height: 0;
  padding-bottom: {STATS_VBAR_XAXIS_PADDING_BOTTOM}px;  /* room for x-axis labels (icons up to {STATS_MANA_SVG_DISPLAY_SIZE}px tall) */
  position: relative;
}}

.vbar-col {{
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  flex: 1;
  min-width: 0;
  height: 100%;
  position: relative;
  cursor: default;
}}

/* value label above bar */
.vbar-val {{
  font-size: {STATS_FONT_SIZE_SMALL}px;
  color: #ECECEC;
  margin-bottom: 2px;
  white-space: nowrap;
  line-height: 1;
  text-align: center;
}}

.vbar {{
  width: 100%;
  border-radius: {STATS_BAR_BORDER_RADIUS}px {STATS_BAR_BORDER_RADIUS}px 0 0;
  transition: filter 0.1s;
  min-height: 2px;
}}

.vbar-col:hover .vbar {{
  filter: brightness(1.3);
}}

/* x-axis label below bars */
.vbar-lbl {{
  position: absolute;
  bottom: {STATS_VBAR_XAXIS_BOTTOM_OFFSET}px;
  font-size: {STATS_FONT_SIZE_SMALL}px;
  color: #8B929E;
  white-space: nowrap;
  text-align: center;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}}

/* ── Floating tooltip (JS-positioned, never clipped) ── */
#tooltip {{
  display: none;
  position: fixed;
  background: rgba(10, 12, 16, 0.93);
  color: #ECECEC;
  padding: {STATS_TOOLTIP_PADDING};
  border-radius: {STATS_TOOLTIP_BORDER_RADIUS}px;
  white-space: nowrap;
  font-size: {STATS_FONT_SIZE_LABEL}px;
  pointer-events: none;
  z-index: {STATS_TOOLTIP_Z_INDEX};
  border: 1px solid #3B4351;
}}

/* ── Horizontal bar chart (Card Types) ── */
.hbar-area {{
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  flex: 1;
  min-height: 0;
  gap: {PADDING_SM}px;
  padding-top: 2px;
}}

.hbar-row {{
  display: flex;
  align-items: center;
  gap: {PADDING_MD}px;
  cursor: default;
  position: relative;
  height: {STATS_HBAR_ROW_HEIGHT}px;
  flex-shrink: 0;
}}

.hbar-label {{
  width: {STATS_HBAR_LABEL_WIDTH}px;
  text-align: left;
  color: #ECECEC;
  font-size: {STATS_FONT_SIZE_LABEL}px;
  flex-shrink: 0;
  white-space: nowrap;
}}

.hbar-track {{
  flex: 1;
  position: relative;
  height: {STATS_HBAR_TRACK_HEIGHT}px;
  border-radius: {STATS_BAR_BORDER_RADIUS}px;
  background: #1C2028;
}}

.hbar {{
  height: 100%;
  border-radius: {STATS_BAR_BORDER_RADIUS}px;
  transition: filter 0.1s;
}}

.hbar-row:hover .hbar {{
  filter: brightness(1.3);
}}

.hbar-count {{
  width: {STATS_HBAR_COUNT_WIDTH}px;
  font-size: {STATS_FONT_SIZE_LABEL}px;
  color: #8B929E;
  flex-shrink: 0;
}}
"""


_JS_TOOLTIP = f"""
<div id="tooltip"></div>
<script>
var tip = document.getElementById('tooltip');
function showTip(el, evt) {{
  tip.textContent = el.dataset.tip;
  tip.style.display = 'block';
  moveTip(evt);
}}
function moveTip(evt) {{
  var x = evt.clientX + {STATS_TOOLTIP_OFFSET_X}, y = evt.clientY - {STATS_TOOLTIP_OFFSET_Y};
  var tw = tip.offsetWidth, th = tip.offsetHeight;
  if (x + tw > window.innerWidth - {STATS_TOOLTIP_EDGE_MARGIN}) x = evt.clientX - tw - {STATS_TOOLTIP_FLIP_OFFSET_X};
  if (y < {STATS_TOOLTIP_EDGE_MARGIN}) y = evt.clientY + {STATS_TOOLTIP_BELOW_OFFSET_Y};
  tip.style.left = x + 'px';
  tip.style.top  = y + 'px';
}}
function hideTip() {{ tip.style.display = 'none'; }}
</script>
"""


def _build_vbars(
    items: list[tuple[str, str, float, str, str]],  # (label, val_text, raw, colour, tooltip)
    val_font_size: int = STATS_FONT_SIZE_SMALL,
    icon_map: dict[str, str] | None = None,
) -> str:
    """Render the inner bar columns of a vertical bar chart."""
    if not items:
        return '<div class="chart-empty">No data</div>'

    max_raw = max(r for _, _, r, _, _ in items) or 1.0

    html = '<div class="vbar-area">'
    for label, val_text, raw, colour, tooltip in items:
        pct = raw / max_raw * 100
        tip_attr = escape(tooltip, quote=True)
        lbl_html = icon_map[label] if (icon_map and label in icon_map) else escape(label)
        html += (
            f'<div class="vbar-col" data-tip="{tip_attr}"'
            f' onmouseenter="showTip(this,event)" onmousemove="moveTip(event)" onmouseleave="hideTip()">'
            f'<div class="vbar-val" style="font-size:{val_font_size}px">{escape(val_text)}</div>'
            f'<div class="vbar" style="height:{pct:.1f}%;background:{colour};"></div>'
            f'<div class="vbar-lbl">{lbl_html}</div>'
            f"</div>"
        )
    html += "</div>"
    return html


def _build_hbars(
    items: list[tuple[str, int, int, str, str]],  # (label, count, max_count, colour, tooltip)
) -> str:
    """Render a horizontal bar chart (Card Types)."""
    if not items:
        return '<div class="chart-empty">No data</div>'

    max_count = max(c for _, c, _, _, _ in items) or 1

    html = '<div class="hbar-area">'
    for label, count, _max, colour, tooltip in items:
        pct = count / max_count * 100
        tip_attr = escape(tooltip, quote=True)
        # Zero-count rows: dim the label and show an empty track
        dim = f' style="opacity:{STATS_HBAR_ZERO_OPACITY}"' if count == 0 else ""
        html += (
            f'<div class="hbar-row" data-tip="{tip_attr}"'
            f' onmouseenter="showTip(this,event)" onmousemove="moveTip(event)" onmouseleave="hideTip()">'
            f'<div class="hbar-label"{dim}>{escape(label)}</div>'
            f'<div class="hbar-track">'
            f'<div class="hbar" style="width:{pct:.1f}%;background:{colour};"></div>'
            f"</div>"
            f'<div class="hbar-count"{dim}>{count if count else ""}</div>'
            f"</div>"
        )
    html += "</div>"
    return html


def _build_html(
    summary: str,
    curve_items: list[tuple[str, str, float, str, str]],
    color_items: list[tuple[str, str, float, str, str]],
    type_items: list[tuple[str, int, int, str, str]],
    hand_items: list[tuple[str, str, float, str, str]],
) -> str:
    curve_html = _build_vbars(curve_items)
    color_html = _build_vbars(color_items, icon_map=_COLOR_SVG_HTML if _COLOR_SVG_HTML else None)
    type_html = _build_hbars(type_items)
    hand_html = _build_vbars(hand_items, val_font_size=STATS_FONT_SIZE_VALUE)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
{_JS_TOOLTIP}
<div class="root">
  <div class="summary">{escape(summary)}</div>
  <div class="top-row">
    <div class="chart">
      <div class="chart-title">Mana Curve</div>
      {curve_html}
    </div>
    <div class="chart">
      <div class="chart-title">Color Share</div>
      {color_html}
    </div>
    <div class="chart">
      <div class="chart-title">Card Types</div>
      {type_html}
    </div>
  </div>
  <div class="bottom-row">
    <div class="chart" style="height:100%">
      <div class="chart-title">Lands in Opening Hand</div>
      {hand_html}
    </div>
  </div>
</div>
</body>
</html>"""


_EMPTY_HTML = _build_html(
    "No deck loaded.",
    [],
    [],
    [],
    [],
)


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class DeckStatsPanel(wx.Panel):
    """Panel that displays deck statistics using an embedded HTML view."""

    def __init__(
        self,
        parent: wx.Window,
        card_manager: CardDataManager | None = None,
        deck_service: DeckService | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.card_manager = card_manager
        self.deck_service = deck_service or get_deck_service()
        self.zone_cards: dict[str, list[dict[str, Any]]] = {}

        self._webview = wx.html2.WebView.New(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._webview.SetPage(_EMPTY_HTML, "")

        # Hidden label kept for test/automation compatibility (summary text readable via GetLabel)
        self.summary_label = wx.StaticText(self, label="No deck loaded.")
        self.summary_label.Hide()

    # ── Public API ──────────────────────────────────────────────────────────

    def update_stats(self, deck_text: str, zone_cards: dict[str, list[dict[str, Any]]]) -> None:
        self.zone_cards = zone_cards

        if not deck_text.strip():
            self.summary_label.SetLabel("No deck loaded.")
            self._webview.SetPage(_EMPTY_HTML, "")
            return

        stats = self.deck_service.analyze_deck(deck_text)
        land_count, mdfc_count = self._count_lands()
        total_land_count = land_count + mdfc_count

        land_label = f"{land_count} land{'s' if land_count != 1 else ''}"
        if mdfc_count:
            land_label += f" + {mdfc_count} MDFC{'s' if mdfc_count != 1 else ''}"
        summary = (
            f"Mainboard: {stats['mainboard_count']} cards ({stats['unique_mainboard']} unique)"
            f"  |  Sideboard: {stats['sideboard_count']} cards ({stats['unique_sideboard']} unique)"
            f"  |  Lands: {land_label}"
        )

        self.summary_label.SetLabel(summary)

        html = _build_html(
            summary,
            self._curve_items(),
            self._color_items(),
            self._type_items(),
            self._hand_items(stats["mainboard_count"], total_land_count),
        )
        self._webview.SetPage(html, "")

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        self.card_manager = card_manager

    def clear(self) -> None:
        self.summary_label.SetLabel("No deck loaded.")
        self._webview.SetPage(_EMPTY_HTML, "")

    # ── Private helpers ─────────────────────────────────────────────────────

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
        """Build mana curve data items."""
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
        """Build color share data items."""
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
        """Build card type data items (all types always shown, zero-count ones dimmed)."""
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
        """Build opening-hand land probability data items."""
        deck_size = round(deck_size)
        land_count = round(land_count)
        if deck_size <= 0:
            return []

        hand_size = STATS_HAND_SIZE
        probs = [
            _hypergeometric_exactly(deck_size, land_count, hand_size, k) * 100
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
