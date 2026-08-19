"""UI construction for the deck stats panel.

Displays deck statistics as an HTML/CSS visualization: summary statistics, mana
curve, colour distribution, type counts, and opening-hand land probability.

Two backends, one data path
---------------------------
The rich rendering needs ``wx.html2.WebView``, which needs the Microsoft Edge
WebView2 runtime. That runtime ships with Windows 11 and current Windows 10 but
is not guaranteed, so the panel falls back to ``wx.html.HtmlWindow`` -- wxWidgets'
own HTML 3.2 renderer, compiled into wxPython and therefore always present.

Before phase 5 the fallback existed only in the sense that construction did not
crash: the panel logged a warning and left an empty sizer, so a user without
WebView2 saw a blank tab. Both backends now render the same four charts from the
same tuples; the fallback loses the tooltips, the rounded bars and the
side-by-side layout, and keeps the data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

from utils.constants.theme import SURFACE_PANEL
from utils.i18n import translate
from widgets.charts.painter import BarChartPanel
from widgets.charts.view import create_webview as create_webview_control
from widgets.panels.deck_stats_panel.handlers import DeckStatsPanelHandlersMixin
from widgets.panels.deck_stats_panel.properties import DeckStatsPanelPropertiesMixin
from widgets.panels.deck_stats_panel.stats_chart_html import _EMPTY_HTML

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager
    from services.deck_service import DeckService


class DeckStatsPanel(DeckStatsPanelHandlersMixin, DeckStatsPanelPropertiesMixin, wx.Panel):
    """Panel that displays deck statistics using an embedded HTML view."""

    def __init__(
        self,
        parent: wx.Window,
        controller: Any,
        card_manager: CardDataManager | None = None,
        *,
        create_webview: bool = True,
        locale: str | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))

        self.controller = controller
        self.card_manager = card_manager
        self.deck_service: DeckService = controller.deck_service
        self.zone_cards: dict[str, list[dict[str, Any]]] = {}
        self._locale = locale
        self._webview_html = _EMPTY_HTML
        self._webview = None
        self._painted: BarChartPanel | None = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Hidden label kept for test/automation compatibility (summary text readable via GetLabel)
        self.summary_label = wx.StaticText(self, label="No deck loaded.")
        self.summary_label.Hide()

        if create_webview:
            self._create_view()

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    @property
    def uses_webview(self) -> bool:
        """Whether the rich backend is in use. Read by tests and the harness."""
        return self._webview is not None

    def _create_view(self) -> None:
        """Build whichever backend this machine can host. Idempotent."""
        if self._webview is not None or self._painted is not None:
            return

        sizer = self.GetSizer()
        self._webview = create_webview_control(self)
        if self._webview is not None:
            if sizer is not None:
                sizer.Add(self._webview, 1, wx.EXPAND)
                self.Layout()
            self._webview.SetPage(self._webview_html, "")
            return

        self._painted = BarChartPanel(self)
        if sizer is not None:
            sizer.Add(self._painted, 1, wx.EXPAND)
            self.Layout()

    # Kept under its original name: call sites and tests outside this package
    # construct the panel with ``create_webview=`` and nothing else.
    _create_webview = _create_view
