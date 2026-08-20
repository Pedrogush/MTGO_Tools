"""Stateless HTML/CSS chart-rendering subsystem for the deck stats panel.

Takes plain tuples and emits HTML; has no panel dependency and is
independently unit-testable.
"""

from __future__ import annotations

from html import escape

from utils.constants.deck_rules import (
    STATS_CURVE_COLOUR_LERP_MAX_CMC,
    STATS_CURVE_X_CMC_FOR_COLOUR,
)
from utils.constants.theme import (
    BORDER_SUBTLE,
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_PLACEHOLDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    chart_ramp,
    to_hex,
)
from utils.constants.ui_images import STATS_MANA_SVG_DISPLAY_SIZE
from utils.constants.ui_layout import (
    SPACE_SM,
    SPACE_XS,
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
    STATS_HBAR_TRACK_MIN_WIDTH,
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
from widgets.charts.bars import ChartBar
from widgets.panels.deck_stats_panel.stats_constants import _COLOR_SVG_HTML


def _curve_colour(bucket: str) -> str:
    if bucket == "X":
        cmc = STATS_CURVE_X_CMC_FOR_COLOUR
    elif bucket.endswith("+") and bucket[:-1].isdigit():
        cmc = int(bucket[:-1])
    elif bucket.isdigit():
        cmc = int(bucket)
    else:
        cmc = 0
    return to_hex(chart_ramp(cmc / STATS_CURVE_COLOUR_LERP_MAX_CMC))


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

# Phase 5 put this panel on screen for the first time and two of its hand-picked
# CSS colours turned out to fail AA against the chart surface: #8B929E chart
# titles / axis labels / counts measured 4.26:1, and the #555 "no data" text
# measured 1.79:1. Both are now theme tokens, which the contrast suite covers.
_PAGE_BG = to_hex(SURFACE_PANEL)
_CARD_BG = to_hex(SURFACE_ALT)
_TRACK_BG = to_hex(SURFACE_BASE)
_INK = to_hex(TEXT_PRIMARY)
_MUTED = to_hex(TEXT_SECONDARY)
_FAINT = to_hex(TEXT_PLACEHOLDER)
_BORDER = to_hex(BORDER_SUBTLE)

#: Section headings, in call order. Both builders take them as data so the panel
#: can pass translations in; the defaults keep the builders independently
#: testable without an i18n import.
DEFAULT_CHART_TITLES: tuple[str, str, str, str] = (
    "Mana Curve",
    "Color Share",
    "Card Types",
    "Lands in Opening Hand",
)
_NO_DATA_TEXT = "No data"


_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body {{
  height: 100%;
  background: {_PAGE_BG};
  color: {_INK};
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: {STATS_FONT_SIZE_BODY}px;
  overflow: hidden;
}}

.root {{
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: {SPACE_SM}px;
  gap: {SPACE_SM}px;
}}

/* ── Summary bar ── */
.summary {{
  color: {_MUTED};
  font-size: {STATS_FONT_SIZE_LABEL}px;
  flex-shrink: 0;
  padding: {SPACE_XS}px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

/* ── Top row: three charts side-by-side ── */
.top-row {{
  display: flex;
  gap: {SPACE_SM}px;
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
  background: {_CARD_BG};
  border-radius: {STATS_CHART_BORDER_RADIUS}px;
  padding: {SPACE_SM}px {SPACE_SM}px {SPACE_XS}px {SPACE_SM}px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}}

.chart-title {{
  font-size: {STATS_FONT_SIZE_LABEL}px;
  font-weight: 600;
  color: {_MUTED};
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: {SPACE_XS}px;
  flex-shrink: 0;
}}

/* Card Types is the only horizontal-bar chart up here, so its rows carry a text
   label *and* a bar *and* a count on one line, where the two vertical charts
   only need their bars. An equal third left the label at "Creat..." and the
   track at a hairline. */
.chart-wide {{
  flex: 1.6;
}}

.chart-empty {{
  color: {_FAINT};
  font-style: italic;
  padding: {SPACE_SM}px;
}}

/* ── Vertical bar chart ── */
.vbar-area {{
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: {SPACE_XS}px;
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
  color: {_INK};
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
  color: {_MUTED};
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
  color: {_INK};
  padding: {STATS_TOOLTIP_PADDING};
  border-radius: {STATS_TOOLTIP_BORDER_RADIUS}px;
  white-space: nowrap;
  font-size: {STATS_FONT_SIZE_LABEL}px;
  pointer-events: none;
  z-index: {STATS_TOOLTIP_Z_INDEX};
  border: 1px solid {_BORDER};
}}

/* ── Horizontal bar chart (Card Types) ── */
.hbar-area {{
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  flex: 1;
  min-height: 0;
  gap: {SPACE_XS}px;
  padding-top: 2px;
}}

.hbar-row {{
  display: flex;
  align-items: center;
  gap: {SPACE_SM}px;
  cursor: default;
  position: relative;
  height: {STATS_HBAR_ROW_HEIGHT}px;
  flex-shrink: 0;
}}

.hbar-label {{
  /* Fixed at 82px until phase 5. In the deck stats layout the Card Types chart
     gets a third of the top row -- about 150px -- so an 82px label plus a 28px
     count plus two 8px gaps left the track ~24px wide and the bars rendered as
     hairlines. A max-width lets the label give room back when the chart is
     narrow, and the ellipsis keeps the longest type name ("Planeswalker") from
     wrapping. */
  max-width: {STATS_HBAR_LABEL_WIDTH}px;
  flex: 0 1 auto;
  min-width: 0;
  text-align: left;
  color: {_INK};
  font-size: {STATS_FONT_SIZE_LABEL}px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

.hbar-track {{
  flex: 1 1 auto;
  min-width: {STATS_HBAR_TRACK_MIN_WIDTH}px;
  position: relative;
  height: {STATS_HBAR_TRACK_HEIGHT}px;
  border-radius: {STATS_BAR_BORDER_RADIUS}px;
  background: {_TRACK_BG};
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
  text-align: right;
  font-size: {STATS_FONT_SIZE_LABEL}px;
  color: {_MUTED};
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
    titles: tuple[str, str, str, str] = DEFAULT_CHART_TITLES,
) -> str:
    curve_title, color_title, type_title, hand_title = (escape(t) for t in titles)
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
      <div class="chart-title">{curve_title}</div>
      {curve_html}
    </div>
    <div class="chart">
      <div class="chart-title">{color_title}</div>
      {color_html}
    </div>
    <div class="chart chart-wide">
      <div class="chart-title">{type_title}</div>
      {type_html}
    </div>
  </div>
  <div class="bottom-row">
    <div class="chart" style="height:100%">
      <div class="chart-title">{hand_title}</div>
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
# Painted fallback (no WebView2 runtime)
# ---------------------------------------------------------------------------
# The panel used to have no fallback content at all: when WebView2 was missing it
# logged a warning and left an empty sizer, so the user saw a blank tab. The
# fallback now paints the same four charts with a wx.DC. It loses the tooltips,
# the rounded bars, the mana glyphs and the side-by-side layout, and keeps the
# part that carries the data: labelled bars whose length is the value.
#
# (An HTML fallback through wx.html.HtmlWindow was tried first and drew every
# label and no bars -- see widgets/charts/painter.py.)


def bars_from_ratio_items(
    items: list[tuple[str, str, float, str, str]],
) -> list[ChartBar]:
    """``(label, value_text, raw, colour, tooltip)`` -> bars scaled to the max."""
    if not items:
        return []
    top = max(raw for _, _, raw, _, _ in items) or 1.0
    return [
        ChartBar(label=label, value_text=value_text, fraction=raw / top, colour=colour)
        for label, value_text, raw, colour, _ in items
    ]


def bars_from_count_items(items: list[tuple[str, int, int, str, str]]) -> list[ChartBar]:
    """``(label, count, max_count, colour, tooltip)`` -> bars scaled to the max."""
    if not items:
        return []
    top = max(count for _, count, _, _, _ in items) or 1
    return [
        ChartBar(label=label, value_text=str(count), fraction=count / top, colour=colour)
        for label, count, _max, colour, _ in items
    ]


def build_sections(
    curve_items: list[tuple[str, str, float, str, str]],
    color_items: list[tuple[str, str, float, str, str]],
    type_items: list[tuple[str, int, int, str, str]],
    hand_items: list[tuple[str, str, float, str, str]],
    titles: tuple[str, str, str, str] = DEFAULT_CHART_TITLES,
) -> list[tuple[str, list[ChartBar]]]:
    """The whole panel as ``(section title, bars)`` pairs for the painted view."""
    return [
        (titles[0], bars_from_ratio_items(curve_items)),
        (titles[1], bars_from_ratio_items(color_items)),
        (titles[2], bars_from_count_items(type_items)),
        (titles[3], bars_from_ratio_items(hand_items)),
    ]
