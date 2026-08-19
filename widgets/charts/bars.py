"""Stateless sorted-bar-chart rendering, in two dialects.

Phase 5 replaced the metagame pie with a sorted horizontal bar chart. The chart
has to render on machines that have the WebView2 runtime *and* on machines that
do not, so the same data is emitted twice:

* :func:`build_webview_page` — modern CSS, rendered by ``wx.html2.WebView``. Same
  dialect as :mod:`widgets.panels.deck_stats_panel.stats_chart_html`, so the app
  has one charting stack wherever WebView2 is available.
The non-WebView rendering is *not* a second HTML dialect. That was the first
attempt and it did not work: screenshotted, ``wx.html.HtmlWindow`` drew every
label and no bars, because it ignores ``bgcolor`` on a table, collapses an empty
cell and ignores ``height`` on ``<td>``. The fallback is painted with a ``wx.DC``
instead — see :mod:`widgets.charts.painter`. :func:`build_bars` stays shared, so
both paths get the same ordering, aggregation and palette.

Why bars and not a pie: with 11 near-equal slices, angle and area convey nothing
and the reader falls back to reading the labels, which is the encoding a bar
chart gives directly. Length from a common baseline is the most accurately
decoded visual channel there is; colour here is decoration, so the palette is
allowed to run out.
"""

from __future__ import annotations

from html import escape
from typing import NamedTuple

from utils.constants.theme import (
    CHART_CATEGORICAL,
    CHART_OTHER,
    SURFACE_ALT,
    SURFACE_BASE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    chart_palette,
    css_font_size,
    to_hex,
)
from utils.constants.ui_layout import (
    CHART_BAR_MIN_WIDTH_PCT,
    CHART_BAR_RADIUS,
    CHART_BAR_TRACK_HEIGHT,
    CHART_LABEL_COLUMN_PCT,
    CHART_ROW_HEIGHT,
    CHART_VALUE_COLUMN_PCT,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)


class ChartBar(NamedTuple):
    """One row of a sorted bar chart.

    ``fraction`` is the bar's length as a share of the longest bar (0..1), not of
    the total: a bar chart's job is comparison between rows, so the longest row
    should fill the track whatever its absolute value.
    """

    label: str
    value_text: str
    fraction: float
    colour: str


#: Rows past this are aggregated into a single "Other" bar. Chosen so the chart
#: stays taller than CHART_ROW_HEIGHT * rows in the metagame window's chart pane
#: at its minimum size, and because a long-tail archetype at 0.4% is not a thing
#: anyone compares by length.
MAX_BARS = 12

#: How many rows get a hue of their own. The palette is seven hues plus a
#: neutral; past the seventh row colour stops identifying anything, so the tail
#: and the aggregated remainder share the neutral.
CHART_HUE_COUNT = len(CHART_CATEGORICAL)


def build_bars(
    entries: list[tuple[str, float]],
    *,
    other_label: str = "Other",
    max_bars: int = MAX_BARS,
    value_format: str = "{:.1f}%",
) -> list[ChartBar]:
    """Sort ``(label, value)`` pairs descending and assign colours.

    Zero-valued entries are dropped rather than drawn: a zero-length bar carries
    no information and, in the pie this replaces, a zero-angle wedge still got a
    leader label — which is how the old chart ended up with a pile of overlapping
    "(0.0%)" strings stacked at one o'clock.

    Colour assignment is deliberately partial. The palette holds seven hues plus a
    neutral, so the top seven rows get a hue each and everything below them — the
    tail and the aggregated remainder — takes the neutral. Beyond eight categories
    colour cannot identify anything, and here it does not have to: rank is carried
    by vertical position and magnitude by bar length.
    """
    ranked = sorted(
        ((label, value) for label, value in entries if value > 0),
        key=lambda item: (-item[1], item[0]),
    )
    if not ranked:
        return []

    if len(ranked) > max_bars:
        head = ranked[:max_bars]
        tail_total = sum(value for _, value in ranked[max_bars:])
        if tail_total > 0:
            head = [*head, (other_label, tail_total)]
        ranked = head

    hues = [to_hex(rgb) for rgb in chart_palette(CHART_HUE_COUNT)]
    neutral = to_hex(CHART_OTHER)
    top = max(value for _, value in ranked)

    bars: list[ChartBar] = []
    for index, (label, value) in enumerate(ranked):
        colour = hues[index] if index < len(hues) else neutral
        bars.append(
            ChartBar(
                label=label,
                value_text=value_format.format(value),
                fraction=(value / top) if top else 0.0,
                colour=colour,
            )
        )
    return bars


def _bar_width_pct(fraction: float) -> float:
    """Track fill percentage, floored so a tiny-but-present row stays visible."""
    return max(CHART_BAR_MIN_WIDTH_PCT, min(1.0, fraction) * 100.0)


# ---------------------------------------------------------------------------
# WebView (CSS) dialect
# ---------------------------------------------------------------------------

_WEBVIEW_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  height: 100%;
  background: {to_hex(SURFACE_BASE)};
  color: {to_hex(TEXT_PRIMARY)};
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  font-size: {css_font_size("body")}px;
  overflow: hidden;
}}
.root {{
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: {SPACE_MD}px;
  gap: {SPACE_XS}px;
}}
.title {{
  font-size: {css_font_size("heading")}px;
  font-weight: 600;
  flex-shrink: 0;
}}
.subtitle {{
  font-size: {css_font_size("caption")}px;
  color: {to_hex(TEXT_SECONDARY)};
  flex-shrink: 0;
  margin-bottom: {SPACE_SM}px;
}}
.rows {{
  display: flex;
  flex-direction: column;
  gap: {SPACE_XS}px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}}
.row {{
  display: flex;
  align-items: center;
  gap: {SPACE_SM}px;
  height: {CHART_ROW_HEIGHT}px;
  flex-shrink: 0;
}}
.label {{
  width: {CHART_LABEL_COLUMN_PCT}%;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: right;
}}
.track {{
  flex: 1;
  height: {CHART_BAR_TRACK_HEIGHT}px;
  background: {to_hex(SURFACE_ALT)};
  border-radius: {CHART_BAR_RADIUS}px;
}}
.bar {{
  height: 100%;
  border-radius: {CHART_BAR_RADIUS}px;
}}
.value {{
  width: {CHART_VALUE_COLUMN_PCT}%;
  flex-shrink: 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: {to_hex(TEXT_PRIMARY)};
}}
.empty {{
  color: {to_hex(TEXT_SECONDARY)};
  padding: {SPACE_MD}px 0;
  font-size: {css_font_size("heading")}px;
}}
"""


def build_webview_page(title: str, subtitle: str, bars: list[ChartBar], empty_text: str) -> str:
    """A full HTML document for ``wx.html2.WebView``."""
    if not bars:
        body = f'<div class="empty">{escape(empty_text)}</div>'
    else:
        rows = "".join(
            f'<div class="row">'
            f'<div class="label" title="{escape(bar.label, quote=True)}">{escape(bar.label)}</div>'
            f'<div class="track"><div class="bar" style="width:{_bar_width_pct(bar.fraction):.2f}%;'
            f'background:{bar.colour};"></div></div>'
            f'<div class="value">{escape(bar.value_text)}</div>'
            f"</div>"
            for bar in bars
        )
        body = f'<div class="rows">{rows}</div>'
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_WEBVIEW_CSS}</style></head><body><div class='root'>"
        f'<div class="title">{escape(title)}</div>'
        f'<div class="subtitle">{escape(subtitle)}</div>'
        f"{body}</div></body></html>"
    )
