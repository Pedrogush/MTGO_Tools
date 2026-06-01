"""Pie-chart and changes-panel rendering for the metagame analysis viewer."""

from __future__ import annotations

from html import escape
from typing import Any

import wx.html
from loguru import logger
from matplotlib.axes import Axes
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure


class MetagameVisualizationMixin:
    """Chart drawing and changes-display rendering for :class:`MetagameAnalysisFrame`."""

    current_format: str
    current_days: int
    base_day_offset: int
    current_data: dict[str, int]
    previous_data: dict[str, int]
    stats_data: dict[str, Any]
    figure: Figure
    canvas: FigureCanvas
    ax: Axes
    changes_html: wx.html.HtmlWindow

    def update_visualization(self) -> None:
        logger.debug(
            f"update_visualization called, offset={self.base_day_offset}, "
            f"days={self.current_days}"
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

        self._draw_pie_chart()
        self._update_changes_display()

    def _draw_pie_chart(self) -> None:
        self.ax.clear()

        if not self.current_data or sum(self.current_data.values()) == 0:
            self.ax.axis("off")
            self.ax.text(
                0.5,
                0.5,
                self._t("metagame.chart.no_data"),
                ha="center",
                va="center",
                color="#b9bfca",
                fontsize=14,
            )
            self.canvas.draw()
            return

        percentages = self._calculate_percentages(self.current_data)
        sorted_archetypes = sorted(percentages.items(), key=lambda x: x[1], reverse=True)

        top_archetypes = sorted_archetypes[:10]
        other_pct = sum(pct for _, pct in sorted_archetypes[10:])

        labels = [f"{arch} ({pct:.1f}%)" for arch, pct in top_archetypes]
        sizes = [pct for _, pct in top_archetypes]

        if other_pct > 0:
            labels.append(f"Other ({other_pct:.1f}%)")
            sizes.append(other_pct)

        colors = [
            "#FF6B6B",
            "#4ECDC4",
            "#45B7D1",
            "#FFA07A",
            "#98D8C8",
            "#F7DC6F",
            "#BB8FCE",
            "#85C1E2",
            "#F8B88B",
            "#ABEBC6",
            "#D5DBDB",
        ]

        self.ax.pie(
            sizes,
            labels=labels,
            colors=colors[: len(sizes)],
            startangle=90,
            autopct="%1.1f%%",
            pctdistance=0.72,
            labeldistance=1.02,
            textprops={"color": "#ecececec", "fontsize": 7},
        )

        self.ax.axis("equal")
        if self.base_day_offset == 0:
            period_desc = self._t("metagame.period.last_days", count=self.current_days)
        else:
            end_day = self.base_day_offset
            start_day = self.base_day_offset + self.current_days - 1
            if start_day == end_day:
                period_desc = self._t("metagame.period.days_ago", count=end_day)
            else:
                period_desc = self._t(
                    "metagame.period.range_days_ago", start=start_day, end=end_day
                )
        title = f"{self.current_format.title()} Metagame ({period_desc})"
        self.ax.set_title(title, color="#ecececec", fontsize=12, pad=20)

        self.canvas.draw()

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
        if prev_start == prev_end:
            prev_desc = self._t("metagame.period.days_ago", count=prev_start)
        else:
            prev_desc = self._t("metagame.period.range_days_ago", start=prev_end, end=prev_start)

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
