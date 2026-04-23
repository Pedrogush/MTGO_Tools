"""Event handlers, worker threads, and UI-mutation methods for the metagame analysis viewer."""

from __future__ import annotations

import threading
from datetime import date, datetime
from html import escape
from typing import Any

import wx
import wx.html
from loguru import logger
from matplotlib.axes import Axes
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

from repositories.metagame_repository import get_metagame_repository


class MetagameAnalysisHandlersMixin:
    """Callbacks, data workers, and UI-mutation helpers for :class:`MetagameAnalysisFrame`."""

    current_format: str
    current_days: int
    base_day_offset: int
    current_data: dict[str, int]
    previous_data: dict[str, int]
    stats_data: dict[str, Any]
    min_days: int
    max_days: int
    max_day_offset: int
    format_choice: wx.Choice
    refresh_button: wx.Button
    days_prev_button: wx.Button
    days_next_button: wx.Button
    offset_prev_button: wx.Button
    offset_next_button: wx.Button
    days_value_box: wx.Panel
    days_value_label: wx.StaticText
    offset_value_box: wx.Panel
    offset_value_label: wx.StaticText
    status_label: wx.StaticText
    figure: Figure
    canvas: FigureCanvas
    ax: Axes
    changes_html: wx.html.HtmlWindow

    def on_format_change(self, event: wx.CommandEvent) -> None:
        self.current_format = self.format_choice.GetStringSelection().lower()
        self.refresh_data()

    def on_days_decrease(self, event: wx.CommandEvent) -> None:
        if self.current_days <= self.min_days:
            return
        self.current_days -= 1
        self._sync_navigation_controls()
        self.update_visualization()

    def on_days_increase(self, event: wx.CommandEvent) -> None:
        if self.current_days >= self.max_days:
            return
        self.current_days += 1
        self._sync_navigation_controls()
        self.update_visualization()

    def on_offset_decrease(self, event: wx.CommandEvent) -> None:
        if self.base_day_offset <= 0:
            return
        self.base_day_offset -= 1
        self._sync_navigation_controls()
        self.update_visualization()

    def on_offset_increase(self, event: wx.CommandEvent) -> None:
        if self.base_day_offset >= self.max_day_offset:
            return
        self.base_day_offset += 1
        self._sync_navigation_controls()
        self.update_visualization()

    def refresh_data(self) -> None:
        if not self or not self.IsShown():
            return
        self._set_busy(True, self._t("metagame.status.fetching"))
        logger.info(f"Starting metagame data fetch for format: {self.current_format}")

        def worker() -> None:
            try:
                logger.debug(f"Worker thread started for {self.current_format}")
                stats = get_metagame_repository().get_stats_for_format(self.current_format)
                logger.info(f"Successfully loaded archetype stats for {self.current_format}")
                logger.debug(f"Stats keys: {list(stats.keys())}")
                wx.CallAfter(self._populate_data, stats)
            except Exception as exc:
                logger.exception(f"Failed to fetch metagame data for {self.current_format}")
                wx.CallAfter(self._handle_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_error(self, message: str) -> None:
        logger.error(f"_handle_error called with message: {message}")
        if not self or not self.IsShown():
            logger.warning("Widget not shown, skipping error display")
            return
        self._set_busy(False, self._t("metagame.status.error", message=message))

    def _populate_data(self, stats: dict[str, Any]) -> None:
        logger.info(f"_populate_data called with stats for format: {self.current_format}")
        if not self or not self.IsShown():
            logger.warning("Widget not shown, skipping populate")
            return

        try:
            self.stats_data = stats
            format_stats = stats.get(self.current_format, {})
            self._set_default_day_offset(format_stats)
            archetype_count = len([k for k in format_stats.keys() if k != "timestamp"])
            logger.info(f"Found {archetype_count} archetypes in data")
            self._set_busy(False, self._t("metagame.loaded", count=archetype_count))
            self.update_visualization()
        except Exception as exc:
            logger.exception(f"Error processing metagame data:\n{exc}")
            self._set_busy(False, "Error processing metagame data")

    def _set_default_day_offset(self, format_stats: dict[str, Any]) -> None:
        today = datetime.now().date()
        daily_totals: dict[date, int] = {}

        for archetype_name, archetype_data in format_stats.items():
            if archetype_name == "timestamp":
                continue

            results = archetype_data.get("results", {})
            for date_str, count in results.items():
                try:
                    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if parsed > today:
                    continue
                daily_totals[parsed] = daily_totals.get(parsed, 0) + int(count)

        if not daily_totals:
            self.base_day_offset = 0
            self.max_day_offset = 30
            self._sync_navigation_controls()
            return

        non_empty_dates = [day for day, total in daily_totals.items() if total > 0]
        available_dates = non_empty_dates or list(daily_totals.keys())
        latest_data_date = max(available_dates)
        earliest_data_date = min(available_dates)

        self.base_day_offset = max(0, (today - latest_data_date).days)
        self.max_day_offset = max(self.base_day_offset, (today - earliest_data_date).days)
        self._sync_navigation_controls()

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

    def _sync_navigation_controls(self) -> None:
        self.days_value_label.SetLabel(str(self.current_days))
        self.offset_value_label.SetLabel(str(self.base_day_offset))
        self.days_value_box.Layout()
        self.offset_value_box.Layout()
        self.days_prev_button.Enable(self.current_days > self.min_days)
        self.days_next_button.Enable(self.current_days < self.max_days)
        self.offset_prev_button.Enable(self.base_day_offset > 0)
        self.offset_next_button.Enable(self.base_day_offset < self.max_day_offset)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        logger.debug(f"_set_busy called: busy={busy}, message={message}")
        self.refresh_button.Enable(not busy)
        self.days_prev_button.Enable((not busy) and self.current_days > self.min_days)
        self.days_next_button.Enable((not busy) and self.current_days < self.max_days)
        self.offset_prev_button.Enable((not busy) and self.base_day_offset > 0)
        self.offset_next_button.Enable((not busy) and self.base_day_offset < self.max_day_offset)

        if message:
            self.status_label.SetLabel(message)
        elif busy:
            self.status_label.SetLabel(self._t("research.loading_archetypes"))
        else:
            self.status_label.SetLabel(self._t("app.status.ready"))

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()
