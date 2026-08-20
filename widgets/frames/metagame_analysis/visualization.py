"""Share-chart and changes-panel rendering for the metagame analysis viewer.

The share chart was a matplotlib pie until phase 5. It is now a sorted horizontal
bar chart drawn by :mod:`widgets.charts`, the same renderer the deck stats panel
uses, so the app has one charting stack instead of two.
"""

from __future__ import annotations

from html import escape
from typing import Any

import wx.html
from loguru import logger

from widgets.charts import ChartView, build_bars


class MetagameVisualizationMixin:
    """Chart drawing and changes-display rendering for :class:`MetagameAnalysisFrame`."""

    current_format: str
    current_days: int
    base_day_offset: int
    current_data: dict[str, int]
    previous_data: dict[str, int]
    stats_data: dict[str, Any]
    chart: ChartView
    changes_html: wx.html.HtmlWindow

    def update_visualization(self) -> None:
        logger.debug(
            f"update_visualization called, offset={self.base_day_offset}, days={self.current_days}"
        )
        if not self.stats_data:
            logger.warning("No stats data available for visualization")
            return

        self.current_data = self._aggregate_for_days(self.current_days, self.base_day_offset)
        logger.debug(
            f"Current data aggregated: {len(self.current_data)} archetypes, "
            f"total decks: {sum(self.current_data.values())}"
        )

        previous_offset = self.base_day_offset + self.current_days
        self.previous_data = self._aggregate_for_days(self.current_days, previous_offset)
        logger.debug(
            f"Previous data aggregated: {len(self.previous_data)} archetypes, "
            f"total decks: {sum(self.previous_data.values())}"
        )

        self._draw_share_chart()
        self._update_changes_display()

    def _draw_share_chart(self) -> None:
        """Render the archetype share as a sorted horizontal bar chart.

        Everything the pie encoded twice is now encoded once: the share is the bar
        length, and the number beside it is the exact value. The pie printed the
        percentage inside the wedge *and* repeated it in the leader label, drew
        both in a light grey that measured 1.10:1 against the pastel fills, and
        gave a zero-share archetype a zero-angle wedge with a full leader label —
        which is why every capture of it has a pile of overlapping "(0.0%)"
        strings stacked at one o'clock.
        """
        percentages = self._calculate_percentages(self.current_data)
        bars = build_bars(
            list(percentages.items()),
            other_label=self._t("metagame.chart.other"),
        )
        self.chart.set_chart(
            title=self._t("metagame.chart.title", format=self.current_format.title()),
            subtitle=self._period_description(),
            bars=bars,
            empty_text=self._t("metagame.chart.no_data"),
        )

    def _period_description(self) -> str:
        """The human-readable window this chart covers.

        Split out of the title because the title named the format and the period
        in one string, which made "Modern Metagame (Last 1 day(s))" — the
        programmer plural leaking to the user — impossible to fix without also
        re-composing the format name.
        """
        if self.base_day_offset == 0:
            if self.current_days == 1:
                return self._t("metagame.period.last_day")
            return self._t("metagame.period.last_days", count=self.current_days)
        end_day = self.base_day_offset
        start_day = self.base_day_offset + self.current_days - 1
        if start_day == end_day:
            if end_day == 1:
                return self._t("metagame.period.day_ago")
            return self._t("metagame.period.days_ago", count=end_day)
        return self._t("metagame.period.range_days_ago", start=start_day, end=end_day)

    def _update_changes_display(self) -> None:
        if not self.current_data or not self.previous_data:
            self._set_changes_html(
                self._build_changes_html(
                    self._t("metagame.label.changes"),
                    [f"<div class='empty'>{escape(self._t('metagame.changes.no_data'))}</div>"],
                )
            )
            return

        previous_total = sum(self.previous_data.values())
        if previous_total == 0:
            self._set_changes_html(
                self._build_changes_html(
                    self._t("metagame.label.changes"),
                    [
                        "<div class='empty'>"
                        f"{escape(self._t('metagame.changes.previous_missing'))}"
                        "</div>"
                    ],
                )
            )
            return

        current_pct = self._calculate_percentages(self.current_data)
        previous_pct = self._calculate_percentages(self.previous_data)

        all_archetypes = set(current_pct.keys()) | set(previous_pct.keys())
        changes: dict[str, float] = {}
        for archetype in all_archetypes:
            current = current_pct.get(archetype, 0.0)
            previous = previous_pct.get(archetype, 0.0)
            changes[archetype] = current - previous

        sorted_changes = sorted(changes.items(), key=lambda x: abs(x[1]), reverse=True)

        prev_start = self.base_day_offset + self.current_days
        prev_end = self.base_day_offset + self.current_days * 2 - 1
        if prev_start != prev_end:
            prev_desc = self._t("metagame.period.range_days_ago", start=prev_end, end=prev_start)
        elif prev_start == 1:
            prev_desc = self._t("metagame.period.day_ago")
        else:
            prev_desc = self._t("metagame.period.days_ago", count=prev_start)

        cards: list[str] = []
        for archetype, change in sorted_changes[:15]:
            if abs(change) < 0.1:
                continue
            current_val = current_pct.get(archetype, 0.0)
            previous_val = previous_pct.get(archetype, 0.0)
            cards.append(
                self._build_change_card(
                    archetype,
                    change,
                    current_val=current_val,
                    previous_val=previous_val,
                )
            )

        if not cards:
            cards.append(f"<div class='empty'>{escape(self._t('metagame.changes.none'))}</div>")

        self._set_changes_html(
            self._build_changes_html(
                self._t("metagame.changes.vs_period", period=prev_desc),
                cards,
            )
        )

    def _set_changes_html(self, html_content: str) -> None:
        self.changes_html.SetPage(html_content)
