"""A chart surface that degrades from WebView2 to wxHTML.

``wx.html2.WebView`` needs the Microsoft Edge WebView2 runtime. It ships with
Windows 11 and with current Windows 10, but it is not guaranteed, and a machine
without it must not simply render nothing — which is exactly what the deck stats
panel did before phase 5 (it constructed with ``create_webview=False`` and hid
itself, so the only visible artefact was an empty panel).

:class:`ChartView` therefore has two backends and always has one:

1. ``wx.html2.WebView`` when it constructs,
2. an own-drawn :class:`~widgets.charts.painter.BarChartPanel` otherwise. The
   first attempt used ``wx.html.HtmlWindow`` for the fallback and, screenshotted,
   drew every label and no bars — see that module for what wxHTML refuses.

The caller passes data, never markup, so both backends are fed from the same
tuples. ``MTGO_TOOLS_DISABLE_WEBVIEW=1`` forces the fallback, which is how the
no-WebView2 path gets exercised on a machine that has the runtime installed.
"""

from __future__ import annotations

import os

import wx
from loguru import logger

from utils.constants.theme import SURFACE_BASE
from widgets.charts.bars import ChartBar, build_webview_page
from widgets.charts.painter import BarChartPanel

#: Set to ``1`` to force the wxHTML fallback. Read once per construction rather
#: than cached at import so a test can flip it between frames.
DISABLE_WEBVIEW_ENV = "MTGO_TOOLS_DISABLE_WEBVIEW"


def webview_disabled_by_env() -> bool:
    """Whether the environment has asked for the non-WebView path."""
    return os.environ.get(DISABLE_WEBVIEW_ENV, "").strip().lower() in {"1", "true", "yes"}


def create_webview(parent: wx.Window) -> wx.Window | None:
    """Construct a ``wx.html2.WebView`` on ``parent``, or ``None`` if unavailable.

    Both the import and the construction are guarded: ``wx.html2`` imports fine on
    a machine with no WebView2 runtime and only fails when ``WebView.New`` goes
    looking for the backend, and some failures come back as ``None`` rather than
    an exception.
    """
    if webview_disabled_by_env():
        logger.info(f"{DISABLE_WEBVIEW_ENV} is set; using the wxHTML chart fallback")
        return None
    try:
        import wx.html2

        # wxMSW frames the control with a light 1px client edge otherwise --
        # the same native chrome phase 2 stripped off wx.Button.
        view = wx.html2.WebView.New(parent, style=wx.BORDER_NONE)
    except Exception as exc:  # pragma: no cover - depends on the host runtime
        logger.warning(f"WebView2 unavailable; using the wxHTML chart fallback: {exc}")
        return None
    if view is None:  # pragma: no cover - defensive; WebView.New can return None
        logger.warning("WebView2 returned no control; using the wxHTML chart fallback")
    return view


class ChartView(wx.Panel):
    """Renders a sorted bar chart, on WebView2 if present and wxHTML if not."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(*SURFACE_BASE))

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self._title = ""
        self._subtitle = ""
        self._bars: list[ChartBar] = []
        self._empty_text = ""
        self._painted: BarChartPanel | None = None

        self._webview = create_webview(self)
        if self._webview is not None:
            sizer.Add(self._webview, 1, wx.EXPAND)
            self._painted = None
        else:
            self._painted = BarChartPanel(self)
            sizer.Add(self._painted, 1, wx.EXPAND)

    @property
    def uses_webview(self) -> bool:
        """Whether the rich backend is in use. Read by tests and the harness."""
        return self._webview is not None

    def set_chart(
        self,
        title: str,
        subtitle: str,
        bars: list[ChartBar],
        empty_text: str = "",
    ) -> None:
        """Render ``bars`` on whichever backend this view got."""
        self._title, self._subtitle, self._bars, self._empty_text = (
            title,
            subtitle,
            bars,
            empty_text,
        )
        if self._webview is not None:
            self._webview.SetPage(self.current_html(), "")
        elif self._painted is not None:
            self._painted.set_sections(title, subtitle, [("", bars)], empty_text)

    def current_html(self) -> str:
        """The page this view renders, when it is rendering a page.

        Kept public so a test can assert what the WebView was handed without a
        WebView2 runtime to read it back from.
        """
        return build_webview_page(self._title, self._subtitle, self._bars, self._empty_text)
