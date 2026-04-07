"""Metagame analysis widget for visualizing archetype distribution over time."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import threading

import wx
import wx.html
from loguru import logger
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

from repositories.metagame_repository import get_metagame_repository
from utils.constants import DARK_ACCENT, DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import translate


class MetagameAnalysisFrame(wx.Frame):
    """Widget for displaying metagame archetype distribution and changes over time."""

    def __init__(self, parent: wx.Window | None = None, locale: str | None = None) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.metagame_analysis"),
            size=(980, 660),
            style=style,
        )
        self._locale = locale

        self.current_format: str = "modern"
        self.current_days: int = 1
        self.base_day_offset: int = 0
        self.current_data: dict[str, int] = {}
        self.previous_data: dict[str, int] = {}
        self.stats_data: dict[str, Any] = {}

        self.min_days: int = 1
        self.max_days: int = 7
        self.max_day_offset: int = 30

        self._build_ui()
        self.Centre(wx.BOTH)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallAfter(self.refresh_data)

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(main_sizer)

        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(toolbar, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        format_label = wx.StaticText(panel, label=self._t("metagame.label.format"))
        format_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(format_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.format_choice = wx.Choice(
            panel,
            choices=[
                "Modern",
                "Standard",
                "Pioneer",
                "Legacy",
                "Vintage",
                "Pauper",
            ],
        )
        self.format_choice.SetSelection(0)
        self.format_choice.SetBackgroundColour(DARK_ALT)
        self.format_choice.SetForegroundColour(LIGHT_TEXT)
        self.format_choice.Bind(wx.EVT_CHOICE, self.on_format_change)
        toolbar.Add(self.format_choice, 0, wx.RIGHT, 12)

        time_window_label = wx.StaticText(panel, label=self._t("metagame.label.time_window"))
        time_window_label.SetForegroundColour(SUBDUED_TEXT)
        time_window_tooltip = self._t("metagame.tooltip.time_window")
        time_window_label.SetToolTip(time_window_tooltip)
        toolbar.Add(time_window_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.days_prev_button = wx.Button(panel, label="←", size=(28, 26))
        self._stylize_button(self.days_prev_button)
        self.days_prev_button.Bind(wx.EVT_BUTTON, self.on_days_decrease)
        self.days_prev_button.SetToolTip(time_window_tooltip)
        toolbar.Add(self.days_prev_button, 0, wx.RIGHT, 3)

        self.days_value_box, self.days_value_label = self._create_value_badge(
            panel, str(self.current_days), tooltip=time_window_tooltip
        )
        toolbar.Add(self.days_value_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)

        self.days_next_button = wx.Button(panel, label="→", size=(28, 26))
        self._stylize_button(self.days_next_button)
        self.days_next_button.Bind(wx.EVT_BUTTON, self.on_days_increase)
        self.days_next_button.SetToolTip(time_window_tooltip)
        toolbar.Add(self.days_next_button, 0, wx.RIGHT, 12)

        day_label = wx.StaticText(panel, label=self._t("metagame.label.starting_from"))
        day_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(day_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.offset_prev_button = wx.Button(panel, label="←", size=(28, 26))
        self._stylize_button(self.offset_prev_button)
        self.offset_prev_button.Bind(wx.EVT_BUTTON, self.on_offset_decrease)
        toolbar.Add(self.offset_prev_button, 0, wx.RIGHT, 3)

        self.offset_value_box, self.offset_value_label = self._create_value_badge(
            panel, str(self.base_day_offset)
        )
        toolbar.Add(self.offset_value_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)

        self.offset_next_button = wx.Button(panel, label="→", size=(28, 26))
        self._stylize_button(self.offset_next_button)
        self.offset_next_button.Bind(wx.EVT_BUTTON, self.on_offset_increase)
        toolbar.Add(self.offset_next_button, 0, wx.RIGHT, 12)

        self.refresh_button = wx.Button(panel, label=self._t("metagame.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_data())
        toolbar.Add(self.refresh_button, 0, wx.RIGHT, 8)

        toolbar.AddStretchSpacer(1)

        self.status_label = wx.StaticText(panel, label=self._t("app.status.ready"))
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(self.status_label, 0, wx.ALIGN_CENTER_VERTICAL)

        content_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(content_sizer, 1, wx.ALL | wx.EXPAND, 8)

        self.figure = Figure(figsize=(6, 5), facecolor="#14161b")
        self.canvas = FigureCanvas(panel, -1, self.figure)
        self.canvas.SetBackgroundColour(DARK_PANEL)
        content_sizer.Add(self.canvas, 1, wx.EXPAND | wx.RIGHT, 8)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#14161b")

        right_panel = wx.Panel(panel)
        right_panel.SetBackgroundColour(DARK_PANEL)
        right_panel.SetMinSize((250, -1))
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_panel.SetSizer(right_sizer)
        content_sizer.Add(right_panel, 0, wx.EXPAND)

        changes_label = wx.StaticText(right_panel, label=self._t("metagame.label.changes"))
        changes_label.SetForegroundColour(LIGHT_TEXT)
        font = changes_label.GetFont()
        font.MakeBold()
        font.PointSize += 2
        changes_label.SetFont(font)
        right_sizer.Add(changes_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        self.changes_html = wx.html.HtmlWindow(right_panel, style=wx.BORDER_NONE)
        self.changes_html.SetBackgroundColour(DARK_ALT)
        right_sizer.Add(self.changes_html, 1, wx.ALL | wx.EXPAND, 8)

        self._sync_navigation_controls()

    def _stylize_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _create_value_badge(
        self, parent: wx.Window, value: str, *, tooltip: str | None = None
    ) -> tuple[wx.Panel, wx.StaticText]:
        badge = wx.Panel(parent, size=(34, 24))
        badge.SetBackgroundColour(DARK_ALT)
        sizer = wx.BoxSizer(wx.VERTICAL)
        badge.SetSizer(sizer)

        sizer.AddStretchSpacer(1)
        label = wx.StaticText(badge, label=value, style=wx.ALIGN_CENTER_HORIZONTAL)
        label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
        sizer.AddStretchSpacer(1)

        if tooltip:
            badge.SetToolTip(tooltip)
            label.SetToolTip(tooltip)
        return badge, label

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

    def _aggregate_for_days(self, days: int, base_offset: int = 0) -> dict[str, int]:
        """Aggregate deck counts for the specified number of days starting from base_offset."""
        format_stats = self.stats_data.get(self.current_format, {})
        today = datetime.now().date()

        archetype_counts = Counter()
        for archetype_name, archetype_data in format_stats.items():
            if archetype_name == "timestamp":
                continue

            results = archetype_data.get("results", {})
            for day_offset in range(base_offset, base_offset + days):
                date_str = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                count = results.get(date_str, 0)
                archetype_counts[archetype_name] += count

        return dict(archetype_counts)

    def update_visualization(self) -> None:
        logger.debug(
            f"update_visualization called, offset={self.base_day_offset}, days={self.current_days}"
        )
        if not self.stats_data:
            logger.warning("No stats data available for visualization")
            return

        self.current_data = self._aggregate_for_days(self.current_days, self.base_day_offset)
        logger.debug(
            f"Current data aggregated: {len(self.current_data)} archetypes, total decks: {sum(self.current_data.values())}"
        )

        previous_offset = self.base_day_offset + self.current_days
        self.previous_data = self._aggregate_for_days(self.current_days, previous_offset)
        logger.debug(
            f"Previous data aggregated: {len(self.previous_data)} archetypes, total decks: {sum(self.previous_data.values())}"
        )

        self._draw_pie_chart()
        self._update_changes_display()

    def _calculate_percentages(self, counts: dict[str, int]) -> dict[str, float]:
        """Calculate percentage share for each archetype."""
        total = sum(counts.values())
        if total == 0:
            return {}
        return {archetype: (count / total) * 100 for archetype, count in counts.items()}

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

    def _build_change_card(
        self, archetype: str, change: float, *, current_val: float, previous_val: float
    ) -> str:
        if change >= 2.0:
            arrow = "▲▲"
            direction_class = "up"
        elif change > 0:
            arrow = "▲"
            direction_class = "up"
        elif change <= -2.0:
            arrow = "▼▼"
            direction_class = "down"
        else:
            arrow = "▼"
            direction_class = "down"

        arrow_color = "#43d17b" if direction_class == "up" else "#ff6464"
        dark_panel = self._rgb_to_hex(DARK_PANEL)
        dark_accent = self._rgb_to_hex(DARK_ACCENT)
        light_text = self._rgb_to_hex(LIGHT_TEXT)
        subdued_text = self._rgb_to_hex(SUBDUED_TEXT)

        return f"""
