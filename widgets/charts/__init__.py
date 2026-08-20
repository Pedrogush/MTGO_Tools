"""Shared charting: one bar-chart builder with a guaranteed rendering backend."""

from __future__ import annotations

from widgets.charts.bars import (
    MAX_BARS,
    ChartBar,
    build_bars,
    build_webview_page,
)
from widgets.charts.painter import BarChartPanel, ChartSection, SparkBarPanel
from widgets.charts.view import ChartView, create_webview, webview_disabled_by_env

__all__ = [
    "MAX_BARS",
    "BarChartPanel",
    "ChartBar",
    "ChartSection",
    "ChartView",
    "SparkBarPanel",
    "build_bars",
    "build_webview_page",
    "create_webview",
    "webview_disabled_by_env",
]
