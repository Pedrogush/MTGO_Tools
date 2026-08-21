"""A chart surface that degrades from WebView2 to an own-drawn fallback.

``wx.html2.WebView`` needs the Microsoft Edge WebView2 runtime. It ships with
Windows 11 and with current Windows 10, but it is not guaranteed, and a machine
without it must not simply render nothing — which is exactly what the deck stats
panel did before phase 5 (it constructed with ``create_webview=False`` and hid
itself, so the only visible artefact was an empty panel).

:class:`ChartView` therefore has two backends and always has one:

1. ``wx.html2.WebView`` **on its Edge backend**, when that constructs,
2. an own-drawn :class:`~widgets.charts.painter.BarChartPanel` otherwise. The
   first attempt used ``wx.html.HtmlWindow`` for the fallback and, screenshotted,
   drew every label and no bars — see that module for what wxHTML refuses.

The caller passes data, never markup, so both backends are fed from the same
tuples. ``MTGO_TOOLS_DISABLE_WEBVIEW=1`` forces the fallback, which is how the
no-WebView2 path gets exercised on a machine that has the runtime installed.

Why the Edge backend is demanded by name
----------------------------------------
``wxWebView::New()`` with the default backend does *not* fail when WebView2 is
unavailable on MSW: it silently hands back the **IE** backend, which is Trident
in IE7 document mode. IE7 has no flexbox, so every ``display:flex`` row in the
chart CSS collapses to a block — each bar stretches to the full panel width, the
value labels centre themselves above the bars instead of sitting beside them, and
the Card Types labels land on top of their own tracks. That is a *wrong* chart,
not a plainer one, and it is worse than the painted fallback.

It shipped that way because a PyInstaller build did not bundle
``WebView2Loader.dll``. The DLL lives in the wxPython package next to
``wx/_html2*.pyd`` and is loaded by name at runtime, so PyInstaller's static
analysis never sees it; the spec now bundles it and
:func:`ensure_webview2_loader` loads it out of the bundle by absolute path before
wx goes looking. From source nothing changes — wx finds it next to its own
extension module.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import wx
from loguru import logger

from utils.constants.paths import resource_path
from utils.constants.theme import SURFACE_BASE
from widgets.charts.bars import ChartBar, build_webview_page
from widgets.charts.painter import BarChartPanel

#: Set to ``1`` to force the wxHTML fallback. Read once per construction rather
#: than cached at import so a test can flip it between frames.
DISABLE_WEBVIEW_ENV = "MTGO_TOOLS_DISABLE_WEBVIEW"

#: Where ``packaging/mtgo_tools.spec`` puts ``WebView2Loader.dll`` inside the
#: bundle: the same ``wx/`` layout it has in site-packages. The spec declares the
#: same two strings and ``tests/test_webview_backend.py`` cross-checks them, so
#: the bundling and the lookup cannot drift apart.
WEBVIEW2_LOADER_DEST = "wx"
WEBVIEW2_LOADER_NAME = "WebView2Loader.dll"

#: wxPython 4.2 spells the backend names as bytes; ``IsBackendAvailable`` and
#: ``New`` both take either, and the ``str`` form is what logs readably.
EDGE_BACKEND = "wxWebViewEdge"

#: What ``wx.html2.WebViewBackendDefault`` is: "pick for me". Only wxMSW has an
#: IE backend to be silently picked, so it is the only platform that names one.
DEFAULT_BACKEND = ""


def webview_disabled_by_env() -> bool:
    """Whether the environment has asked for the non-WebView path."""
    return os.environ.get(DISABLE_WEBVIEW_ENV, "").strip().lower() in {"1", "true", "yes"}


def webview2_loader_path() -> Path | None:
    """Absolute path of the bundled ``WebView2Loader.dll``, or ``None`` from source.

    Only a frozen build needs this: running from source, the DLL sits beside
    ``wx/_html2*.pyd`` in site-packages where wxWidgets' own load finds it.
    """
    if not getattr(sys, "frozen", False):
        return None
    return resource_path(WEBVIEW2_LOADER_DEST, WEBVIEW2_LOADER_NAME)


def ensure_webview2_loader() -> bool:
    """Pre-load the bundled WebView2 loader DLL so wx's Edge backend can find it.

    wxWidgets loads the DLL with a bare ``LoadLibrary("WebView2Loader.dll")``,
    and the places Windows then searches are not places a PyInstaller bundle can
    count on. Loading it here by absolute path puts it in the process's module
    table under that base name, and wx's later load by name resolves to it —
    measured both ways.

    Returns whether the loader is in the process (``True`` when running from
    source, where wx does its own lookup).
    """
    path = webview2_loader_path()
    if path is None:
        return True
    if not path.exists():
        logger.warning(
            f"{WEBVIEW2_LOADER_NAME} is missing from the bundle at {path}; "
            "the WebView2 chart backend cannot start"
        )
        return False
    try:
        ctypes.WinDLL(str(path))  # type: ignore[attr-defined]  # MSW only
    except Exception as exc:  # pragma: no cover - depends on the host runtime
        logger.warning(f"could not load {path}: {exc}")
        return False
    return True


def preferred_backend() -> str:
    """The backend :func:`create_webview` will ask for by name.

    Naming Edge on MSW is the fix: the default backend there degrades to IE
    without a word. Off MSW the default is WebKit, which renders the chart CSS,
    so nothing needs naming.
    """
    return EDGE_BACKEND if wx.Platform == "__WXMSW__" else DEFAULT_BACKEND


def edge_backend_available() -> bool:
    """Whether wx can give us a WebView that renders the chart CSS.

    On MSW that means the Edge backend specifically: the default backend falls
    back to IE without saying so, and IE renders the charts wrong (see the module
    docstring). Elsewhere the default backend is WebKit, which is fine.
    """
    import wx.html2

    if wx.Platform != "__WXMSW__":  # pragma: no cover - MSW is the shipped platform
        return True
    return bool(wx.html2.WebView.IsBackendAvailable(EDGE_BACKEND))


def create_webview(parent: wx.Window) -> wx.Window | None:
    """Construct a ``wx.html2.WebView`` on ``parent``, or ``None`` if unavailable.

    Every step is guarded: ``wx.html2`` imports fine on a machine with no WebView2
    runtime, ``WebView.New`` can come back as ``None`` rather than raise, and --
    the failure this function exists to catch -- it can come back as a *working
    control on the wrong backend*.
    """
    if webview_disabled_by_env():
        logger.info(f"{DISABLE_WEBVIEW_ENV} is set; using the painted chart fallback")
        return None
    ensure_webview2_loader()
    try:
        import wx.html2

        if not edge_backend_available():
            logger.warning(
                "the WebView2 (Edge) backend is unavailable; using the painted chart "
                "fallback rather than wx's silent IE fallback, which cannot render "
                "the chart layout"
            )
            return None
        # The backend is named rather than defaulted: see the module docstring.
        # wxMSW also frames the control with a light 1px client edge otherwise --
        # the same native chrome phase 2 stripped off wx.Button.
        view = wx.html2.WebView.New(parent, backend=preferred_backend(), style=wx.BORDER_NONE)
    except Exception as exc:  # pragma: no cover - depends on the host runtime
        logger.warning(f"WebView2 unavailable; using the painted chart fallback: {exc}")
        return None
    if view is None:  # pragma: no cover - defensive; WebView.New can return None
        logger.warning("WebView2 returned no control; using the painted chart fallback")
    return view


class ChartView(wx.Panel):
    """Renders a sorted bar chart: on WebView2 if present, own-drawn if not."""

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
