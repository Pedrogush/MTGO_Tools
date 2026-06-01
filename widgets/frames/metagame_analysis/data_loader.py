"""Worker-thread data loading and population for the metagame analysis viewer."""

from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Any

import wx
from loguru import logger


class MetagameDataLoaderMixin:
    """Background fetch, error handling, and stats population for :class:`MetagameAnalysisFrame`."""

    current_format: str
    base_day_offset: int
    max_day_offset: int
    stats_data: dict[str, Any]

    def refresh_data(self) -> None:
        if not self or not self.IsShown():
            return
        self._set_busy(True, self._t("metagame.status.fetching"))
        logger.info(f"Starting metagame data fetch for format: {self.current_format}")

        def worker() -> None:
            try:
                logger.debug(f"Worker thread started for {self.current_format}")
                stats = self.controller.metagame_service.get_stats_for_format(self.current_format)
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