<table cellspacing='0' cellpadding='0' width='100%'>
  <tr>
    <td align='center'>
      <table cellspacing='1' cellpadding='0' bgcolor='{dark_accent}' width='96%'>
        <tr>
          <td bgcolor='{dark_panel}'>
            <table cellspacing='0' cellpadding='4' width='100%'>
              <tr>
                <td><font color='{arrow_color}'><b>{arrow}</b></font></td>
                <td><font color='{light_text}'><b>{escape(archetype)}</b></font></td>
                <td align='right'><font color='{arrow_color}'><b>{change:+.1f}%</b></font></td>
              </tr>
              <tr>
                <td colspan='3'>
                  <font color='{subdued_text}' size='2'>
                    {escape(self._t('metagame.changes.now'))} {current_val:.1f}% | {escape(self._t('metagame.changes.previous'))} {previous_val:.1f}%
                  </font>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""

    def _build_changes_html(self, title: str, cards: list[str]) -> str:
        cards_html = "<br/>".join(cards)
        dark_alt = self._rgb_to_hex(DARK_ALT)
        subdued_text = self._rgb_to_hex(SUBDUED_TEXT)
        light_text = self._rgb_to_hex(LIGHT_TEXT)
        return f"""
<html>
<body bgcolor='{dark_alt}'>
<font face='Segoe UI, Arial, sans-serif' color='{subdued_text}'><b>{escape(title)}</b></font>
<br/><br/>
<font face='Segoe UI, Arial, sans-serif' color='{light_text}'>
{cards_html}
</font>
</body>
</html>
"""

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

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


def main() -> None:
    """Launch the metagame analysis widget as a standalone application."""
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = MetagameAnalysisFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()


__all__ = ["MetagameAnalysisFrame"]
