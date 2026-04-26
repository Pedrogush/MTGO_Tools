"""UI construction for :class:`CardPanel` — a two-tab notebook (Oracle / Stats).

Replaces the standalone oracle text panel that previously sat in the bottom
right of the app. Tab 1 renders the card as MTG-card-like HTML so the textual
data stays readable even when the selected printing has no oracle text on the
art (full-art promos, foreign-language printings).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
import wx.html

from utils.constants import DARK_PANEL, LIGHT_TEXT, PADDING_MD, PADDING_SM, SUBDUED_TEXT
from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.card_panel.handlers import CardPanelHandlersMixin
from widgets.panels.card_panel.properties import CardPanelPropertiesMixin


def _default_t(key: str, **fmt: Any) -> str:
    return key.format(**fmt) if fmt else key


class CardPanel(
    CardPanelHandlersMixin,
    CardPanelPropertiesMixin,
    wx.Panel,
):
    """Two-tab notebook displaying card information and play stats."""

    def __init__(
        self,
        parent: wx.Window,
        mana_icons: ManaIconFactory | None = None,
        t: Callable[..., str] | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self.mana_icons = mana_icons or ManaIconFactory()
        self._t = t or _default_t

        self._current_meta: Any = None
        self._current_printing: dict[str, Any] | None = None
        self._current_format: str | None = None
        self._current_archetype: dict[str, Any] | None = None
        self._current_radar: Any | None = None

        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self.notebook = wx.Notebook(self)
        self.notebook.SetBackgroundColour(DARK_PANEL)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, PADDING_SM)

        self._build_oracle_tab()
        self._build_stats_tab()

    def _build_oracle_tab(self) -> None:
        oracle_panel = wx.Panel(self.notebook)
        oracle_panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        oracle_panel.SetSizer(sizer)

        self.oracle_html = wx.html.HtmlWindow(
            oracle_panel,
            style=wx.html.HW_SCROLLBAR_AUTO | wx.NO_BORDER,
        )
        self.oracle_html.SetBackgroundColour(DARK_PANEL)
        self.oracle_html.SetBorders(2)
        self.oracle_html.SetMinSize((-1, 200))
        sizer.Add(self.oracle_html, 1, wx.EXPAND | wx.ALL, PADDING_SM)

        self.notebook.AddPage(oracle_panel, self._t("card_panel.tab.oracle_text"))

    def _build_stats_tab(self) -> None:
        stats_panel = wx.Panel(self.notebook)
        stats_panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        stats_panel.SetSizer(sizer)

        self.stats_card_label = wx.StaticText(stats_panel, label="")
        font = self.stats_card_label.GetFont()
        font.MakeBold()
        font.SetPointSize(font.GetPointSize() + 1)
        self.stats_card_label.SetFont(font)
        self.stats_card_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.stats_card_label, 0, wx.ALL, PADDING_SM)

        self.stats_format_header = self._make_subheader(stats_panel)
        sizer.Add(self.stats_format_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, PADDING_SM)
        self.stats_format_total = self._make_value_label(stats_panel)
        sizer.Add(self.stats_format_total, 0, wx.LEFT | wx.RIGHT, PADDING_MD)
        self.stats_format_avg = self._make_value_label(stats_panel)
        sizer.Add(self.stats_format_avg, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        self.stats_archetype_header = self._make_subheader(stats_panel)
        sizer.Add(self.stats_archetype_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, PADDING_SM)

        self.stats_main_header = wx.StaticText(
            stats_panel, label=self._t("card_panel.stats.mainboard")
        )
        self.stats_main_header.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.stats_main_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)
        self.stats_main_total = self._make_value_label(stats_panel)
        self.stats_main_avg = self._make_value_label(stats_panel)
        self.stats_main_karsten = self._make_value_label(stats_panel)
        self.stats_main_inclusion = self._make_value_label(stats_panel)
        for w in (
            self.stats_main_total,
            self.stats_main_avg,
            self.stats_main_karsten,
            self.stats_main_inclusion,
        ):
            sizer.Add(w, 0, wx.LEFT | wx.RIGHT, PADDING_MD * 2)

        self.stats_side_header = wx.StaticText(
            stats_panel, label=self._t("card_panel.stats.sideboard")
        )
        self.stats_side_header.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.stats_side_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)
        self.stats_side_total = self._make_value_label(stats_panel)
        self.stats_side_avg = self._make_value_label(stats_panel)
        self.stats_side_karsten = self._make_value_label(stats_panel)
        self.stats_side_inclusion = self._make_value_label(stats_panel)
        for w in (
            self.stats_side_total,
            self.stats_side_avg,
            self.stats_side_karsten,
            self.stats_side_inclusion,
        ):
            sizer.Add(w, 0, wx.LEFT | wx.RIGHT, PADDING_MD * 2)

        self.notebook.AddPage(stats_panel, self._t("card_panel.tab.stats"))

    def _make_subheader(self, parent: wx.Window) -> wx.StaticText:
        label = wx.StaticText(parent, label="")
        font = label.GetFont()
        font.MakeBold()
        label.SetFont(font)
        label.SetForegroundColour(LIGHT_TEXT)
        return label

    def _make_value_label(self, parent: wx.Window) -> wx.StaticText:
        label = wx.StaticText(parent, label="")
        label.SetForegroundColour(SUBDUED_TEXT)
        return label
