"""The no-WebView2 path, constructed for real.

A machine without the Microsoft Edge WebView2 runtime is the one case where a
silent failure ships to a user who then sees nothing at all -- which is what the
deck stats panel did before phase 5. ``MTGO_TOOLS_DISABLE_WEBVIEW`` makes that
machine reproducible here, so the fallback is exercised rather than assumed.
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from utils.constants.theme import SURFACE_BASE  # noqa: E402
from widgets.charts import ChartView, build_bars  # noqa: E402
from widgets.charts.painter import BarChartPanel, SparkBarPanel  # noqa: E402
from widgets.charts.view import DISABLE_WEBVIEW_ENV  # noqa: E402


@pytest.fixture(name="frame")
def fixture_frame(wx_app):
    frame = wx.Frame(None, size=(600, 400))
    yield frame
    frame.Destroy()


def _children(window: wx.Window, kind: type) -> list[wx.Window]:
    return [child for child in window.GetChildren() if isinstance(child, kind)]


@pytest.mark.usefixtures("wx_app")
def test_chart_view_falls_back_to_a_painted_panel(frame, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DISABLE_WEBVIEW_ENV, "1")
    view = ChartView(frame)
    assert view.uses_webview is False
    assert _children(view, BarChartPanel), "the fallback must produce a real chart surface"


@pytest.mark.usefixtures("wx_app")
def test_the_fallback_renders_the_bars_it_was_given(frame, monkeypatch: pytest.MonkeyPatch) -> None:
    """The first fallback attempt was wxHTML and drew every label and no bars.

    The painted panel has to report content height that grows with the data --
    a chart that lays out to nothing is the same defect in a new place.
    """
    monkeypatch.setenv(DISABLE_WEBVIEW_ENV, "1")
    view = ChartView(frame)
    panel = _children(view, BarChartPanel)[0]

    empty_height = panel.content_height()
    view.set_chart(
        "Modern metagame share",
        "Last day",
        build_bars([("Temur Prowess", 57.1), ("The Rock", 28.6)]),
        "No data",
    )
    assert panel.content_height() > empty_height


@pytest.mark.usefixtures("wx_app")
def test_the_fallback_actually_paints_the_bar_colour(
    frame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draw into a bitmap and look for the series colour in the pixels.

    This is the assertion wxHTML would have failed: it emitted every label and
    rendered no coloured pixels at all, which is only visible in a screenshot or
    in a test that reads the output back.
    """
    monkeypatch.setenv(DISABLE_WEBVIEW_ENV, "1")
    view = ChartView(frame)
    bars = build_bars([("Temur Prowess", 57.1), ("The Rock", 28.6)])
    view.set_chart("t", "s", bars, "")
    panel = _children(view, BarChartPanel)[0]

    width, height = 600, 60
    bitmap = wx.Bitmap(width, height)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(wx.Colour(*SURFACE_BASE)))
    dc.Clear()
    panel._draw_bars(dc, bars, 0, width)
    del dc

    image = bitmap.ConvertToImage()
    wanted = wx.Colour(bars[0].colour)
    found = any(
        (image.GetRed(x, y), image.GetGreen(x, y), image.GetBlue(x, y))
        == (wanted.Red(), wanted.Green(), wanted.Blue())
        for y in range(height)
        for x in range(0, width, 2)
    )
    assert found, "the fallback drew no bar pixels"


@pytest.mark.usefixtures("wx_app")
def test_sparkline_reports_no_series_until_it_is_given_one(frame) -> None:
    spark = SparkBarPanel(frame)
    spark.set_series([1, 2, 3], ["M", "T", "W"], "6", "last 3 days", (0, 0, 255))
    assert spark._values == [1, 2, 3]
    spark.clear()
    assert spark._values == []
