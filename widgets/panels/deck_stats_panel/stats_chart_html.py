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
from utils.constants.ui_images import STATS_MANA_SVG_DISPLAY_SIZE
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
from widgets.panels.deck_stats_panel.stats_constants import (
    _COLOR_SVG_HTML,
    _CURVE_COLD,
    _CURVE_WARM,
)


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
