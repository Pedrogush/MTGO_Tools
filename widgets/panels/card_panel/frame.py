"""UI construction for :class:`CardPanel` — a two-tab notebook (Oracle / Stats).

Replaces the standalone oracle text panel that previously sat in the bottom
right of the app. Tab 1 renders the card as MTG-card-like HTML so the textual
data stays readable even when the selected printing has no oracle text on the
art (full-art promos, foreign-language printings).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import wx
import wx.html

from utils.constants import DARK_PANEL, LIGHT_TEXT, SPACE_LG, SPACE_MD, SPACE_SM, SUBDUED_TEXT
from widgets.mana_icon_factory import ManaIconFactory
from widgets.notebook import make_flat_notebook
from widgets.panels.card_panel.handlers import CardPanelHandlersMixin
from widgets.panels.card_panel.properties import CardPanelPropertiesMixin
from widgets.panels.card_panel.rule_popup import RulePopupFrame
from widgets.stylize import apply_type_level, stylize_scrollable


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
        controller: Any,
        mana_icons: ManaIconFactory | None = None,
        t: Callable[..., str] | None = None,
        keyword_lookup_source: Callable[[], Mapping[str, Any]] | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self.controller = controller
        self.mana_icons = mana_icons or ManaIconFactory()
        self._t = t or _default_t

        def _default_keyword_lookup_source() -> Mapping[str, Any]:
            try:
                return controller.comp_rules_service.get_keyword_lookup()
            except Exception:
                return {}

        self._keyword_lookup_source = keyword_lookup_source or _default_keyword_lookup_source
        self._rule_popup: RulePopupFrame | None = None

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

        # FlatNotebook, not wx.Notebook: the native MSW tab control ignores both
        # SetBackgroundColour and SetForegroundColour, so this rendered a white tab
        # strip with black text about 400px from the deck workspace's dark
        # FlatNotebook (issue #962, C3). Migration is the only fix there is.
        self.notebook = make_flat_notebook(self)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, SPACE_SM)

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
        stylize_scrollable(self.oracle_html, surface="panel")
        self.oracle_html.SetBorders(2)
        self.oracle_html.SetMinSize((-1, 200))
        self.oracle_html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self._on_oracle_link_clicked)
        sizer.Add(self.oracle_html, 1, wx.EXPAND | wx.ALL, SPACE_SM)

        self.notebook.AddPage(oracle_panel, self._t("card_panel.tab.oracle_text"))

    def _build_stats_tab(self) -> None:
        stats_panel = wx.ScrolledWindow(self.notebook, style=wx.VSCROLL)
        stylize_scrollable(stats_panel, surface="panel")
        stats_panel.SetScrollRate(0, 10)
        sizer = wx.BoxSizer(wx.VERTICAL)
        stats_panel.SetSizer(sizer)
        self.stats_panel = stats_panel

        # S2. The four levels of this list used to be indented 4 / 6 / 12 px --
        # a 4->6 step is 2px and is simply not seen, so the hierarchy was
        # carried by nothing. Levels now step 8 / 8 / 16 / 24 on the 4px grid
        # and are backed by type and tone rather than indent alone:
        #   L1 card name          heading, primary
        #   L2 format / archetype body,    primary
        #   L3 mainboard/sideboard body,    secondary
        #   L4 the numbers        caption, secondary
        self.stats_card_label = wx.StaticText(stats_panel, label="")
        apply_type_level(self.stats_card_label, "heading")
        self.stats_card_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.stats_card_label, 0, wx.ALL, SPACE_SM)

        self.stats_format_header = self._make_subheader(stats_panel)
        sizer.Add(self.stats_format_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)
        self.stats_format_total = self._make_value_label(stats_panel)
        sizer.Add(self.stats_format_total, 0, wx.LEFT | wx.RIGHT, SPACE_MD)
        self.stats_format_avg = self._make_value_label(stats_panel)
        sizer.Add(self.stats_format_avg, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        self.stats_archetype_header = self._make_subheader(stats_panel)
        sizer.Add(self.stats_archetype_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)

        self.stats_main_header = wx.StaticText(
            stats_panel, label=self._t("card_panel.stats.mainboard")
        )
        apply_type_level(self.stats_main_header, "body")
        self.stats_main_header.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.stats_main_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_MD)
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
            sizer.Add(w, 0, wx.LEFT | wx.RIGHT, SPACE_LG)

        self.stats_side_header = wx.StaticText(
            stats_panel, label=self._t("card_panel.stats.sideboard")
        )
        apply_type_level(self.stats_side_header, "body")
        self.stats_side_header.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.stats_side_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_MD)
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
            sizer.Add(w, 0, wx.LEFT | wx.RIGHT, SPACE_LG)

        self.notebook.AddPage(stats_panel, self._t("card_panel.tab.stats"))

    def _make_subheader(self, parent: wx.Window) -> wx.StaticText:
        """L2 of the Stats hierarchy: primary tone, body weight, no bold.

        These were bold. So was the card name above them and so was every other
        label in the app, which is exactly why bold marked nothing.
        """
        label = wx.StaticText(parent, label="")
        apply_type_level(label, "body")
        label.SetForegroundColour(LIGHT_TEXT)
        return label

    def _make_value_label(self, parent: wx.Window) -> wx.StaticText:
        """L4 of the Stats hierarchy: the numbers themselves."""
        label = wx.StaticText(parent, label="")
        apply_type_level(label, "caption")
        label.SetForegroundColour(SUBDUED_TEXT)
        return label
